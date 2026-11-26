"""0.2.0 Desk: the OPS desk's panel logic as pure functions (no Textual). Ported from the web desk
(components/hud/ops-panels.tsx, panel.tsx, hazard-ui.tsx, lib/desk/time.ts, notices.ts, automate.tsx, exchanges.ts
and globe-prefs.ts). Read-only: the only write is Focus 25m/50m (``start_focus``), saved by the app with a
saveInstance merge.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

from nuzehub_tui import rank

MARKET_TAPE: tuple[tuple[str, str], ...] = (
    ("^GSPC", "S&P 500"), ("^DJI", "Dow 30"), ("^IXIC", "Nasdaq"), ("^RUT", "Russell 2000"), ("^TNX", "10-Year Bond"),
    ("^VIX", "VIX"), ("GC=F", "Gold"), ("BTC-USD", "Bitcoin USD"), ("CL=F", "Crude Oil"),
    ("FPACEBOUS-USD-TR.FGI", "US Private Equity"),
)
TAPE_SYMBOLS = [s for s, _ in MARKET_TAPE]
DEFAULT_WATCHLIST = ("NVDA", "AAPL", "MSFT", "GOOG", "AMZN", "TSM", "SPCX", "2222.SR", "META", "AVGO")
# globe-prefs.ts GLOBE_LAYERS and their defaults; Alt+1..Alt+8 toggle them in this order (brief §9 Q5)
LAYERS: tuple[tuple[str, str], ...] = (
    ("heat", "News heat"), ("points", "Story points"), ("rings", "Breaking"), ("arcs", "Links"), ("pins", "Pins"),
    ("exchanges", "Exchanges"), ("terminator", "Day / night"), ("graticule", "Graticule"),
)
LAYER_DEFAULTS = {"heat": True, "points": True, "rings": True, "arcs": True, "pins": True, "exchanges": False,
                  "terminator": True, "graticule": False}
SEVERITY_ROLE = ("muted", "accent", "warning", "error")  # hazard-ui SEVERITY_TONE
SEVERITY_LABEL = ("Info", "Minor", "Moderate", "Major")
PRICE_RULE = ("Price moves", 2.0)  # the web's default "Price moves" template rule
QUIET = "Quiet. Rules on Automate post here."


def js_round(x: float) -> int:
    """``Math.round`` (halves go up)."""
    return math.floor(x + 0.5)


def age_label(at: Any, now_ms: float) -> str:
    """panel.tsx ``ageLabel``: now / 12m / 5h / 3d; empty when the time cannot be read."""
    if at is None:
        return ""
    ms = float(at) if isinstance(at, int | float) else rank.parse_ms(at)
    if not math.isfinite(ms):
        return ""
    minutes = max(0.0, (now_ms - ms) / 60000)
    if minutes < 1:
        return "now"
    if minutes < 60:
        return f"{js_round(minutes)}m"
    if minutes < 60 * 48:
        return f"{js_round(minutes / 60)}h"
    return f"{js_round(minutes / 1440)}d"


def price_text(price: Any) -> str:
    """ops-panels ``priceText``: 0 decimals from 1,000, 2 from 10, else 3; grouped."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(p):
        return "—"
    digits = 0 if abs(p) >= 1000 else 2 if abs(p) >= 10 else 3
    return f"{p:,.{digits}f}"


def pct(n: Any) -> str:
    """time.ts ``pct``: "+1.20%" (a plus only above zero)."""
    v = float(n or 0)
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def local(now_ms: float) -> datetime:
    return datetime.fromtimestamp(now_ms / 1000)


def greeting(now_ms: float, name: str = "") -> str:
    h = local(now_ms).hour
    word = "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"
    return f"{word}{', ' + name if name else ''}."


def sitrep_date(now_ms: float) -> str:
    d = local(now_ms)
    return f"{d:%a}, {d:%b} {d.day}"


def day_key(d: datetime) -> str:
    return f"{d.year}-{d.month:02d}-{d.day:02d}"


def week_key(d: datetime) -> str:
    js_day = (d.weekday() + 1) % 7  # JS getDay: Sunday 0
    offset = -6 if js_day == 0 else 1 - js_day
    return day_key(d + timedelta(days=offset))


