"""Pure helpers for the TUI: Wikipedia pinning, citations (same text as the web panel), notes, model chip.

The citation helpers are line-for-line ports of NuzeHub's ``src/lib/brain/wiki-panel.ts`` (excerptOf,
citationOf, citationMarkdown, appendCitation, citationNote), so a note cited from the TUI reads exactly like
one cited from the web desk. Nothing here ranks, fetches or calls a model.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

LICENSE = "CC BY-SA 4.0"
WIKI_BASE = "https://en.wikipedia.org/wiki/"


# ---- Wikipedia library pinning --------------------------------------------------------------------
def library_on(status: dict[str, Any] | None) -> bool:
    return bool(status) and status.get("state") == "on"  # type: ignore[union-attr]


def library_name(status: dict[str, Any] | None) -> str:
    if not status:
        return ""
    return str(status.get("path") or status.get("sourceLabel") or "")


def status_summary(status: dict[str, Any] | None) -> str:
    """Short status line, like the web panel's ``statusSummary``."""
    if not status:
        return "Library: checking…"
    state = status.get("state")
    if state == "on":
        parts = [str(status.get("sourceLabel") or "library")]
        if status.get("articles"):
            parts.append(f"{status['articles']} articles")
        if status.get("freshness"):
            parts.append(str(status["freshness"]))
        return "Library on: " + " · ".join(parts)
    line = " ".join(str(status.get("line") or "").split())
    if state == "off":
        return f"Library off: {line}" if line else "Library off."
    return f"Library unavailable: {line}" if line else "Library unavailable."


def pinned(answer: dict[str, Any], named: dict[str, Any] | None) -> tuple[bool, str]:
    """True when ``answer`` is a success that came from the library the status line names.

    The host already refuses rows that are not in the named file (wiki-panel.server.ts). The TUI checks again
    that the answer's own status is "on" and names the same file and source as the status line it shows, so a
    library that moved, vanished or changed between calls can never fill the screen.
    """
    if not answer.get("ok"):
        return False, str(answer.get("message") or "The library did not answer.")
    st = answer.get("status") or {}
    if not library_on(st):
        return False, status_summary(st)
    if not library_on(named):
        return False, "The library is not available, so no results are shown."
    assert named is not None
    if (st.get("path") or "") != (named.get("path") or "") or (st.get("source") or "") != (named.get("source") or ""):
        return False, (
            f"These results came from {library_name(st) or 'another library'}, not {library_name(named)} as the "
            "status line says. Nothing is shown. Press r to check the library again."
        )
    return True, ""


# ---- citations (port of wiki-panel.ts) ------------------------------------------------------------
def wiki_url(title: str) -> str:
    """``encodeURIComponent`` of the title with spaces as underscores, then ( ) escaped, as wikiUrl does."""
    from urllib.parse import quote

    return WIKI_BASE + quote(title.replace(" ", "_"), safe="-_.!~*'()").replace("(", "%28").replace(")", "%29")


def article_body(title: str, text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and re.match(r"^#\s+", lines[0]) and re.sub(r"^#\s+", "", lines[0]).strip().lower() == title.strip().lower():
        lines.pop(0)
    return "\n".join(lines).strip()


def excerpt_of(article: dict[str, Any], selection: str = "", limit: int = 320) -> str:
    pick = re.sub(r"\s+", " ", selection).strip()
    if len(pick) >= 12:
        return pick if len(pick) <= limit else pick[: limit - 1].rstrip() + "…"
    source = str(article.get("abstract") or "").strip()
    if not source:
        body = article_body(str(article.get("title", "")), str(article.get("text") or ""))
        paras = [p.strip() for p in re.split(r"\n\s*\n", body)]
        source = next((p for p in paras if p and not re.match(r"^(#|\||[*-] |!\[)", p)), "")
    source = re.sub(r"\s+", " ", re.sub(r"\*\*|__|`", "", source)).strip()
    if len(source) <= limit:
        return source
    cut = source[:limit]
    stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: stop + 1] if stop > limit * 0.4 else cut.rstrip() + "…"


