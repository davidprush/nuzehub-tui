"""HTTP client for the running NuzeHub server (LaunchAgent ``net.secondbrain.nuzehub``).

It calls the server's existing TanStack ``createServerFn`` handlers exactly as the web desk does:
``POST /_serverFn/<id>`` with ``x-tsr-serverFn: true``, a seroval payload, and a same-origin ``Origin``
header (TanStack's CSRF check). Every handler keeps its own ``assertOpen`` / ``assertHost`` guard on the
server: the host computer, a trusted device, or a session that unlocked with the host key. The client never
logs, prints or stores the key, and it drops the ``key`` field that ``accessStatus`` returns to the host.

Function ids: in the dev server NuzeHub's LaunchAgent runs (``npm run dev``), an id is the base64url of
``{"file":"/src/lib/<file>?tss-serverfn-split","export":"<name>_createServerFn_handler"}``. If the server
does not know a computed id, the client reads the ids from the same client module the browser loads
(``GET /src/lib/<file>``) once and retries, so a changed id scheme does not break the TUI silently.
"""

from __future__ import annotations

import base64
import http.cookiejar
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nuzehub_tui import seroval

DEFAULT_URL = "http://127.0.0.1:8080"

# handler name -> module under src/lib (NuzeHub 1.2.1 + 1.3 + 1.5 + wiki ranking + Wikipedia Library panel)
FUNCTIONS: dict[str, str] = {
    "accessStatus": "host/api.ts",
    "unlockHost": "host/api.ts",
    "loadInstance": "host/api.ts",
    "saveInstance": "host/api.ts",
    "probeEngines": "host/api.ts",
    "fetchNews": "desk/server-fns.ts",
    "fetchArticle": "desk/server-fns.ts",
    "getMarkets": "desk/server-fns.ts",
    "searchSymbols": "desk/server-fns.ts",
    "getHazards": "desk/server-fns.ts",
    "wikiPanelStatus": "host/wiki-api.ts",
    "wikiPanelSearch": "host/wiki-api.ts",
    "wikiPanelRead": "host/wiki-api.ts",
    "wikiPanelRelated": "host/wiki-api.ts",
}

NEEDS_KEY = "This remote session needs the API key."


class NuzeHubError(Exception):
    """A call failed. ``str()`` is a sentence the TUI shows as is (never a key or a key link)."""


class Unreachable(NuzeHubError):
    pass


class TimedOut(NuzeHubError):
    pass


class AccessDenied(NuzeHubError):
    pass


class ServerError(NuzeHubError):
    pass


