"""Citations match the web panel byte for byte; the model chip is Ollama first with no warning."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nuzehub_tui import desk

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "wiki_panel_golden.json").read_text("utf-8"))
NOW = datetime(2026, 11, 21, 9, 30)


def test_citations_match_wiki_panel_ts():
    for case in GOLDEN:
        c = desk.citation_of(case["article"], via="Server primary", now=NOW)
        assert c == case["citation"]
        assert desk.citation_markdown(c) == case["markdown"]
        title, md = desk.citation_note(c)
        assert {"title": title, "markdown": md} == case["note"]
        body, added = desk.append_citation("My note\n\n", c)
        assert {"body": body, "added": added} == case["append1"]
        again, added2 = desk.append_citation(body, c)
        assert {"body": again, "added": added2} == case["append2"]
        assert desk.wiki_url(case["article"]["title"]) == case["url"]
        assert desk.excerpt_of(case["article"], "  a selected   passage of text  ") == case["sel"]


def test_model_chip_ollama_first_no_warning():
    up = {"ollama": {"ok": True, "models": ["a", "b"]}, "studio": {"ok": True, "models": ["c"]}, "savedOk": None}
    text, level = desk.model_chip(up)
    assert level == "ok" and text.startswith("Ollama") and "LM Studio" not in text and "warn" not in text.lower()
    text, level = desk.model_chip(up, {"ollama": {"ok": True, "count": 3}, "lmstudio": None})
    assert (text, level) == ("Ollama · 3 models", "ok")
    down = {"ollama": {"ok": False, "models": []}, "studio": {"ok": True, "models": ["c"]}}
    text, level = desk.model_chip(down)
    assert level == "fallback" and "LM Studio" in text
    assert desk.model_chip({"ollama": {"ok": False}, "studio": {"ok": False}})[1] == "down"


def test_save_and_cite_shapes():
    inst = {"brain": {"notes": [{"id": "n1", "title": "T", "body": "x", "url": "", "sourceTag": "quick"}]}}
    c = desk.citation_of({"title": "Saturn", "abstract": "Saturn is a planet."}, via="Server primary", now=NOW)
    brain, nid, existed = desk.brain_with_save(inst, c, note_id="new", now="2026-11-21T00:00:00.000Z")
    note = brain["notes"][0]
    assert not existed and note["para"] == "resources" and note["tags"] == ["wikipedia"] and note["sourceTag"] == "wikipedia"
    assert note["sourceKind"] == "markdown" and note["url"] == c["url"] and inst["brain"]["notes"][0]["id"] == "n1"
    again = {"brain": brain}
    _b, nid2, existed2 = desk.brain_with_save(again, c)
    assert existed2 and nid2 == "new"
    cited, added = desk.brain_with_cite(again, "n1", c)
    assert added
    _c2, added2 = desk.brain_with_cite({"brain": cited}, "n1", c)
    assert not added2