def is_task_done(task: dict, now_ms: float) -> bool:
    done_on = task.get("doneOn")
    if not done_on:
        return False
    if task.get("recurrence") == "once":
        return True
    ms = rank.parse_ms(done_on)
    if not math.isfinite(ms):
        return False
    done, now = local(ms), local(now_ms)
    if task.get("recurrence") == "daily":
        return day_key(done) == day_key(now)
    return week_key(done) == week_key(now)


def brief_text(brief: Any) -> str:
    text = brief.get("text") if isinstance(brief, dict) else None
    if not isinstance(text, str):
        return ""
    return re.sub(r"\n+", " ", re.sub(r"[#*_>`]", "", text)).strip()


def desk_of(instance: dict) -> dict:
    d = instance.get("desk") if isinstance(instance, dict) else None
    return d if isinstance(d, dict) else {}


def prefs_of(instance: dict) -> dict:
    p = desk_of(instance).get("prefs")
    return p if isinstance(p, dict) else {}


def _items(instance: dict, key: str) -> list:
    v = desk_of(instance).get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def ranked_stories(instance: dict, stories: list[dict], now_ms: float) -> list[dict]:
    """SITREP / INTEL use ``rankStories(stories, prefs, "7", now, newsVotes)``."""
    return rank.rank_stories(stories, prefs_of(instance), "7", now_ms, _items(instance, "newsVotes"))


def map_data(instance: dict, stories: list[dict], now_ms: float) -> rank.MapData:
    return rank.compute_map_data(stories, _items(instance, "savedLinks"), _items(instance, "mapPlacements"),
                                 _items(instance, "mapArchive"), False, now_ms)


def sitrep(instance: dict, ranked: list[dict], mdata: rank.MapData, now_ms: float) -> dict[str, Any]:
    breaking = sum(len(loc["articles"]) for loc in mdata.locations if loc["freshest"] is not None and loc["freshest"] < 120)
    tasks = _items(instance, "tasks")
    open_n = sum(1 for t in tasks if not is_task_done(t, now_ms))
    brief = desk_of(instance).get("brief")
    return {"stories": len(ranked), "geo": len(mdata.ranked), "breaking": breaking, "tasks": open_n,
            "brief": brief_text(brief), "brief_at": brief.get("at") if isinstance(brief, dict) else None,
            "world": rank.geopolitical_stories(ranked)[:4], "name": str(prefs_of(instance).get("displayName") or "")}


def world_row(index: int, story: dict, mdata: rank.MapData) -> tuple[str, str, str]:
    """("01", title, "UA · FX world") for a world-developments row."""
    country = rank.country_by_id(mdata.country_for_url.get(story.get("url", "")))
    meta = " · ".join(x for x in ((country.iso2 if country else ""), story.get("sourceName", "")) if x)
    return f"{index + 1:02d}", str(story.get("title", "")), meta