def function_id(name: str, module: str | None = None) -> str:
    module = module or FUNCTIONS[name]
    raw = json.dumps(
        {"file": f"/src/lib/{module}?tss-serverfn-split", "export": f"{name}_createServerFn_handler"},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _export_of(fn_id: str) -> str:
    try:
        pad = "=" * (-len(fn_id) % 4)
        data = json.loads(base64.urlsafe_b64decode(fn_id + pad))
        return str(data.get("export", ""))
    except (ValueError, TypeError):
        return ""


def clean_base_url(url: str) -> str:
    """``http://host:port`` only. A ``?key=`` link is refused without echoing it."""
    raw = (url or "").strip() or DEFAULT_URL
    if "://" not in raw:
        raw = "http://" + raw
    parts = urllib.parse.urlsplit(raw)
    if parts.query or parts.fragment or "key=" in raw:
        raise NuzeHubError(
            "Give the NuzeHub address without ?key=… (for example http://127.0.0.1:8080). "
            "The TUI asks for the key itself and never stores it."
        )
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise NuzeHubError("The NuzeHub address must look like http://127.0.0.1:8080.")
    host = parts.hostname
    port = f":{parts.port}" if parts.port else ""
    shown = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{shown}{port}"


def is_loopback(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


Opener = Callable[[urllib.request.Request, float], Any]


@dataclass
class NuzeHubClient:
    base_url: str = DEFAULT_URL
    timeout: float = 30.0
    log: Callable[[str], None] | None = None
    _jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar, repr=False)
    _ids: dict[str, str] = field(default_factory=dict, repr=False)
    _discovered: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.base_url = clean_base_url(self.base_url)
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))

    # ---- transport ----------------------------------------------------------------------------
    @property
    def loopback(self) -> bool:
        return is_loopback(self.base_url)

    def _note(self, text: str) -> None:
        if self.log:
            self.log(text)

    def _open(self, req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
        try:
            with self._opener.open(req, timeout=timeout) as res:
                return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp else b""
            return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body
        except TimeoutError as exc:
            raise TimedOut(f"NuzeHub at {self.base_url} did not answer within {timeout:g} s.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError | socket.timeout):
                raise TimedOut(f"NuzeHub at {self.base_url} did not answer within {timeout:g} s.") from exc
            raise Unreachable(self._client_hint() or (
                f"NuzeHub is not answering at {self.base_url}. On the server check it is running "
                "(launchctl print gui/$(id -u)/net.secondbrain.nuzehub), then press r."
            )) from exc
        except (ConnectionError, OSError) as exc:
            raise Unreachable(self._client_hint() or
                              f"NuzeHub is not answering at {self.base_url}. Press r to try again.") from exc

    def _client_hint(self) -> str:
        """0.1.1: loopback did not answer and this Mac has the ``nuzehub-remote`` launcher, so it is a client."""
        if self.loopback and (Path.home() / ".local/bin/nuzehub-remote").exists():
            return (f"Open NuzeHub with nuzehub-remote (quit with q): it runs on the NuzeHub server, not on this Mac, so "
                    f"{self.base_url} does not answer.")
        return ""

    def _post(self, fn_id: str, data: Any, timeout: float) -> tuple[int, dict[str, str], bytes]:
        body = seroval.encode_payload(data).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/_serverFn/{fn_id}",
            data=body,
            method="POST",
            headers={
                "x-tsr-serverFn": "true",
                "accept": "application/json",
                "content-type": "application/json",
                # TanStack's CSRF middleware: the request comes from the desk's own origin.
                "origin": self.base_url,
                "user-agent": "nuzehub-tui",
            },
        )
        return self._open(req, timeout)

    def _discover(self, module: str) -> None:
        if module in self._discovered:
            return
        self._discovered.add(module)
        req = urllib.request.Request(f"{self.base_url}/src/lib/{module}", headers={"user-agent": "nuzehub-tui"})
        status, _h, body = self._open(req, self.timeout)
        if status != 200:
            return
        for fn_id in re.findall(r'createClientRpc\(\s*"([A-Za-z0-9_-]+)"', body.decode("utf-8", "replace")):
            export = _export_of(fn_id)
            if export.endswith("_createServerFn_handler"):
                self._ids[export.removesuffix("_createServerFn_handler")] = fn_id

    def call(self, name: str, data: Any = seroval.UNDEFINED, *, timeout: float | None = None) -> Any:
        """Run one server function and return its result. Raises a ``NuzeHubError`` with a plain sentence."""
        module = FUNCTIONS[name]
        wait = timeout or self.timeout
        fn_id = self._ids.get(name) or function_id(name, module)
        status, headers, body = self._post(fn_id, data, wait)
        if status in (404, 500) and b"HTTPError" in body and module not in self._discovered:
            self._discover(module)
            if self._ids.get(name) and self._ids[name] != fn_id:
                fn_id = self._ids[name]
                status, headers, body = self._post(fn_id, data, wait)
        self._note(f"{name}: HTTP {status}")
        if status == 403:
            raise AccessDenied(
                "NuzeHub refused the request (403). Use the address NuzeHub prints, for example "
                "http://127.0.0.1:8080 on the server."
            )
        if status != 200 or "x-tss-serialized" not in headers:
            raise ServerError(f"NuzeHub could not run {name} (HTTP {status}). Press r to try again.")
        try:
            answer = seroval.decode(body)
        except seroval.SerovalError as exc:
            raise ServerError(f"NuzeHub answered {name} with something the TUI cannot read.") from exc
        if not isinstance(answer, dict):
            raise ServerError(f"NuzeHub answered {name} with something the TUI cannot read.")
        err = answer.get("error")
        if isinstance(err, dict) and err.get("__error__"):
            message = str(err.get("message") or "Server error")
            if NEEDS_KEY in message or "needs the API key" in message:
                raise AccessDenied("This session needs the host key. Type it in the key field and press Unlock.")
            raise ServerError(message)
        return answer.get("result")

    # ---- access -------------------------------------------------------------------------------
    def access_status(self) -> dict[str, Any]:
        view = dict(self.call("accessStatus") or {})
        view.pop("key", None)  # the host sees its own key; the TUI never keeps or shows it
        return view

    def unlock(self, key: str) -> dict[str, Any]:
        view = dict(self.call("unlockHost", {"key": key}) or {})
        view.pop("key", None)
        return view

    # ---- desk ---------------------------------------------------------------------------------
    def load_instance(self) -> dict[str, Any]:
        return dict(self.call("loadInstance") or {})

    def save_instance(self, *, desk: Any = None, brain: Any = None, base_rev: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"desk": desk, "brain": brain}
        if base_rev is not None:
            payload["baseRev"] = base_rev
        return dict(self.call("saveInstance", payload) or {})

    def fetch_news(self, urls: list[str]) -> dict[str, Any]:
        return dict(self.call("fetchNews", {"urls": urls[:40]}, timeout=45) or {})

    def fetch_article(self, url: str) -> dict[str, Any]:
        return dict(self.call("fetchArticle", {"url": url}, timeout=30) or {})

    def get_markets(self, symbols: list[str], rng: str, sources: list[str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"symbols": symbols, "range": rng}
        if sources:
            data["sources"] = sources
        return dict(self.call("getMarkets", data, timeout=45) or {})

    def search_symbols(self, query: str) -> dict[str, Any]:
        return dict(self.call("searchSymbols", {"query": query}) or {})

    def get_hazards(self, window: str, kinds: list[str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"window": window}
        if kinds is not None:
            data["kinds"] = kinds
        return dict(self.call("getHazards", data, timeout=45) or {})

    # ---- Wikipedia (Second Brain library through the host) ------------------------------------
    def wiki_status(self) -> dict[str, Any]:
        return dict(self.call("wikiPanelStatus", timeout=20) or {})

    def wiki_search(self, query: str, k: int = 10) -> dict[str, Any]:
        return dict(self.call("wikiPanelSearch", {"query": query, "k": k}, timeout=40) or {})

    def wiki_read(self, title: str) -> dict[str, Any]:
        return dict(self.call("wikiPanelRead", {"title": title}, timeout=35) or {})

    def wiki_related(self, title: str, text: str = "") -> dict[str, Any]:
        return dict(self.call("wikiPanelRelated", {"title": title, "text": text[:2000]}, timeout=120) or {})

    # ---- models -------------------------------------------------------------------------------
    def probe_engines(self) -> dict[str, Any]:
        return dict(self.call("probeEngines", timeout=20) or {})

    def model_status(self) -> dict[str, Any] | None:
        """``GET /api/model-status`` (1.5 probe fix; loopback callers only). None when not loopback or absent."""
        if not self.loopback:
            return None
        req = urllib.request.Request(f"{self.base_url}/api/model-status", headers={"user-agent": "nuzehub-tui"})
        try:
            status, _h, body = self._open(req, 10)
        except NuzeHubError:
            return None
        if status != 200:
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None
