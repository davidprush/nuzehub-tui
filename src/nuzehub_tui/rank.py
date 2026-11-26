"""0.2.0 Desk: exact ports of the web desk's ``rankStories`` / ``geopoliticalStories`` (src/lib/desk/rank.ts),
``norm`` / ``detectCountries`` / ``countriesFor`` / ``articleFrom`` (places.ts), ``computeMapData`` / ``heatLevel``
(map-data.tsx) and the gazetteer (gazetteer.ts). Brief §9 Q1: the tests compare these with fixtures produced by the
TS functions themselves (tests/fixtures/desk-ts-fixtures.json).

Port notes: JS ``Array.sort`` is stable, so is ``sorted``; ``localeCompare`` is approximated by ``locale_key`` (ICU
root order: separators, then punctuation, then digits, then letters with accents and case as later tie-breaks); the JS
regexes ``\\b`` are ASCII, so the Python ones use ``re.ASCII``.
"""

from __future__ import annotations

import functools
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib import resources
from typing import Any
from urllib.parse import urlsplit

# ---- gazetteer.ts -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Country:
    id: str
    iso2: str
    name: str
    lat: float
    lon: float
    aliases: tuple[str, ...] = ()


def _load(name: str) -> Any:
    return json.loads(resources.files("nuzehub_tui").joinpath("data", name).read_text(encoding="utf-8"))


COUNTRIES: list[Country] = [Country(r[0], r[1], r[2], float(r[3]), float(r[4]), tuple(r[5])) for r in _load("countries.json")]
_BY_ID = {c.id: c for c in COUNTRIES}


def country_by_id(cid: str | None) -> Country | None:
    if not cid:
        return None
    return _BY_ID.get(str(cid).rjust(3, "0")) or _BY_ID.get(str(cid))


# ---- JS helpers -------------------------------------------------------------------------------------------------


def parse_ms(value: Any) -> float:
    """``Date.parse`` for the shapes the desk sees: ISO 8601 (date-only is UTC, a time without zone is local) and
    RFC 2822. Returns NaN when it cannot be read."""
    if not isinstance(value, str) or not value.strip():
        return math.nan
    s = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.astimezone()).timestamp() * 1000
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s).timestamp() * 1000
    except (TypeError, ValueError, IndexError):
        return math.nan


def _char_class(ch: str) -> int:
    if ch.isspace():
        return 0
    if ch.isdigit():
        return 2
    if ch.isalpha():
        return 3
    return 1


def locale_key(text: str) -> tuple:
    """Sort key that follows ``String.prototype.localeCompare`` (ICU root collation) closely enough for titles,
    country names and ISO dates: primary = base letters (accents and case ignored), then accents, then lower before
    upper case."""
    base, accents, case = [], [], []
    for ch in str(text):
        decomposed = unicodedata.normalize("NFD", ch)
        root = decomposed[0]
        base.append((_char_class(root), root.casefold()))
        accents.append(len(decomposed) - 1)
        case.append(1 if root.isupper() else 0)
    return (tuple(base), tuple(accents), tuple(case))


def locale_compare(a: str, b: str) -> int:
    ka, kb = locale_key(a), locale_key(b)
    return (ka > kb) - (ka < kb)


def _host_of(url: str) -> str:
    try:
        host = urlsplit(str(url)).hostname or ""
    except ValueError:
        return ""
    return re.sub(r"^www\.", "", host).lower()


# ---- rank.ts ----------------------------------------------------------------------------------------------------

STOP = frozenset("""about after again also amid and are been before being but can could did does for from had has have
her his how into its just more most new not now off one our out over said say says she than that the their them then
there they this was were what when where which while who will with would you your""".split())

_TOKEN = re.compile(r"[a-z][a-z0-9'+-]{3,}")


def _js_lower(text: str) -> str:
    return str(text).lower()


def tokens_of(text: str) -> list[str]:
    words = _TOKEN.findall(_js_lower(text))
    return list(dict.fromkeys(w for w in words if w not in STOP))


def _blob(story: dict) -> str:
    return _js_lower(f"{story.get('title', '')} {story.get('summary', '')}")


