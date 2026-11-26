"""Once against a real booted NuzeHub tree (never the live server). Skipped unless NUZEHUB_TUI_LIVE_URL is set.

NUZEHUB_TUI_LIVE_URL      e.g. http://127.0.0.1:18080 (a scratch NuzeHub dev server with a scratch HOME)
NUZEHUB_TUI_LIVE_PRIMARY  the synthetic primary library that server's Second Brain names; it is renamed away
                          and back to prove a decoy at the default path never answers.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from conftest import _real_getaddrinfo, settle
from nuzehub_tui import desk
from nuzehub_tui.client import NuzeHubClient
from nuzehub_tui.settings import Settings
from nuzehub_tui.ui.app import NuzeHubApp
from uihelp import TABS, screen_lines

URL = os.environ.get("NUZEHUB_TUI_LIVE_URL", "")
PRIMARY = os.environ.get("NUZEHUB_TUI_LIVE_PRIMARY", "")
pytestmark = pytest.mark.skipif(not URL, reason="set NUZEHUB_TUI_LIVE_URL to a scratch NuzeHub dev server")


@pytest.fixture(autouse=True)
def allow_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _real_getaddrinfo)
    assert NuzeHubClient(URL).loopback, "live tests only run against a loopback scratch server"


def _brain(c: NuzeHubClient) -> bytes:
    return json.dumps(c.load_instance()["brain"], sort_keys=True, ensure_ascii=False).encode()


def test_live_handlers():
    c = NuzeHubClient(URL, timeout=60)
    view = c.access_status()
    assert view["open"] and "key" not in view
    inst = c.load_instance()
    assert isinstance(inst["rev"], int)
    assert "stories" in c.fetch_news(desk.feed_urls(inst)[:1] or ["https://example.invalid/x.xml"])
    assert "quotes" in c.get_markets(["AAPL"], "5d")
    assert "hits" in c.search_symbols("app")
    assert "results" in c.get_hazards("24h", ["quake"])
    assert c.wiki_status()["state"] == "on"
    res = c.wiki_search("saturn", 5)
    assert res["ok"] and res["results"]
    title = res["results"][0]["title"]
    assert c.wiki_read(title)["ok"]
    assert c.wiki_related("Saturn rings", "Cassini")["ok"]
    assert "ollama" in c.probe_engines()
    assert c.model_status() is not None


async def test_live_save_undo_cite_and_decoy(tmp_path):
    c = NuzeHubClient(URL, timeout=60)
    before = _brain(c)
    app = NuzeHubApp(NuzeHubClient(URL, timeout=60), settings=Settings(tmp_path / "s"), clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        for tab in TABS:
            app.action_show_tab(tab)
            await settle(pilot)
        app.action_show_tab("tab-wiki")
        await app.wiki_search("saturn")
        await settle(pilot)
        saved = {n.get("url") for n in c.load_instance()["brain"]["notes"] if n.get("sourceTag") == "wikipedia"}
        fresh = next(r["title"] for r in app.wiki_results if desk.wiki_url(r["title"]) not in saved)
        await app.wiki_open(fresh)
        await settle(pilot)
        app.action_wiki_save()
        await settle(pilot, 4)
        await pilot.click("#save-ok")
        await settle(pilot, 4)
        assert _brain(c) != before
        await pilot.press("u")
        await settle(pilot, 4)
        assert _brain(c) == before  # byte-for-byte restore on the real server
        for _ in range(2):
            app.action_wiki_cite()
            await settle(pilot, 4)
            await pilot.click("#cite-ok")
            await settle(pilot, 4)
        url = desk.wiki_url(app.wiki_article["title"])
        note = next(n for n in c.load_instance()["brain"]["notes"] if n["id"] == app.cite_target)
        assert note["body"].count(url) == 1
        await pilot.press("u")
        await settle(pilot, 4)
        if PRIMARY:
            p = Path(PRIMARY)
            p.rename(p.with_suffix(".away"))
            try:
                assert c.wiki_status()["state"] != "on"
                await app.wiki_search("saturn")
                await settle(pilot)
                assert app.wiki_results == [] and app.wiki_article is None
                assert "Decoy" not in "\n".join(screen_lines(app))
                raw = c.wiki_search("saturn", 5)
                assert not raw.get("ok") and not any("Decoy" in r.get("title", "") for r in raw.get("results", []))
            finally:
                p.with_suffix(".away").rename(p)
            assert c.wiki_status()["state"] == "on"