def flat_hazards(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    for res in results or []:
        out += [e for e in (res.get("events") or []) if isinstance(e, dict)]
    return out


def mag_label(e: dict) -> str:
    mag = e.get("magnitude")
    if e.get("kind") == "quake":
        return f"M{float(mag):.1f}" if mag is not None else "M?"
    if e.get("kind") == "storm":
        return f"{js_round(float(mag))} kt" if mag is not None else "—"
    level = str(e.get("level") or "").split(" / ")[0]
    sev = int(e.get("severity") or 0)
    return level or SEVERITY_LABEL[max(0, min(3, sev))]


def hazard_line(events: list[dict]) -> dict[str, Any]:
    top = sorted(events, key=lambda e: (-(e.get("severity") or 0), -(e.get("magnitude") or 0)))[:1]
    storms = sum(1 for e in events if e.get("kind") == "storm" and e.get("ongoing"))
    quakes = sum(1 for e in events if e.get("kind") == "quake" and (e.get("magnitude") or 0) >= 5)
    out: dict[str, Any] = {"digest": f"{quakes} M5+ · {storms} storms", "top": None}
    if top:
        e = top[0]
        sev = max(0, min(3, int(e.get("severity") or 0)))
        out["top"] = {"label": mag_label(e), "role": SEVERITY_ROLE[sev],
                      "text": (e.get("place") or e.get("title")) if e.get("kind") == "quake" else e.get("title")}
    return out


# ---- alerts ------------------------------------------------------------------------------------------------------


def live_notices(notices: list[dict], cleared_at: Any) -> list[dict]:
    """notices.ts ``liveNotices``: only notices newer than the last clear."""
    cut = rank.parse_ms(cleared_at) if isinstance(cleared_at, str) else float(cleared_at) if cleared_at else -math.inf
    if not math.isfinite(cut):
        cut = -math.inf

    def at(n: dict) -> float:
        v = n.get("at")
        return float(v) if isinstance(v, int | float) else rank.parse_ms(v)

    return [n for n in notices if at(n) > cut]


def price_rule(instance: dict) -> tuple[str, float]:
    """Name and threshold of the first enabled automation with a price-move action (automate.tsx cleanAction:
    a number above 0, else 2, at most 100); the web's default rule when there is none. Read-only."""
    for rule in _items(instance, "automations"):
        if rule.get("enabled") is False:
            continue
        for action in rule.get("actions") or []:
            if isinstance(action, dict) and action.get("kind") == "price-move":
                raw = action.get("thresholdPct")
                th = float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) and raw > 0 else 2.0
                return str(rule.get("name") or PRICE_RULE[0]), min(100.0, th)
    return PRICE_RULE


def price_alerts(instance: dict, quotes: list[dict], quotes_at: float | None, stale: bool) -> list[dict]:
    """Brief §9 Q6: the web's price-move rule, run on the TUI's own watchlist quotes. One alert at most:
    ``PRICE MOVES  NVDA +30.09%, AAPL -2.10%``. Nothing for an empty watchlist, stale quotes, or when the notices were
    cleared after these quotes arrived."""
    if stale or not quotes or quotes_at is None:
        return []
    cleared = desk_of(instance).get("automationNoticesClearedAt")
    if live_notices([{"at": quotes_at}], cleared) == []:
        return []
    name, threshold = price_rule(instance)
    moved = [q for q in quotes if not q.get("error") and abs(float(q.get("changePct") or 0)) >= threshold]
    if not moved:
        return []
    body = ", ".join(f"{q.get('symbol')} {pct(q.get('changePct'))}" for q in moved)
    return [{"id": "tui-price-move", "at": quotes_at, "tag": name, "text": body}]


def alert_items(instance: dict, stories: list[dict], mdata: rank.MapData, now_ms: float,
                price: list[dict] | None = None) -> list[dict]:
    notices = live_notices(_items(instance, "automationNotices"),
                           desk_of(instance).get("automationNoticesClearedAt"))[:8]
    items = list(price or []) + [{"id": n.get("id"), "at": n.get("at"), "tag": n.get("title", ""), "text": n.get("body", "")}
                                 for n in notices]
    if items:
        return items
    fresh = [s for s in stories if s.get("publishedAt") and now_ms - rank.parse_ms(s["publishedAt"]) < 2 * 3600_000][:6]
    out = []
    for s in fresh:
        country = rank.country_by_id(mdata.country_for_url.get(s.get("url", "")))
        out.append({"id": s.get("id"), "at": s.get("publishedAt"), "tag": country.name if country else "Breaking",
                    "text": s.get("title", "")})
    return out


def hhmm(at: Any) -> str:
    ms = float(at) if isinstance(at, int | float) else rank.parse_ms(at)
    return f"{local(ms):%H:%M}" if math.isfinite(ms) else "--:--"


# ---- markets -----------------------------------------------------------------------------------------------------


def watch_rows(quotes: list[dict]) -> list[dict]:
    """WatchPanel: live quotes (no error), with the last 30 closes for the spark; up when changePct >= 0."""
    rows = []
    for q in quotes:
        if q.get("error"):
            continue
        closes = [p.get("close") for p in (q.get("points") or []) if isinstance(p, dict) and p.get("close") is not None][-30:]
        cp = float(q.get("changePct") or 0)
        rows.append({"symbol": q.get("symbol"), "price": price_text(q.get("price")), "pct": pct(cp), "up": cp >= 0,
                     "closes": closes})
    return rows