def _taste_maps(votes: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    liked: dict[str, int] = {}
    disliked: dict[str, int] = {}
    for vote in votes:
        bag = liked if vote.get("vote") == 1 else disliked
        for token in tokens_of(f"{vote.get('title', '')} {vote.get('summary', '')}"):
            bag[token] = bag.get(token, 0) + 1
    return liked, disliked


def _taste_for(tokens: list[str], vote: dict | None, liked: dict[str, int], disliked: dict[str, int]) -> float:
    if not tokens or (not liked and not disliked):
        return 0
    own = set(tokens_of(f"{vote.get('title', '')} {vote.get('summary', '')}")) if vote else set()
    up = down = hit = 0
    for token in tokens:
        like = liked.get(token, 0)
        dislike = disliked.get(token, 0)
        if token in own and vote:
            if vote.get("vote") == 1:
                like = max(0, like - 1)
            else:
                dislike = max(0, dislike - 1)
        if not like and not dislike:
            continue
        hit += 1
        up += like
        down += dislike
    if not hit:
        return 0
    return max(-6, min(6, ((up - down) / hit) * 2.5))


def _list(prefs: dict, key: str) -> list:
    value = prefs.get(key) if isinstance(prefs, dict) else None
    return value if isinstance(value, list) else []


def rank_stories(stories: list[dict], prefs: dict, window: str = "7", now: float | None = None,
                 votes: list[dict] | None = None) -> list[dict]:
    """``rankStories``: drop blocked hosts / keywords / concerns and stories older than the window, score topics,
    boost words, freshness (< 12 h) and taste; sort by score, then newer ``publishedAt`` string first."""
    import time

    now = time.time() * 1000 if now is None else now
    votes = votes or []
    blocks = [str(k).lower() for k in _list(prefs, "blockKeywords") if str(k).lower()]
    concerns = [str(k).lower() for k in _list(prefs, "concerns") if str(k).lower()]
    hosts = [re.sub(r"^www\.", "", str(h).lower()) for h in _list(prefs, "blockedHosts")]
    hosts = [h for h in hosts if h]
    names = {s.get("url"): s.get("name") for s in _list(prefs, "sources") if isinstance(s, dict)}
    max_age = math.inf if window == "all" else float(window) * 864e5
    by_url = {v.get("url"): v for v in votes}
    liked, disliked = _taste_maps(votes)
    ranked: list[dict] = []
    for story in stories:
        host = _host_of(str(story.get("url", "")))
        if any(host == b or host.endswith(f".{b}") for b in hosts):
            continue
        blob = _blob(story)
        if any(k in blob for k in blocks) or any(k in blob for k in concerns):
            continue
        published = story.get("publishedAt")
        if published and max_age < math.inf:
            t = parse_ms(published)
            if math.isfinite(t) and now - t > max_age:
                continue
        if not published and window == "1":
            continue
        score: float = 1
        hits: list[str] = []
        for topic in _list(prefs, "topics"):
            words = [w for w in re.split(r"\s+", _js_lower(topic.get("name", ""))) if len(w) > 2]
            if not words:
                continue
            matched = [w for w in words if w in blob]
            if len(matched) == len(words) or len(matched) >= 1:
                score += min(10, max(1, topic.get("weight", 0))) * (len(matched) / len(words))
                hits.append(topic.get("name"))
        for keyword in _list(prefs, "boostKeywords"):
            k = _js_lower(keyword)
            if k and k in blob:
                score += 2
                hits.append(keyword)
        if published:
            age = now - parse_ms(published)
            if math.isfinite(age) and age < 12 * 36e5:
                score += 0.6
        taste = _taste_for(tokens_of(f"{story.get('title', '')} {story.get('summary', '')}"), by_url.get(story.get("url")),
                           liked, disliked)
        score += taste
        feed = str(story.get("feedUrl", ""))
        ranked.append({**story, "score": score, "taste": taste, "hits": list(dict.fromkeys(hits)),
                       "sourceName": names[feed] if feed in names and names[feed] is not None else _host_of(feed)})

    def cmp(a: dict, b: dict) -> int:
        d = b["score"] - a["score"]
        if d:
            return -1 if d < 0 else 1
        return locale_compare(_js_string(b.get("publishedAt")), _js_string(a.get("publishedAt")))

    return sorted(ranked, key=functools.cmp_to_key(cmp))


def _js_string(value: Any) -> str:
    return "undefined" if value is None else str(value)


GEO_TERMS = ("war", "wars", "sanction", "sanctions", "nato", "election", "elections", "diplomat", "diplomacy", "border",
             "missile", "missiles", "ceasefire", "treaty", "invasion", "ukraine", "gaza", "taiwan", "nuclear", "military",
             "conflict", "summit", "troops", "embargo", "coup", "airstrike", "airstrikes")
_GEO = [re.compile(rf"\b{t}\b", re.IGNORECASE | re.ASCII) for t in GEO_TERMS]


def geopolitical_stories(stories: list[dict]) -> list[dict]:
    out = []
    for story in stories:
        blob = f"{story.get('title', '')} {story.get('summary', '')}"
        if any(rx.search(blob) for rx in _GEO):
            out.append(story)
    return out


# ---- places.ts --------------------------------------------------------------------------------------------------


def norm(value: str) -> str:
    s = unicodedata.normalize("NFD", _js_lower(value))
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("M"))
    s = re.sub(r"['\u2019]", "", s)
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _keep_phrase(phrase: str) -> bool:
    if not phrase:
        return False
    return len(phrase) >= 4 or phrase in ("uk", "usa", "uae", "drc", "prc")


