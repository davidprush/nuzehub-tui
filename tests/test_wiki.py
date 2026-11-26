"""Wikipedia results stay pinned to the library the status line names.

Status off, missing named file, mismatched rows, a file vanishing mid-search, the ssh (remote) status, and a
regression test with decoy libraries planted at documented default paths:
$HOME/SecondBrain-data/wiki/wikipedia.sqlite (HOME is the test's temp home) and
/usr/local/var/second-brain/wiki/wikipedia.sqlite. Otherwise the stand-in's default list points at a
temp decoy instead, so nothing can touch a real library.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import settle
from nuzehub_tui.client import NuzeHubClient
from nuzehub_tui.settings import Settings
from nuzehub_tui.ui.app import NuzeHubApp
from standin import DECOY_ARTICLES, REAL_ARTICLES, StandIn, Wiki, make_library

REAL_DEFAULT = Path("/usr/local/var/second-brain/wiki/wikipedia.sqlite")


@pytest.fixture
def libraries(tmp_path):
    named = make_library(tmp_path / "primary" / "wikipedia.sqlite", REAL_ARTICLES)
    home_default = Path(os.environ["HOME"]) / "SecondBrain-data" / "wiki" / "wikipedia.sqlite"
    make_library(home_default, DECOY_ARTICLES, wid_base=9000)
    planted: list[Path] = []
    work = REAL_DEFAULT.parents[2]
    if work.is_dir() and os.access(work, os.W_OK) and not REAL_DEFAULT.exists():
        make_library(REAL_DEFAULT, DECOY_ARTICLES, wid_base=9000)
        planted.append(REAL_DEFAULT)
        volumes_default = REAL_DEFAULT
    else:
        volumes_default = make_library(tmp_path / "intercepted-volumes-work-default" / "wikipedia.sqlite", DECOY_ARTICLES, wid_base=9000)
    yield named, [volumes_default, home_default]
    for p in planted:
        p.unlink(missing_ok=True)


def _screen(app) -> str:
    return "\n".join("".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips())


async def _run(standin: StandIn, tmp_path, steps):
    app = NuzeHubApp(NuzeHubClient(standin.url), settings=Settings(tmp_path / "s"), clock=lambda: "00:00:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.action_show_tab("tab-wiki")
        await settle(pilot)
        await steps(app, pilot)


@pytest.mark.parametrize("mode", ["fixed", "fallback"])
async def test_decoy_at_default_paths_never_answers(tmp_path, libraries, mode):
    named, defaults = libraries
    wiki = Wiki(named, defaults, mode=mode)
    with StandIn(wiki=wiki) as s:
        async def steps(app, pilot):
            await app.wiki_search("saturn rings")
            await settle(pilot)
            assert app.wiki_results and app.wiki_results[0]["title"] == "Rings of Saturn"
            await app.wiki_open("Saturn")
            await settle(pilot)
            assert app.wiki_article["title"] == "Saturn"
            named.rename(named.with_suffix(".away"))
            try:
                await app.wiki_search("saturn rings")
                await settle(pilot)
                assert app.wiki_results == [] and app.wiki_article is None and app.wiki_links == []
                assert "Decoy" not in _screen(app)
                assert app.wiki_query == "saturn rings"  # the search is kept
                await app.wiki_open("Decoy Saturn")
                await app.wiki_related("Saturn rings", "Cassini and NASA", "Brain")
                await settle(pilot)
                assert app.wiki_results == [] and app.wiki_article is None
                assert "Decoy" not in _screen(app)
            finally:
                named.with_suffix(".away").rename(named)
            await app.wiki_search("saturn v")
            await settle(pilot)
            assert app.wiki_results[0]["title"] == "Saturn V"
        await _run(s, tmp_path, steps)


async def test_status_off_and_missing_file_show_unavailable(tmp_path, libraries):
    named, defaults = libraries
    named.unlink()
    with StandIn(wiki=Wiki(named, defaults)) as s:
        async def steps(app, pilot):
            text = _screen(app)
            assert "Library off" in text
            await app.wiki_search("saturn")
            await settle(pilot)
            assert app.wiki_results == []
            assert "Your search is kept" in str(app.query_one("#wiki-notice").render())
        await _run(s, tmp_path, steps)


async def test_mismatched_rows_are_refused(tmp_path, libraries):
    named, defaults = libraries

    class Moved(Wiki):
        def search(self, query, k):
            res = super().search(query, k)
            if res.get("ok"):
                res["status"] = {**res["status"], "path": str(defaults[1])}
            return res

    with StandIn(wiki=Moved(named, defaults)) as s:
        async def steps(app, pilot):
            await app.wiki_search("saturn")
            await settle(pilot)
            assert app.wiki_results == []
            assert "not " in str(app.query_one("#wiki-notice").render())
        await _run(s, tmp_path, steps)


async def test_file_vanishing_mid_search(tmp_path, libraries):
    named, defaults = libraries
    wiki = Wiki(named, defaults, mode="fixed")
    with StandIn(wiki=wiki) as s:
        async def steps(app, pilot):
            await app.wiki_search("saturn")
            await settle(pilot)
            assert app.wiki_results
            wiki.vanish_after_status = True
            await app.wiki_search("rings")
            await settle(pilot)
            assert app.wiki_results == [] and "Decoy" not in _screen(app)
            wiki.vanish_after_status = False
            named.with_suffix(".away").rename(named)
        await _run(s, tmp_path, steps)


async def test_ssh_remote_status_answers_and_stays_pinned(tmp_path, libraries):
    named, defaults = libraries
    with StandIn(wiki=Wiki(named, defaults, source="remote")) as s:
        async def steps(app, pilot):
            assert "the server over ssh" in _screen(app)
            await app.wiki_search("saturn")
            await settle(pilot)
            assert app.wiki_results and app.wiki_results[0]["title"] == "Saturn"
        await _run(s, tmp_path, steps)