def citation_of(article: dict[str, Any], *, selection: str = "", via: str = "", now: datetime | None = None) -> dict[str, str]:
    when = now or datetime.now()
    return {
        "title": str(article.get("title", "")),
        "url": str(article.get("url") or "").strip() or wiki_url(str(article.get("title", ""))),
        "excerpt": excerpt_of(article, selection),
        "retrieved": f"{when.year}-{when.month:02d}-{when.day:02d}",
        "via": via.strip() or "Second Brain Wikipedia library",
    }


def citation_markdown(c: dict[str, str]) -> str:
    quote = f"> {re.sub(chr(10) + '+', ' ', c['excerpt'])}\n" if c["excerpt"] else ""
    return (
        f"{quote}> — [{c['title']}]({c['url']}), Wikipedia, {LICENSE}. Retrieved {c['retrieved']} from the "
        f"Second Brain library ({c['via']})."
    )


def append_citation(body: str, c: dict[str, str]) -> tuple[str, bool]:
    if f"]({c['url']})" in body:
        return body, False
    trimmed = body.rstrip()
    return f"{trimmed + chr(10) + chr(10) if trimmed else ''}{citation_markdown(c)}\n", True


def citation_note(c: dict[str, str]) -> tuple[str, str]:
    lines = [
        f"# {c['title']}",
        "",
        f"Wikipedia · {LICENSE} · retrieved {c['retrieved']}",
        "",
        c["url"],
        "",
        f"> {c['excerpt']}" if c["excerpt"] else "",
        "",
        f"Source: Wikipedia, \"{c['title']}\" ({c['url']}), {LICENSE}. From the Second Brain Wikipedia library ({c['via']}).",
    ]
    markdown = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return c["title"], markdown + "\n"


# ---- notes (same shape as the web desk's capture()) -----------------------------------------------
def iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(UTC).microsecond // 1000:03d}Z"


def new_note(*, title: str, body: str, url: str = "", para: str = "inbox", tags: list[str] | None = None,
             source_kind: str = "text", source_tag: str = "quick", note_id: str | None = None,
             now: str | None = None) -> dict[str, Any]:
    stamp = now or iso_now()
    return {
        "id": note_id or str(uuid.uuid4()),
        "title": title.strip() or "Untitled",
        "body": body.strip(),
        "para": para,
        "tags": list(tags or []),
        "sourceKind": source_kind,
        "sourceTag": source_tag.strip() or "quick",
        "url": url.strip(),
        "attachmentId": None,
        "attachmentMime": "",
        "createdAt": stamp,
        "updatedAt": stamp,
        "summary": "",
        "takeaway": "",
        "actions": [],
        "embeddedHash": "",
    }


def notes_of(instance: dict[str, Any]) -> list[dict[str, Any]]:
    brain = instance.get("brain") or {}
    notes = brain.get("notes") if isinstance(brain, dict) else None
    return [n for n in notes or [] if isinstance(n, dict)]


def brain_with_save(instance: dict[str, Any], c: dict[str, str], *, note_id: str | None = None,
                    now: str | None = None) -> tuple[dict[str, Any], str, bool]:
    """Save to Brain: the web panel's onSave. Reuses a note already saved for this article."""
    brain = copy.deepcopy(instance.get("brain") or {})
    notes = [n for n in brain.get("notes") or [] if isinstance(n, dict)]
    for note in notes:
        if note.get("url") == c["url"] and note.get("sourceTag") == "wikipedia":
            return brain, str(note.get("id")), True
    title, markdown = citation_note(c)
    note = new_note(title=title, body=markdown, url=c["url"], para="resources", tags=["wikipedia"],
                    source_kind="markdown", source_tag="wikipedia", note_id=note_id, now=now)
    brain["notes"] = [note, *notes]
    return brain, note["id"], False


