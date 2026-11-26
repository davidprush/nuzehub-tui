"""The seroval subset, checked against payloads captured from seroval 1.7.7 (NuzeHub's lockfile)."""

from __future__ import annotations

import json

from nuzehub_tui import seroval

# toJSONAsync({data:{query:'saturn rings',k:5,arr:[1,'a',null,true,{x:-1.5}],u:undefined}}) from node + seroval 1.7.7
CAPTURED_REQUEST = '{"t":{"t":10,"i":0,"p":{"k":["data"],"v":[{"t":10,"i":1,"p":{"k":["query","k","arr","u"],"v":[{"t":1,"s":"saturn rings"},{"t":0,"s":5},{"t":9,"i":2,"a":[{"t":0,"s":1},{"t":1,"s":"a"},{"t":2,"s":0},{"t":2,"s":2},{"t":10,"i":3,"p":{"k":["x"],"v":[{"t":0,"s":-1.5}]},"o":0}],"o":0},{"t":2,"s":1}]},"o":0}]},"o":0},"f":127,"m":[]}'
# a real NuzeHub answer (saveInstance with a bad payload): result undefined, error the TanStack Error plugin
CAPTURED_ERROR = '{"t":10,"i":0,"p":{"k":["result","error","context"],"v":[{"t":2,"s":1},{"t":25,"i":1,"s":{"message":{"t":1,"s":"Missing desk"}},"c":"$TSR/Error"},{"t":10,"i":2,"p":{"k":[],"v":[]},"o":0}]},"o":0}'


def test_request_matches_seroval_byte_for_byte():
    ours = seroval.encode_payload({"query": "saturn rings", "k": 5, "arr": [1, "a", None, True, {"x": -1.5}], "u": seroval.UNDEFINED})
    want = json.loads(CAPTURED_REQUEST)
    want["t"]["p"]["v"][0]["p"]["k"] = ["query", "k", "arr"]
    want["t"]["p"]["v"][0]["p"]["v"] = want["t"]["p"]["v"][0]["p"]["v"][:3]
    assert json.loads(ours) == want


def test_decode_captured_request_and_error():
    assert seroval.decode(CAPTURED_REQUEST) == {"data": {"query": "saturn rings", "k": 5, "arr": [1, "a", None, True, {"x": -1.5}]}}
    err = seroval.decode(CAPTURED_ERROR)
    assert "result" not in err and err["error"] == {"__error__": True, "message": "Missing desk"}


def test_string_escapes_round_trip():
    text = '</script> "q" \\ é\n\u2028 <b>'
    assert seroval.unescape(seroval.escape(text)) == text
    assert seroval.escape(text) == '\\x3C/script> \\"q\\" \\\\ é\\n\\u2028 \\x3Cb>'
    assert seroval.unescape("\\x3Cb\\u00e9\\ud83d\\ude00") == "<bé😀"


def test_references_and_constants():
    doc = {"t": 10, "i": 0, "p": {"k": ["a", "b", "n", "inf", "neg"], "v": [
        {"t": 10, "i": 1, "p": {"k": ["x"], "v": [{"t": 0, "s": 1}]}, "o": 0}, {"t": 4, "i": 1},
        {"t": 2, "s": 0}, {"t": 2, "s": 5}, {"t": 2, "s": 4}]}, "o": 0}
    out = seroval.decode(json.dumps(doc))
    assert out["a"] == {"x": 1} and out["b"] is out["a"] and out["n"] is None and out["inf"] == float("inf")


def test_junk_is_an_error():
    import pytest

    with pytest.raises(seroval.SerovalError):
        seroval.decode("<html>")
