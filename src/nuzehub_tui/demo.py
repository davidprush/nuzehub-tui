"""Deterministic demo desk: the same calls as ``NuzeHubClient``, answered in process (no network).

Used by ``nuzehub-tui --demo``, the snapshot tests and the visual check. Every value is fictional and marked
DEMO; there are no keys. The Wikipedia part keeps the web panel's rules: answers carry the status of the
library they came from, and a missing library answers ``ok: false`` with no rows.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

from nuzehub_tui.client import AccessDenied

DEMO_NOW_MS = 1_795_000_000_000  # fixed clock for snapshots
DESK_NOW_MS = 1795264200000  # 0.2.0: the demo Desk's fixed clock (2026-11-21 12:30 UTC), half an hour after the newest story

_ARTICLES = {
    "Saturn": ("Saturn is the sixth planet from the Sun.",
               "# Saturn\n\n**Saturn** is the sixth planet from the Sun and the second-largest planet in the Solar System. "
               "The Rings of Saturn are made mostly of ice. The Cassini probe orbited Saturn from 2004 to 2017.\n\n"
               "## Exploration\n\nThe Voyager program flew past Saturn in 1980 and 1981."),
    "Rings of Saturn": ("The rings of Saturn are the most extensive ring system of any planet.",
                        "# Rings of Saturn\n\nThe rings of Saturn are the most extensive ring system of any planet in the "
                        "Solar System. Saturn has seven named main rings. Cassini studied them closely."),
    "Cassini–Huygens": ("Cassini–Huygens was a space-research mission to Saturn.",
                        "# Cassini–Huygens\n\nCassini–Huygens was a NASA, ESA and ASI mission to Saturn and its moons. "
                        "It ended in 2017 with a dive into Saturn."),
    "Voyager program": ("The Voyager program is an American scientific program of two probes.",
                        "# Voyager program\n\nThe Voyager program launched two probes in 1977. Both flew past Saturn."),
    "Titan (moon)": ("Titan is the largest moon of Saturn.",
                     "# Titan (moon)\n\nTitan is the largest moon of Saturn. The Huygens probe from Cassini landed on it."),
}


def _wiki_url(title: str) -> str:
    from nuzehub_tui.desk import wiki_url

    return wiki_url(title)


DEMO_STATUS_ON = {
    "state": "on", "line": "on (6,170,000 articles, Server primary /usr/local/var/second-brain/wiki/wikipedia.sqlite, current)",
    "source": "primary", "sourceLabel": "Server primary", "path": "/usr/local/var/second-brain/wiki/wikipedia.sqlite",
    "articles": "6,170,000", "freshness": "current", "lastSync": "", "lastAnswer": "",
}


def demo_instance() -> dict[str, Any]:
    note: dict[str, Any] = {
        "attachmentId": None, "attachmentMime": "", "summary": "", "takeaway": "", "actions": [], "embeddedHash": "",
    }
    return {
        "rev": 7,
        "desk": {
            "version": 1,
            "prefs": {
                "sources": [
                    {"id": "s1", "name": "Demo World", "url": "https://demo.invalid/world.xml", "enabled": True},
                    {"id": "s2", "name": "Demo Space", "url": "https://demo.invalid/space.xml", "enabled": True},
                    {"id": "s3", "name": "Off feed", "url": "https://demo.invalid/off.xml", "enabled": False},
                ],
                "llmBaseUrl": "http://127.0.0.1:11434/v1",
            },
            "watchlist": ["NVDA", "AAPL", "MSFT"],
            # 0.2.0 Desk demo (fictional): tasks, calendar, brief, an automation notice and the price rule
            "tasks": [{"id": "t1", "title": "Read the Cassini ring paper (DEMO)", "recurrence": "once", "doneOn": None},
                      {"id": "t2", "title": "Check the Reykjanes aviation code", "recurrence": "daily", "doneOn": None},
                      {"id": "t3", "title": "Weekly market notes", "recurrence": "once", "doneOn": "2026-11-20T09:00:00.000Z"}],
            "events": [{"id": "e1", "title": "Desk review (DEMO)", "start": "2026-11-21T15:00:00.000Z",
                        "end": "2026-11-21T15:30:00.000Z", "allDay": False}],
            "brief": {"at": "2026-11-21T07:00:00.000Z", "text": "## Morning brief (DEMO)\n\n**Iceland** raised the volcano "
                      "alert near Reykjanes; flights continue. Chip makers lead a quiet session ahead of earnings. Cassini "
                      "data suggest Saturn's rings formed recently. The Atlantic storm season ends below average."},
            "automationNotices": [],
            "automations": [{"id": "a1", "name": "Price moves", "enabled": True,
                             "actions": [{"kind": "price-move", "thresholdPct": 1}]}],
        },
        "brain": {
            "notes": [
                {**note, "id": "n-1", "title": "Saturn reading list", "body": "Books and links about Saturn.\n\nStart with Cassini.",
                 "para": "projects", "tags": ["space"], "sourceKind": "text", "sourceTag": "quick", "url": "",
                 "createdAt": "2026-11-20T10:00:00.000Z", "updatedAt": "2026-11-20T10:00:00.000Z"},
                {**note, "id": "n-2", "title": "Market notes", "body": "NVDA earnings next week. Watch TSM.",
                 "para": "areas", "tags": ["markets"], "sourceKind": "text", "sourceTag": "quick", "url": "",
                 "createdAt": "2026-11-19T09:00:00.000Z", "updatedAt": "2026-11-19T09:00:00.000Z"},
                {**note, "id": "n-3", "title": "Trip ideas", "body": "Iceland in March? Check volcano activity first.",
                 "para": "inbox", "tags": [], "sourceKind": "text", "sourceTag": "quick", "url": "",
                 "createdAt": "2026-11-18T08:00:00.000Z", "updatedAt": "2026-11-18T08:00:00.000Z"},
            ],
            "prefs": {"temperature": 0.3},
        },
    }


def demo_stories() -> list[dict[str, Any]]:
    base = [
        ("Cassini data shows Saturn's rings are younger than thought", "space", "New analysis of Cassini measurements suggests the Rings of Saturn formed recently.", 0),
        ("Markets steady as chip makers report", "world", "NVDA and TSM lead a quiet session ahead of earnings.", 1),
        ("Volcano alert raised in Iceland", "world", "Authorities raised the aviation colour code near Reykjanes.", 2),
        ("Voyager program marks another year in interstellar space", "space", "Both probes still send data home.", 3),
        ("Storm season ends quietly in the Atlantic", "world", "Forecasters review a below-average season.", 4),
    ]
    out = []
    for i, (title, feed, summary, age) in enumerate(base):
        out.append({
            "id": f"st-{i}", "title": f"{title} (DEMO)", "url": f"https://demo.invalid/{feed}/{i}",
            "feedUrl": f"https://demo.invalid/{feed}.xml", "summary": summary,
            "publishedAt": f"2026-11-21T{12 - age:02d}:00:00.000Z",
        })
    return out


def demo_quotes(symbols: list[str], rng: str) -> list[dict[str, Any]]:
    seeds = {"NVDA": (182.4, 1.2), "AAPL": (231.1, -0.4), "MSFT": (512.9, 0.3),
             # 0.2.0: the Desk's MKT tape (fictional levels)
             "^GSPC": (6012.5, 0.42), "^DJI": (44120.0, -0.18), "^IXIC": (19650.3, 0.77), "^RUT": (2391.2, -1.05),
             "^TNX": (4.312, 0.9), "^VIX": (14.82, -3.1), "GC=F": (2688.4, 0.35), "BTC-USD": (97250.0, 2.4),
             "CL=F": (69.41, -0.62), "FPACEBOUS-USD-TR.FGI": (1520.7, 0.05)}
    out = []
    for s in symbols:
        price, pct = seeds.get(s, (100.0, 0.0))
        n = {"5d": 20, "1mo": 22, "6mo": 26}.get(rng, 22)
        pts = [{"t": DEMO_NOW_MS - (n - i) * 86_400_000, "close": round(price * (1 + ((i * 7 % 11) - 5) / 400), 2)} for i in range(n)]
        out.append({"symbol": s, "currency": "USD", "price": price, "change": round(price * pct / 100, 2), "changePct": pct,
                    "volume": 1_000_000, "points": pts, "name": f"{s} (DEMO)", "source": "demo", "fallback": False})
    return out


def demo_hazards(window: str, kinds: list[str]) -> list[dict[str, Any]]:
    events = {
        "quake": [{"id": "q1", "kind": "quake", "source": "usgs", "title": "M 5.8 - Kermadec Islands (DEMO)", "place": "Kermadec Islands",
                   "lat": -30.1, "lon": -178.2, "time": DEMO_NOW_MS - 3_600_000, "ongoing": False, "magnitude": 5.8, "magType": "mww",
                   "depthKm": 35.0, "severity": 2, "level": "GREEN", "url": "https://demo.invalid/q1"},
                  {"id": "q2", "kind": "quake", "source": "usgs", "title": "M 4.6 - Hokkaido (DEMO)", "place": "Hokkaido, Japan",
                   "lat": 42.9, "lon": 143.1, "time": DEMO_NOW_MS - 7_200_000, "ongoing": False, "magnitude": 4.6, "magType": "mb",
                   "depthKm": 60.0, "severity": 1, "level": "", "url": "https://demo.invalid/q2"}],
        "volcano": [{"id": "v1", "kind": "volcano", "source": "smithsonian", "title": "Reykjanes (DEMO)", "place": "Iceland",
                     "lat": 63.9, "lon": -22.4, "time": DEMO_NOW_MS - 86_400_000, "ongoing": True, "magnitude": None,
                     "severity": 2, "level": "ORANGE / WATCH", "url": "https://demo.invalid/v1"}],
        "storm": [],
    }
    return [{"kind": k, "events": events.get(k, []), "used": ["demo"], "skipped": [], "error": None} for k in kinds]


class DemoBackend:
    """Same method names and return shapes as ``NuzeHubClient``."""

    base_url = "demo"
    loopback = True
    desk_now_ms = DESK_NOW_MS

    def __init__(self, *, needs_key: bool = False, key: str = "demo-key") -> None:
        self._lock = threading.Lock()
        self.instance = demo_instance()
        self.needs_key = needs_key
        self._key = key
        self._unlocked = False
        self.wiki_state = "on"  # on | off | missing | mismatch | unavailable
        self.ollama_ok = True
        self.studio_ok = False
        self.calls: list[str] = []

    # access
    def _guard(self) -> None:
        if self.needs_key and not self._unlocked:
            raise AccessDenied("This session needs the host key. Type it in the key field and press Unlock.")

    def access_status(self) -> dict[str, Any]:
        self.calls.append("accessStatus")
        if not self.needs_key:
            return {"open": True, "remote": False, "busy": False}
        return {"open": self._unlocked, "remote": True, "busy": False}

    def unlock(self, key: str) -> dict[str, Any]:
        self.calls.append("unlockHost")
        if key.strip() == self._key:
            self._unlocked = True
            return {"open": True, "remote": True, "busy": False}
        return {"open": False, "remote": True, "busy": False, "error": "That key does not match."}

    # desk
    def load_instance(self) -> dict[str, Any]:
        self.calls.append("loadInstance")
        self._guard()
        with self._lock:
            return copy.deepcopy(self.instance)

    def save_instance(self, *, desk: Any = None, brain: Any = None, base_rev: int | None = None) -> dict[str, Any]:
        self.calls.append("saveInstance")
        self._guard()
        with self._lock:
            rev = int(self.instance.get("rev") or 0)
            if base_rev is not None and base_rev != rev:
                return {"ok": False, "conflict": True, "rev": rev, "desk": copy.deepcopy(self.instance["desk"]),
                        "brain": copy.deepcopy(self.instance["brain"])}
            if desk is not None:
                self.instance["desk"] = copy.deepcopy(desk)
            if brain is not None:
                self.instance["brain"] = copy.deepcopy(brain)
            self.instance["rev"] = rev + 1
            return {"ok": True, "rev": rev + 1}

    def fetch_news(self, urls: list[str]) -> dict[str, Any]:
        self.calls.append("fetchNews")
        self._guard()
        return {"stories": [s for s in demo_stories() if s["feedUrl"] in urls], "errors": []}

    def fetch_article(self, url: str) -> dict[str, Any]:
        self.calls.append("fetchArticle")
        self._guard()
        story = next((s for s in demo_stories() if s["url"] == url), None)
        text = f"{story['summary']}\n\nThis is a fictional demo article. Nothing was fetched." if story else ""
        return {"text": text, "access": "open" if story else "unavailable"}

    def get_markets(self, symbols: list[str], rng: str, sources: list[str] | None = None) -> dict[str, Any]:
        self.calls.append("getMarkets")
        self._guard()
        return {"quotes": demo_quotes(symbols, rng)}

    def search_symbols(self, query: str) -> dict[str, Any]:
        self.calls.append("searchSymbols")
        self._guard()
        q = query.strip().upper()
        hits = [{"symbol": s, "name": f"{s} (DEMO)", "kind": "Equity", "exchange": "DEMO"} for s in ("NVDA", "AAPL", "MSFT", "TSM") if q and q in s]
        return {"hits": hits}

    def get_hazards(self, window: str, kinds: list[str] | None = None) -> dict[str, Any]:
        self.calls.append("getHazards")
        self._guard()
        return {"at": DEMO_NOW_MS, "window": window, "results": demo_hazards(window, kinds or ["quake", "volcano", "storm"])}

    # wiki
    def _status(self) -> dict[str, Any]:
        st = dict(DEMO_STATUS_ON)
        if self.wiki_state == "off":
            st.update(state="off", line="off (no library at /usr/local/var/second-brain/wiki/wikipedia.sqlite)", articles="")
        elif self.wiki_state == "missing":
            st.update(state="off", line="missing: no library at /usr/local/var/second-brain/wiki/wikipedia.sqlite", articles="")
        elif self.wiki_state == "unavailable":
            st.update(state="unavailable", line="brain wiki status did not answer in time.", source="unknown", sourceLabel="unknown", path="")
        return st

    def _answer_status(self) -> dict[str, Any]:
        st = self._status()
        if self.wiki_state == "mismatch":
            st.update(path="/usr/local/var/second-brain/wiki/wikipedia.sqlite", sourceLabel="local default")
        return st

    def _fail(self) -> dict[str, Any] | None:
        if self.wiki_state in ("off", "missing", "unavailable"):
            return {"ok": False, "reason": "unavailable", "message": self._status()["line"], "status": self._status()}
        return None

    def wiki_status(self) -> dict[str, Any]:
        self.calls.append("wikiPanelStatus")
        self._guard()
        return self._status()

    def _hits(self, query: str, k: int) -> list[dict[str, Any]]:
        words = [w for w in query.lower().replace("'s", "").split() if w]
        rows: list[dict[str, Any]] = []
        for title, (abstract, text) in _ARTICLES.items():
            hay = f"{title} {text}".lower()
            if words and all(w in hay for w in words):
                rows.append({"rank": len(rows) + 1, "title": title, "url": _wiki_url(title),
                             "snip": abstract, "abstract": abstract, "textLen": len(text)})
        rows.sort(key=lambda r: (0 if all(w in str(r["title"]).lower() for w in words) else 1, int(r["rank"])))
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return rows[:k]

    def wiki_search(self, query: str, k: int = 10) -> dict[str, Any]:
        self.calls.append("wikiPanelSearch")
        self._guard()
        if not query.strip():
            return {"ok": False, "reason": "bad-query", "message": "Type something to search for."}
        fail = self._fail()
        if fail:
            return fail
        return {"ok": True, "query": query.strip(), "results": self._hits(query, k), "status": self._answer_status()}

    def wiki_read(self, title: str) -> dict[str, Any]:
        self.calls.append("wikiPanelRead")
        self._guard()
        fail = self._fail()
        if fail:
            return fail
        found = _ARTICLES.get(title)
        if not found:
            return {"ok": False, "reason": "not-found", "message": f"No article titled “{title}” in the library."}
        abstract, text = found
        links = [{"phrase": t, "title": t} for t in _ARTICLES if t != title and t.split(" (")[0].split("–")[0] in text]
        return {"ok": True, "article": {"title": title, "url": _wiki_url(title), "abstract": abstract, "text": text,
                                        "dateCreated": "2001-01-01", "truncated": False},
                "links": links, "status": self._answer_status()}

    def wiki_related(self, title: str, text: str = "") -> dict[str, Any]:
        self.calls.append("wikiPanelRelated")
        self._guard()
        fail = self._fail()
        if fail:
            return fail
        seen: dict[str, dict[str, Any]] = {}
        for word in ("Saturn", "Cassini", "Voyager", "Titan"):
            if word.lower() in f"{title} {text}".lower():
                for row in self._hits(word, 4):
                    seen.setdefault(row["title"], {**row, "via": word})
        if not seen:
            return {"ok": False, "reason": "bad-query", "message": "Nothing to look up in that item."}
        rows = list(seen.values())
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return {"ok": True, "queries": [title], "results": rows, "status": self._answer_status()}

    # models
    def probe_engines(self) -> dict[str, Any]:
        self.calls.append("probeEngines")
        return {"ollama": {"ok": self.ollama_ok, "models": ["qwen3.5:9b", "nomic-embed-text"] if self.ollama_ok else []},
                "studio": {"ok": self.studio_ok, "models": ["qwen3.5-9b"] if self.studio_ok else []}, "savedOk": None}

    def model_status(self) -> dict[str, Any] | None:
        self.calls.append("model-status")
        return {"ollama": {"url": "http://127.0.0.1:11434/api/tags", "ok": self.ollama_ok, "count": 2 if self.ollama_ok else 0},
                "lmstudio": None if self.ollama_ok else {"url": "http://127.0.0.1:1234/v1/models", "ok": self.studio_ok,
                                                         "count": 1 if self.studio_ok else 0}}
