"""A local stand-in of the NuzeHub server functions the TUI calls, over real HTTP.

Same wire as TanStack Start 1.168 (``POST /_serverFn/<id>``, seroval in and out, ``x-tss-serialized``),
same CSRF rule (Origin must be the server's own origin), same access rule as ``instance.server.ts``
(host/loopback or trusted is open; otherwise a cookie seat after ``unlockHost`` with the key; a wrong key
says "That key does not match."), and the Wikipedia panel's answers read from real SQLite files: the status
names one file, and search/read answer from it (or, in ``fallback`` mode, from a default-path library the way
Second Brain did before 1.0.2, with the status of the file actually used).
"""

from __future__ import annotations

import copy
import json
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from nuzehub_tui import seroval
from nuzehub_tui.client import FUNCTIONS, function_id
from nuzehub_tui.demo import DemoBackend
from nuzehub_tui.desk import wiki_url

COOKIE = "nuzehub_seat"


def _enc_value(enc: Any, value: Any) -> dict[str, Any]:
    return enc.node(value)


def encode_answer(result: Any, error: str | None = None) -> bytes:
    enc = seroval._Encoder()
    res_node = enc.node(result) if result is not None or error is None else {"t": 2, "s": 1}
    if error is None:
        err_node: dict[str, Any] = {"t": 2, "s": 1}
    else:
        err_node = {"t": 25, "i": enc._id(), "s": {"message": {"t": 1, "s": seroval.escape(error)}}, "c": "$TSR/Error"}
    ctx = {"t": 11, "i": enc._id(), "p": {"k": [], "v": []}, "o": 0}
    root = {"t": 10, "i": 999, "p": {"k": ["result", "error", "context"], "v": [res_node, err_node, ctx]}, "o": 0}
    return json.dumps(root, ensure_ascii=False).encode()