def _aliases() -> list[tuple[Country, str, re.Pattern[str]]]:
    rows: list[tuple[Country, str]] = []
    for country in COUNTRIES:
        phrases = dict.fromkeys(p for p in [norm(country.name), *map(norm, country.aliases)] if _keep_phrase(p))
        rows += [(country, phrase) for phrase in phrases]
    rows.sort(key=lambda row: -len(row[1]))
    return [(c, p, re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE | re.ASCII)) for c, p in rows]


ALIASES = _aliases()
_GEORGIA = re.compile(r"tbilisi|caucasus|abkhazia|ossetia|sakartvelo|republic of georgia|\bgeorgian\b", re.ASCII)


def detect_countries(title: str, text: str) -> list[Country]:
    title_n = norm(title)
    body_n = norm(f"{title} {text}")
    if not body_n:
        return []
    hits: list[tuple[Country, int, int, bool]] = []
    for country, phrase, rx in ALIASES:
        in_title = bool(rx.search(title_n))
        found = rx.search(body_n)
        if not found:
            continue
        hits.append((country, found.start(), len(phrase), in_title))
    kept = [h for i, h in enumerate(hits)
            if not any(j != i and o[2] > h[2] and h[1] >= o[1] and h[1] + h[2] <= o[1] + o[2] for j, o in enumerate(hits))]
    scored: dict[str, tuple[Country, int]] = {}
    for country, _index, length, in_title in kept:
        score = length + (24 if in_title else 0)
        prev = scored.get(country.id)
        if prev is None or score > prev[1]:
            scored[country.id] = (country, score)
    found_list = [c for c, _s in sorted(scored.values(), key=lambda item: -item[1])]
    blob = body_n
    if not _GEORGIA.search(blob):
        found_list = [c for c in found_list if c.iso2 != "GE"]
    north = bool(re.search(r"north korea|dprk|pyongyang", blob))
    south = bool(re.search(r"south korea|seoul", blob))
    if north and not south:
        found_list = [c for c in found_list if c.iso2 != "KR"]
    if south and not north:
        found_list = [c for c in found_list if c.iso2 != "KP"]
    if not north and not south and any(c.iso2 == "KR" for c in found_list):
        found_list = [c for c in found_list if c.iso2 != "KP"]
    return found_list[:3]


def countries_for(item: dict, placement_id: str | None = None) -> list[Country]:
    if placement_id:
        forced = country_by_id(placement_id)
        return [forced] if forced else []
    return detect_countries(item.get("title", ""), item.get("text", ""))


def article_from(item: dict, country: Country) -> dict:
    return {"url": item["url"], "title": str(item.get("title", ""))[:240], "countryId": country.id, "lon": country.lon,
            "lat": country.lat, "source": str(item.get("source", ""))[:120]}


# ---- map-data.tsx -----------------------------------------------------------------------------------------------


def link_kind_label(kind: str) -> str:
    return {"youtube": "YouTube", "rumble": "Rumble", "x": "X post", "social": "Social post"}.get(kind, "Article")


@dataclass
class MapData:
    displayed: list[dict] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    ranked: list[tuple[Country, int]] = field(default_factory=list)
    max_count: int = 0
    locations: list[dict] = field(default_factory=list)
    arcs: list[dict] = field(default_factory=list)
    placement_for: dict[str, str] = field(default_factory=dict)
    country_for_url: dict[str, str] = field(default_factory=dict)
    published_at: dict[str, float] = field(default_factory=dict)


def _to_fixed2(value: float) -> str:
    return f"{value:.2f}"