def tape_items(tape: list[dict], watch: list[dict]) -> list[dict]:
    """MarketTape items: MARKET_TAPE quotes (without error) plus watchlist quotes not already there, sorted by the
    biggest move first (largest abs(changePct), ties by symbol) so the largest gainers and drops show at offset 0
    (David, Nov 23: the tape moves only when the user steps it)."""
    labels = dict(MARKET_TAPE)
    by = {q.get("symbol"): q for q in tape if not q.get("error")}
    items = [by[s] for s in TAPE_SYMBOLS if s in by]
    seen = {q.get("symbol") for q in items}
    items += [q for q in watch if not q.get("error") and q.get("symbol") not in seen]
    items.sort(key=lambda q: (-abs(float(q.get("changePct") or 0)), str(q.get("symbol"))))
    out = []
    for q in items:
        ch = float(q.get("change") or 0)
        out.append({"label": labels.get(str(q.get("symbol")), q.get("symbol")), "price": price_text(q.get("price")),
                    "pct": f"{abs(float(q.get('changePct') or 0)):.2f}%", "up": ch >= 0})
    return out


# ---- day dock ----------------------------------------------------------------------------------------------------


def _same_day(iso: Any, now_ms: float) -> bool:
    ms = rank.parse_ms(iso)
    return math.isfinite(ms) and day_key(local(ms)) == day_key(local(now_ms))


def next_event(instance: dict, now_ms: float) -> dict | None:
    events = []
    for e in _items(instance, "events"):
        end = rank.parse_ms(e.get("end") or e.get("start"))
        if (math.isfinite(end) and end >= now_ms - 3600_000) or _same_day(e.get("start"), now_ms):
            events.append(e)
    events.sort(key=lambda e: rank.parse_ms(e.get("start")))
    if not events:
        return None
    e = events[0]
    start = rank.parse_ms(e.get("start"))
    if _same_day(e.get("start"), now_ms):
        when = "All day" if e.get("allDay") else f"{local(start):%-I:%M %p}" if math.isfinite(start) else ""
    else:
        when = f"{local(start):%b} {local(start).day}" if math.isfinite(start) else ""
    return {"when": when, "title": str(e.get("title", ""))}


def tasks_summary(instance: dict, now_ms: float) -> dict[str, Any]:
    tasks = _items(instance, "tasks")
    done = [t for t in tasks if is_task_done(t, now_ms)]
    open_ = [t for t in tasks if not is_task_done(t, now_ms)]
    return {"done": len(done), "total": len(tasks), "first": str(open_[0].get("title", "")) if open_ else "All clear"}


FOCUS_TOTAL_MS = 25 * 60000


def focus_left(instance: dict, now_ms: float) -> float | None:
    focus = desk_of(instance).get("focus")
    if not isinstance(focus, dict) or not isinstance(focus.get("endsAt"), int | float):
        return None
    left = float(focus["endsAt"]) - now_ms
    return left if left > 0 else None


def focus_text(left: float) -> str:
    return f"{int(left // 60000)}:{int((left % 60000) // 1000):02d}"


def start_focus(minutes: int, now_ms: float) -> dict[str, Any]:
    """store.ts ``startFocus``: the only Desk write, merged into the saved desk by the app."""
    return {"taskId": None, "label": "Focus", "endsAt": int(now_ms + minutes * 60000)}


def bar(fraction: float, width: int, ascii_only: bool = False) -> tuple[str, str]:
    """(filled, rest) cells of a 1-row progress bar."""
    n = max(0, min(width, js_round(max(0.0, min(1.0, fraction)) * width)))
    return ("#" if ascii_only else "━") * n, ("-" if ascii_only else "─") * (width - n)


def feeds_chip(instance: dict, feed_errors: list[dict]) -> tuple[int, int]:
    """(feeds answering, enabled feeds) for the FEEDS status chip."""
    sources = [s for s in (prefs_of(instance).get("sources") or []) if isinstance(s, dict) and s.get("enabled", True)]
    failed = {e.get("url") or e.get("feedUrl") for e in feed_errors if isinstance(e, dict)}
    return sum(1 for s in sources if s.get("url") not in failed), len(sources)