def make_library(path: Path, titles: list[tuple[str, str, str]], *, wid_base: int = 1000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE articles (rowid INTEGER PRIMARY KEY, wid TEXT, title TEXT, abstract TEXT, text TEXT)")
    for i, (title, abstract, text) in enumerate(titles, start=1):
        con.execute("INSERT INTO articles VALUES (?,?,?,?,?)", (i, str(wid_base + i), title, abstract, text))
    con.commit()
    con.close()
    return path


REAL_ARTICLES = [
    ("Saturn", "Saturn is the sixth planet from the Sun.", "# Saturn\n\nSaturn is the sixth planet. The Rings of Saturn are ice. Cassini–Huygens orbited it."),
    ("Rings of Saturn", "The rings of Saturn are the most extensive ring system.", "# Rings of Saturn\n\nSaturn has seven main rings. Saturn is their planet."),
    ("Cassini–Huygens", "Cassini–Huygens was a mission to Saturn.", "# Cassini–Huygens\n\nA mission to Saturn that ended in 2017."),
    ("Saturn V", "Saturn V was an American super heavy-lift rocket.", "# Saturn V\n\nThe rocket of the Apollo program."),
]
DECOY_ARTICLES = [(f"Decoy {t}", f"Decoy {a}", t2.replace("# ", "# Decoy ")) for t, a, t2 in REAL_ARTICLES]


class Wiki:
    """The panel's server side, reduced: status names ``named``; ``mode`` is "fixed" (Second Brain 1.0.2) or
    "fallback" (pre-1.0.2: a missing named file is answered from the first default-path library that exists)."""

    def __init__(self, named: Path, defaults: list[Path], mode: str = "fixed", source: str = "primary") -> None:
        self.named = named
        self.defaults = defaults
        self.mode = mode
        self.source = source
        self.vanish_after_status = False
        self.slow = 0.0

    def _status_for(self, path: Path | None, exists: bool) -> dict[str, Any]:
        if self.source == "remote":
            return {"state": "on", "line": "on (4 articles, remote nuzehub.example over ssh, current)", "source": "remote",
                    "sourceLabel": "the server over ssh", "path": "", "articles": "4", "freshness": "current", "lastSync": "", "lastAnswer": ""}
        if path is None or not exists:
            return {"state": "off", "line": f"off (missing: no library at {self.named})", "source": "primary",
                    "sourceLabel": "Server primary", "path": str(self.named), "articles": "", "freshness": "",
                    "lastSync": "", "lastAnswer": ""}
        return {"state": "on", "line": f"on (4 articles, Server primary {path}, current)", "source": "primary",
                "sourceLabel": "Server primary", "path": str(path), "articles": "4", "freshness": "current",
                "lastSync": "", "lastAnswer": ""}

    def status(self) -> dict[str, Any]:
        if self.source == "remote":
            return self._status_for(None, True)
        return self._status_for(self.named, self.named.is_file())

    def _answering_file(self) -> Path | None:
        if self.source == "remote":
            return self.named if self.named.is_file() else None
        if self.named.is_file():
            return self.named
        if self.mode == "fallback":
            return next((d for d in self.defaults if d.is_file()), None)
        return None

    def _rows(self, db: Path, query: str, k: int) -> list[dict[str, Any]]:
        words = [w for w in query.lower().split() if w]
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT rowid, wid, title, abstract, text FROM articles ORDER BY rowid").fetchall()
        finally:
            con.close()
        hits = [r for r in rows if all(w in f"{r[2]} {r[4]}".lower() for w in words)]
        hits.sort(key=lambda r: (0 if all(w in r[2].lower() for w in words) else 1, len(r[2])))
        return [{"rank": i + 1, "title": r[2], "url": wiki_url(r[2]), "snip": r[3], "abstract": r[3], "textLen": len(r[4])}
                for i, r in enumerate(hits[:k])]

    def _fail(self) -> dict[str, Any]:
        st = self.status()
        return {"ok": False, "reason": "unavailable", "message": st["line"], "status": st}

    def search(self, query: str, k: int) -> dict[str, Any]:
        if not query.strip():
            return {"ok": False, "reason": "bad-query", "message": "Type something to search for."}
        if self.slow:
            time.sleep(self.slow)
        if self.vanish_after_status and self.named.is_file():
            self.named.rename(self.named.with_suffix(".away"))
        db = self._answering_file()
        if db is None:
            return self._fail()
        return {"ok": True, "query": query, "results": self._rows(db, query, k), "status": self._status_for(db, True)}

    def read(self, title: str) -> dict[str, Any]:
        db = self._answering_file()
        if db is None:
            return self._fail()
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT title, abstract, text FROM articles WHERE title = ?", (title,)).fetchone()
            titles = [r[0] for r in con.execute("SELECT title FROM articles")]
        finally:
            con.close()
        if not row:
            return {"ok": False, "reason": "not-found", "message": f"No article titled “{title}” in the library."}
        links = [{"phrase": t, "title": t} for t in titles if t != row[0] and t in row[2]]
        return {"ok": True, "article": {"title": row[0], "url": wiki_url(row[0]), "abstract": row[1], "text": row[2],
                                        "dateCreated": "", "truncated": False}, "links": links, "status": self._status_for(db, True)}

    def related(self, title: str, text: str) -> dict[str, Any]:
        db = self._answering_file()
        if db is None:
            return self._fail()
        seen: dict[str, dict[str, Any]] = {}
        for word in [w for w in f"{title} {text}".replace(",", " ").split() if w[:1].isupper()][:4]:
            for row in self._rows(db, word, 4):
                seen.setdefault(row["title"], {**row, "via": word})
        if not seen:
            return {"ok": False, "reason": "bad-query", "message": "Nothing to look up in that item."}
        rows = list(seen.values())
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return {"ok": True, "queries": [title], "results": rows, "status": self._status_for(db, True)}


class StandIn:
    def __init__(self, *, wiki: Wiki | None = None, peer: str = "host", key: str = "test-key-placeholder",
                 id_scheme: str = "dev") -> None:
        self.data = DemoBackend()
        self.wiki = wiki
        self.peer = peer  # host | trusted | remote
        self.key = key
        self.seats: set[str] = set()
        self.id_scheme = id_scheme
        self.delay = 0.0
        self.requests: list[tuple[str, str]] = []
        self.stored_bytes = b""
        self._store_bytes()
        names = {}
        for name in FUNCTIONS:
            fid = function_id(name) if id_scheme == "dev" else secrets.token_hex(16)
            names[fid] = name
        self.ids = names
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> StandIn:
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def _store_bytes(self) -> None:
        self.stored_bytes = json.dumps(self.data.instance, sort_keys=True, ensure_ascii=False).encode()

    def _open(self, cookie: str | None) -> bool:
        return self.peer in ("host", "trusted") or (cookie is not None and cookie in self.seats)

    def run(self, name: str, data: Any, cookie: str | None) -> tuple[Any, str | None, str | None]:
        """(result, error message, cookie to set)."""
        d = data if isinstance(data, dict) else {}
        view = {"open": self._open(cookie), "remote": self.peer != "host", "busy": False}
        if self.peer == "host":
            view["key"] = self.key  # the real server returns the key to the host; the TUI must drop it
        if self.peer == "trusted":
            view["trusted"] = True
        if name == "accessStatus":
            return view, None, None
        if name == "unlockHost":
            if self.peer != "remote":
                return view, None, None
            if str(d.get("key", "")).strip() != self.key:
                return {"open": False, "remote": True, "busy": False, "key": None, "error": "That key does not match."}, None, None
            seat = secrets.token_hex(12)
            self.seats.add(seat)
            return {"open": True, "remote": True, "busy": False, "key": None}, None, seat
        if not self._open(cookie):
            return None, "This remote session needs the API key.", None
        b = self.data
        if name == "loadInstance":
            inst = b.load_instance()
            return {"desk": inst["desk"], "brain": inst["brain"], "rev": inst["rev"]}, None, None
        if name == "saveInstance":
            if not d or ("desk" not in d and "brain" not in d):
                return None, "Missing desk", None
            res = b.save_instance(desk=d.get("desk"), brain=d.get("brain"), base_rev=d.get("baseRev"))
            self._store_bytes()
            return res, None, None
        if name == "fetchNews":
            return b.fetch_news(list(d.get("urls") or [])), None, None
        if name == "fetchArticle":
            return b.fetch_article(str(d.get("url", ""))), None, None
        if name == "getMarkets":
            return b.get_markets(list(d.get("symbols") or []), str(d.get("range", "1mo"))), None, None
        if name == "searchSymbols":
            return b.search_symbols(str(d.get("query", ""))), None, None
        if name == "getHazards":
            return b.get_hazards(str(d.get("window", "24h")), d.get("kinds")), None, None
        if name == "probeEngines":
            return b.probe_engines(), None, None
        if name.startswith("wikiPanel"):
            w = self.wiki
            if w is None:
                fn = {"wikiPanelStatus": lambda: b.wiki_status(), "wikiPanelSearch": lambda: b.wiki_search(str(d.get("query", "")), int(d.get("k", 10))),
                      "wikiPanelRead": lambda: b.wiki_read(str(d.get("title", ""))),
                      "wikiPanelRelated": lambda: b.wiki_related(str(d.get("title", "")), str(d.get("text", "")))}[name]
                return fn(), None, None
            if name == "wikiPanelStatus":
                return w.status(), None, None
            if name == "wikiPanelSearch":
                return w.search(str(d.get("query", "")), int(d.get("k", 10))), None, None
            if name == "wikiPanelRead":
                return w.read(str(d.get("title", ""))), None, None
            return w.related(str(d.get("title", "")), str(d.get("text", ""))), None, None
        return None, f"no handler {name}", None

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _send(self, code: int, body: bytes, headers: dict[str, str]) -> None:
                self.send_response(code)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                outer.requests.append(("GET", path))
                if path == "/api/model-status":
                    body = json.dumps(outer.data.model_status()).encode()
                    self._send(200, body, {"content-type": "application/json"})
                    return
                if path.startswith("/src/lib/"):
                    module = path[len("/src/lib/"):]
                    lines = [f'export const {n} = createClientRpc("{fid}");' for fid, n in outer.ids.items() if FUNCTIONS[n] == module]
                    if outer.id_scheme != "dev":
                        import base64
                        lines = []
                        for _fid, n in list(outer.ids.items()):
                            if FUNCTIONS[n] != module:
                                continue
                            alias = base64.urlsafe_b64encode(json.dumps({"file": f"/x/{module}", "export": f"{n}_createServerFn_handler"}).encode()).decode().rstrip("=")
                            outer.ids[alias] = n
                            lines.append(f'createClientRpc("{alias}")')
                    self._send(200, "\n".join(lines).encode(), {"content-type": "text/javascript"})
                    return
                self._send(404, b"not found", {"content-type": "text/plain"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                path = self.path.split("?", 1)[0]
                if not path.startswith("/_serverFn/"):
                    self._send(404, b"not found", {"content-type": "text/plain"})
                    return
                origin = self.headers.get("origin")
                if origin != outer.url or self.headers.get("x-tsr-serverFn") != "true":
                    self._send(403, b"Forbidden", {"content-type": "text/plain;charset=UTF-8"})
                    return
                name = outer.ids.get(path[len("/_serverFn/"):])
                outer.requests.append(("POST", name or "?"))
                if name is None:
                    self._send(500, b'{"status":500,"unhandled":true,"message":"HTTPError"}', {"content-type": "application/json"})
                    return
                if outer.delay:
                    time.sleep(outer.delay)
                data = seroval.decode(raw) if raw else {}
                payload = (data or {}).get("data") if isinstance(data, dict) else None
                cookie = None
                for part in (self.headers.get("cookie") or "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == COOKIE:
                        cookie = v
                result, error, seat = outer.run(name, copy.deepcopy(payload), cookie)
                headers = {"content-type": "application/json", "x-tss-serialized": "true"}
                if seat:
                    headers["set-cookie"] = f"{COOKIE}={seat}; Path=/; HttpOnly; SameSite=Lax"
                self._send(200, encode_answer(result, error), headers)

        return H