def compute_map_data(stories: list[dict], links: list[dict] | None = None, placements: list[dict] | None = None,
                     archive: list[dict] | None = None, picture: bool = False, now: float | None = None) -> MapData:
    import time

    now = time.time() * 1000 if now is None else now
    links, placements, archive = links or [], placements or [], archive or []
    placement_for = {p["url"]: p["countryId"] for p in placements}
    published_at: dict[str, float] = {}
    for story in stories:
        at = parse_ms(story.get("publishedAt")) if story.get("publishedAt") else math.nan
        if math.isfinite(at):
            published_at[story.get("url", "")] = at
    items = [{"url": s.get("url", ""), "title": s.get("title", ""), "text": s.get("summary", ""),
              "source": _host_of_keep_case(s.get("url", ""))} for s in stories]
    items += [{"url": lk.get("url", ""), "title": lk.get("title", ""), "text": f"{lk.get('note', '')} {lk.get('author', '')}",
               "source": link_kind_label(lk.get("kind", ""))} for lk in links]
    articles: list[dict] = []
    extras: list[dict] = []
    seen: set[str] = set()
    country_for_url: dict[str, str] = {}
    for item in items:
        if not item["url"] or item["url"] in seen:
            continue
        seen.add(item["url"])
        countries = countries_for(item, placement_for.get(item["url"]))
        if not countries:
            continue
        primary = countries[0]
        country_for_url[item["url"]] = primary.id
        articles.append(article_from(item, primary))
        extras += [{"url": item["url"], "countryId": c.id} for c in countries[1:]]
    if picture:
        displayed = list(archive)
    else:
        live = {a["url"] for a in articles}
        displayed = [*articles, *[a for a in archive if a["url"] not in live]]
    for item in displayed:
        country_for_url.setdefault(item["url"], item["countryId"])
    counts: dict[str, int] = {}
    for article in displayed:
        counts[article["countryId"]] = counts.get(article["countryId"], 0) + 1
    if not picture:
        claimed = {f"{a['url']}:{a['countryId']}" for a in displayed}
        for extra in extras:
            if f"{extra['url']}:{extra['countryId']}" not in claimed:
                counts[extra["countryId"]] = counts.get(extra["countryId"], 0) + 1
    pairs = [(country_by_id(cid), n) for cid, n in counts.items()]
    ranked_pairs = [(c, n) for c, n in pairs if c is not None]

    def rcmp(a: tuple[Country, int], b: tuple[Country, int]) -> int:
        return (b[1] - a[1]) or locale_compare(a[0].name, b[0].name)

    ranked_pairs.sort(key=functools.cmp_to_key(rcmp))
    by_key: dict[str, dict] = {}
    for article in displayed:
        key = f"{_to_fixed2(article['lat'])},{_to_fixed2(article['lon'])}"
        loc = by_key.get(key)
        if loc is None:
            loc = {"key": key, "lat": article["lat"], "lng": article["lon"], "countryId": article["countryId"], "articles": [],
                   "freshest": None}
            by_key[key] = loc
        loc["articles"].append(article)
        pub = published_at.get(article["url"])
        if pub is not None:
            minutes = max(0, (now - pub) / 60000)
            loc["freshest"] = minutes if loc["freshest"] is None else min(loc["freshest"], minutes)
    locations = sorted(by_key.values(), key=lambda loc: -len(loc["articles"]))
    arcs: dict[str, dict] = {}
    if not picture:
        for extra in extras:
            frm = country_by_id(country_for_url.get(extra["url"]))
            to = country_by_id(extra["countryId"])
            if not frm or not to or frm.id == to.id:
                continue
            a, b = (frm, to) if frm.id < to.id else (to, frm)
            key = f"{a.id}-{b.id}"
            if key in arcs:
                arcs[key]["count"] += 1
            else:
                arcs[key] = {"key": key, "from": a, "to": b, "count": 1}
    arc_list = sorted(arcs.values(), key=lambda arc: -arc["count"])[:60]
    return MapData(displayed=displayed, extras=extras, counts=counts, ranked=ranked_pairs,
                   max_count=ranked_pairs[0][1] if ranked_pairs else 0, locations=locations, arcs=arc_list,
                   placement_for=placement_for, country_for_url=country_for_url, published_at=published_at)


def _host_of_keep_case(url: str) -> str:
    """``sourceOf`` in map-data.tsx: ``new URL(url).hostname`` without ``www.`` (URL hostnames are lower case)."""
    return _host_of(url)


def heat_level(count: int) -> int:
    """0..5 heat level, matching the web's choropleth thresholds."""
    for level, floor in ((5, 8), (4, 5), (3, 3), (2, 2), (1, 1)):
        if count >= floor:
            return level
    return 0
