"""The small part of seroval's cross-JSON format that NuzeHub's server functions use.

TanStack Start (1.168, the version NuzeHub pins) sends a server-function payload as
``JSON.stringify(await toJSONAsync({data}))`` and answers with the same format. Only plain JSON values
cross this wire (strings, numbers, booleans, null, arrays, objects), plus the error plugin node TanStack
uses for a thrown ``Error``. Anything else decodes to ``None`` rather than guessing.
"""

from __future__ import annotations

import json
import math
from typing import Any

# Node types (seroval SerovalNodeType).
NUMBER, STRING, CONSTANT, BIGINT, INDEXED, DATE, REGEXP, SET, MAP, ARRAY, OBJECT, NULL_OBJECT = range(12)
PLUGIN = 25
ERROR = 13
# Constants (seroval SerovalConstant).
_CONSTANTS: dict[int, Any] = {0: None, 1: None, 2: True, 3: False, 4: -0.0, 5: math.inf, 6: -math.inf, 7: math.nan}
UNDEFINED = object()  # decoded ``undefined``; callers see it as a missing value

_ESC = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\b": "\\b", "\t": "\\t", "\f": "\\f",
        "<": "\\x3C", "\u2028": "\\u2028", "\u2029": "\\u2029"}
_SIMPLE = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "r": "\r", "b": "\b", "t": "\t", "f": "\f", "v": "\v",
           "0": "\0", "/": "/"}


def escape(text: str) -> str:
    """seroval ``serializeString``: JSON escapes plus ``<`` and the two line separators."""
    out = []
    for ch in text:
        rep = _ESC.get(ch)
        if rep is not None:
            out.append(rep)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def unescape(text: str) -> str:
    """seroval ``deserializeString``."""
    if "\\" not in text:
        return text
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != "\\" or i == n - 1:
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "x" and i + 3 < n + 0 and _ishex(text[i + 2 : i + 4]):
            out.append(chr(int(text[i + 2 : i + 4], 16)))
            i += 4
        elif nxt == "u" and _ishex(text[i + 2 : i + 6]) and len(text[i + 2 : i + 6]) == 4:
            code = int(text[i + 2 : i + 6], 16)
            if 0xD800 <= code < 0xDC00 and text[i + 6 : i + 8] == "\\u" and _ishex(text[i + 8 : i + 12]):
                low = int(text[i + 8 : i + 12], 16)
                if 0xDC00 <= low < 0xE000:
                    out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                    i += 12
                    continue
            out.append(chr(code))
            i += 6
        elif nxt in _SIMPLE:
            out.append(_SIMPLE[nxt])
            i += 2
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


def _ishex(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdefABCDEF" for c in s)


class _Encoder:
    def __init__(self) -> None:
        self.next_id = 0

    def node(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {"t": CONSTANT, "s": 0}
        if value is True:
            return {"t": CONSTANT, "s": 2}
        if value is False:
            return {"t": CONSTANT, "s": 3}
        if isinstance(value, int | float):
            f = float(value)
            if math.isnan(f):
                return {"t": CONSTANT, "s": 7}
            if math.isinf(f):
                return {"t": CONSTANT, "s": 5 if f > 0 else 6}
            if f == 0 and math.copysign(1, f) < 0:
                return {"t": CONSTANT, "s": 4}
            return {"t": NUMBER, "s": value}
        if isinstance(value, str):
            return {"t": STRING, "s": escape(value)}
        if isinstance(value, list | tuple):
            idx = self._id()
            return {"t": ARRAY, "i": idx, "a": [self.node(v) for v in value], "o": 0}
        if isinstance(value, dict):
            idx = self._id()
            keys = [k for k, v in value.items() if v is not UNDEFINED]
            return {"t": OBJECT, "i": idx,
                    "p": {"k": [escape(str(k)) for k in keys], "v": [self.node(value[k]) for k in keys]}, "o": 0}
        raise TypeError(f"cannot send {type(value).__name__} to a server function")

    def _id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i


def encode_payload(data: Any) -> str:
    """The POST body TanStack's ``serverFnFetcher`` sends: ``{data}`` as seroval cross-JSON."""
    enc = _Encoder()
    root = enc.node({"data": data}) if data is not UNDEFINED else enc.node({})
    return json.dumps({"t": root, "f": 127, "m": []}, ensure_ascii=False, separators=(",", ":"))


class SerovalError(ValueError):
    pass


class _Decoder:
    def __init__(self) -> None:
        self.refs: dict[int, Any] = {}

    def value(self, node: Any) -> Any:
        if not isinstance(node, dict):
            return None  # an array hole
        t = node.get("t")
        if t == NUMBER:
            return node.get("s")
        if t == STRING:
            return unescape(str(node.get("s", "")))
        if t == CONSTANT:
            s = node.get("s")
            return UNDEFINED if s == 1 else _CONSTANTS.get(int(s) if isinstance(s, int) else -1)
        if t == BIGINT:
            try:
                return int(str(node.get("s")))
            except ValueError:
                return None
        if t == INDEXED:
            return self.refs.get(int(node.get("i", -1)))
        if t == DATE:
            return self._keep(node, str(node.get("s", "")))
        if t == ARRAY:
            out: list[Any] = []
            self._keep(node, out)
            for item in node.get("a") or []:
                v = self.value(item)
                out.append(None if v is UNDEFINED else v)
            return out
        if t in (OBJECT, NULL_OBJECT):
            obj: dict[str, Any] = {}
            self._keep(node, obj)
            props = node.get("p") or {}
            for k, v in zip(props.get("k") or [], props.get("v") or [], strict=False):
                val = self.value(v)
                if val is not UNDEFINED:
                    obj[unescape(str(k))] = val
            return obj
        if t == SET:
            items: list[Any] = []
            self._keep(node, items)
            items.extend(self.value(v) for v in node.get("a") or [])
            return items
        if t == MAP:
            m: dict[str, Any] = {}
            self._keep(node, m)
            e = node.get("e") or {}
            for k, v in zip(e.get("k") or [], e.get("v") or [], strict=False):
                m[str(self.value(k))] = self.value(v)
            return m
        if t == ERROR or (t == PLUGIN and "Error" in str(node.get("c", ""))):
            s = node.get("s") or {}
            msg = ""
            if isinstance(s, dict):
                raw = s.get("message")
                msg = self.value(raw) if isinstance(raw, dict) else str(raw or "")
            if not msg:
                msg = unescape(str(node.get("m", ""))) or "Server error"
            err = {"__error__": True, "message": msg}
            return self._keep(node, err)
        return None

    def _keep(self, node: dict[str, Any], value: Any) -> Any:
        if "i" in node:
            self.refs[int(node["i"])] = value
        return value


def decode(text: str | bytes) -> Any:
    """A server-function answer (``application/json`` + ``x-tss-serialized``) as plain Python."""
    try:
        raw = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise SerovalError("the server answered something that is not JSON") from exc
    root = raw.get("t") if isinstance(raw, dict) and "t" in raw and isinstance(raw.get("t"), dict) else raw
    value = _Decoder().value(root)
    return None if value is UNDEFINED else value