def brain_with_cite(instance: dict[str, Any], note_id: str, c: dict[str, str], *, now: str | None = None) -> tuple[dict[str, Any], bool]:
    """Cite into a picked note: the web panel's onCite (appendCitation, once per article)."""
    brain = copy.deepcopy(instance.get("brain") or {})
    notes = [n for n in brain.get("notes") or [] if isinstance(n, dict)]
    added = False
    for note in notes:
        if note.get("id") != note_id:
            continue
        body, added = append_citation(str(note.get("body") or ""), c)
        if added:
            note["body"] = body
            note["updatedAt"] = now or iso_now()
            note["embeddedHash"] = ""
        break
    brain["notes"] = notes
    return brain, added


def brain_with_new_cited_note(instance: dict[str, Any], c: dict[str, str], *, note_id: str | None = None,
                              now: str | None = None) -> tuple[dict[str, Any], str]:
    """Cite → "New note": a new Inbox note holding just the citation."""
    brain = copy.deepcopy(instance.get("brain") or {})
    notes = [n for n in brain.get("notes") or [] if isinstance(n, dict)]
    body, _ = append_citation("", c)
    note = new_note(title=f"Notes on {c['title']}", body=body, url="", para="inbox", tags=["wikipedia"],
                    note_id=note_id, now=now)
    brain["notes"] = [note, *notes]
    return brain, note["id"]


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---- model chip (Ollama first) --------------------------------------------------------------------
def model_chip(engines: dict[str, Any] | None, status: dict[str, Any] | None = None) -> tuple[str, str]:
    """(text, level). level is "ok", "fallback" or "down". While Ollama answers it is "ok", with no warning.

    ``engines`` is ``probeEngines``; ``status`` is ``GET /api/model-status`` (loopback only), used when present.
    """
    o_ok = o_n = s_ok = s_n = None
    if status and isinstance(status.get("ollama"), dict):
        o_ok = bool(status["ollama"].get("ok"))
        o_n = int(status["ollama"].get("count") or 0)
        lm = status.get("lmstudio")
        if isinstance(lm, dict):
            s_ok, s_n = bool(lm.get("ok")), int(lm.get("count") or 0)
    if engines:
        ol = engines.get("ollama") or {}
        st = engines.get("studio") or {}
        if o_ok is None:
            o_ok, o_n = bool(ol.get("ok")), len(ol.get("models") or [])
        if s_ok is None:
            s_ok, s_n = bool(st.get("ok")), len(st.get("models") or [])
    if o_ok is None and s_ok is None:
        return "Model: checking…", "ok"
    if o_ok:
        return f"Ollama · {o_n} model{'s' if o_n != 1 else ''}", "ok"
    if s_ok:
        return f"LM Studio (fallback, Ollama not answering) · {s_n} model{'s' if s_n != 1 else ''}", "fallback"
    return "No local model: Ollama is not answering on the server", "down"


# ---- small formatting -----------------------------------------------------------------------------
_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 40) -> str:
    vals = [float(v) for v in values if isinstance(v, int | float)]
    if not vals:
        return ""
    if len(vals) > width:
        step = len(vals) / width
        vals = [vals[min(len(vals) - 1, int(i * step))] for i in range(width)]
    lo, hi = min(vals), max(vals)
    span = hi - lo or 1.0
    return "".join(_BLOCKS[min(7, int((v - lo) / span * 7.999))] for v in vals)


def when(ms_or_iso: Any) -> str:
    try:
        if isinstance(ms_or_iso, int | float):
            dt = datetime.fromtimestamp(float(ms_or_iso) / 1000, UTC)
        else:
            dt = datetime.fromisoformat(str(ms_or_iso).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%b %d %H:%M")
    except (ValueError, OSError, OverflowError):
        return ""


def feed_urls(instance: dict[str, Any]) -> list[str]:
    prefs = (instance.get("desk") or {}).get("prefs") or {}
    return [str(s.get("url")) for s in prefs.get("sources") or [] if isinstance(s, dict) and s.get("enabled") and s.get("url")][:40]


def watchlist(instance: dict[str, Any]) -> list[str]:
    return [str(s) for s in (instance.get("desk") or {}).get("watchlist") or [] if s][:40]
