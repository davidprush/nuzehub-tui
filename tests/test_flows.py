"""State flows end to end over HTTP against the stand-in: repeated runs, switching screens, a stale instance,
the wiki clearing when the library goes away, Save then Undo restoring the stored bytes, and Cite twice."""

from __future__ import annotations

import copy
import json

from conftest import settle
from nuzehub_tui.client import NuzeHubClient
from nuzehub_tui.settings import Settings
from nuzehub_tui.ui.app import NuzeHubApp
from nuzehub_tui.ui.dialogs import CiteDialog, GateScreen, SaveDialog
from standin import StandIn
from uihelp import TABS, demo_app, open_article, screen_lines


def _app(s: StandIn, tmp_path) -> NuzeHubApp:
    return NuzeHubApp(NuzeHubClient(s.url), settings=Settings(tmp_path / "state"), clock=lambda: "09:30:00")


def _brain_bytes(s: StandIn) -> bytes:
    return json.dumps(s.data.instance["brain"], sort_keys=True, ensure_ascii=False).encode()


async def test_save_then_undo_restores_byte_for_byte(tmp_path):
    with StandIn() as s:
        app = _app(s, tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            original = _brain_bytes(s)
            await open_article(app, pilot)
            app.action_wiki_save()
            await settle(pilot, 4)
            assert isinstance(app.screen, SaveDialog)
            await pilot.click("#save-ok")
            await settle(pilot, 4)
            saved = s.data.instance["brain"]["notes"][0]
            assert saved["sourceTag"] == "wikipedia" and saved["para"] == "resources" and saved["title"] == "Saturn"
            assert _brain_bytes(s) != original
            await pilot.press("u")
            await settle(pilot, 4)
            assert _brain_bytes(s) == original
            assert s.stored_bytes == json.dumps(s.data.instance, sort_keys=True, ensure_ascii=False).encode()
            # Save a second time is a no-op once it is there
            app.action_wiki_save()
            await settle(pilot, 4)
            await pilot.click("#save-ok")
            await settle(pilot, 4)
            app.action_wiki_save()
            await settle(pilot, 4)
            await pilot.click("#save-ok")
            await settle(pilot, 4)
            assert sum(n.get("sourceTag") == "wikipedia" for n in s.data.instance["brain"]["notes"]) == 1


async def test_cite_twice_does_not_duplicate_and_new_note_works(tmp_path):
    with StandIn() as s:
        app = _app(s, tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await open_article(app, pilot)
            for _ in range(2):
                app.action_wiki_cite()
                await settle(pilot, 4)
                assert isinstance(app.screen, CiteDialog)
                await pilot.click("#cite-ok")
                await settle(pilot, 4)
            target = next(n for n in s.data.instance["brain"]["notes"] if n["id"] == app.cite_target)
            assert target["body"].count("https://en.wikipedia.org/wiki/Saturn") == 1
            assert "already cites" in str(app.query_one("#wiki-notice").render())
            before = len(s.data.instance["brain"]["notes"])
            app.action_wiki_cite()
            await settle(pilot, 4)
            app.screen.query_one("#cite-notes").highlighted = 0  # first row is "New note"
            await pilot.click("#cite-ok")
            await settle(pilot, 4)
            notes = s.data.instance["brain"]["notes"]
            assert len(notes) == before + 1 and any(n["title"] == "Notes on Saturn" for n in notes)


async def test_stale_instance_is_reloaded_not_overwritten(tmp_path):
    with StandIn() as s:
        app = _app(s, tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await open_article(app, pilot)
            other = copy.deepcopy(s.data.instance["brain"])
            other["notes"][0]["body"] += "\nEdited on another Mac."
            assert s.data.save_instance(brain=other, base_rev=s.data.instance["rev"])["ok"]
            app.action_wiki_save()
            await settle(pilot, 4)
            await pilot.click("#save-ok")
            await settle(pilot, 6)
            assert "Edited on another Mac." in s.data.instance["brain"]["notes"][0]["body"]
            assert app.instance["rev"] == s.data.instance["rev"]
            assert not any(n.get("sourceTag") == "wikipedia" for n in s.data.instance["brain"]["notes"])


async def test_repeated_runs_and_switching_screens(tmp_path):
    with StandIn() as s:
        for run in range(3):
            app = _app(s, tmp_path)
            async with app.run_test(size=(100, 30)) as pilot:
                await settle(pilot)
                for i, tab in enumerate(TABS[1:] * 2):
                    await pilot.press(str(i % 6 + 1))
                    await settle(pilot, 1)
                    assert app._active() == tab
                await pilot.press("r")
                await settle(pilot)
                assert app.instance["rev"] == 7
                await pilot.press("t")
                await settle(pilot)
            assert Settings(tmp_path / "state").load()["active_tab"] == TABS[-1], run


async def test_wiki_cleared_when_library_goes_away(tmp_path):
    app = demo_app(tmp_path / "s")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await open_article(app, pilot)
        assert app.wiki_article and app.wiki_results
        app.backend.wiki_state = "missing"
        await pilot.press("r")
        await settle(pilot, 4)
        assert app.wiki_article is None and app.wiki_results == [] and app.wiki_links == []
        assert "Saturn is the sixth planet" not in "\n".join(screen_lines(app))
        app.backend.wiki_state = "on"
        await app.wiki_search("saturn")
        await settle(pilot)
        assert app.wiki_results


async def test_q_only_quits_without_a_dialog(tmp_path):
    app = demo_app(tmp_path / "s")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        for action in ("help", "about", "theme_modal"):
            getattr(app, f"action_{action}")()
            await settle(pilot, 4)
            await pilot.press("q")
            await settle(pilot)
            assert app.is_running and len(app.screen_stack) == 2, action
            await pilot.press("escape")
            await settle(pilot)
        app.action_open_menu(0)
        await settle(pilot)
        await pilot.press("escape")
        await settle(pilot)
        await pilot.press("q")
        await settle(pilot)
    assert app.return_code in (0, None)


async def test_gate_unlocks_and_never_shows_the_key(tmp_path):
    key = "test-key-placeholder"
    with StandIn(peer="remote", key=key) as s:
        app = _app(s, tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await settle(pilot)
            assert isinstance(app.screen, GateScreen)
            await pilot.press("q")
            await settle(pilot)
            assert app.is_running  # q does not quit from the gate
            app.screen.query_one("#gate-key").value = "nope"
            await pilot.click("#gate-unlock")
            await settle(pilot, 4)
            assert isinstance(app.screen, GateScreen)
            assert "does not match" in str(app.screen.query_one("#gate-error").render())
            app.screen.query_one("#gate-key").value = key
            await pilot.click("#gate-unlock")
            await settle(pilot, 6)
            assert not isinstance(app.screen, GateScreen)
            assert app.instance["rev"] == 7
            text = "\n".join(screen_lines(app))
            assert key not in text and key not in "\n".join(app._activity)


async def test_saved_theme_does_not_ping_pong(tmp_path):
    """A saved non-default theme used to fight the Select's first Changed event: the two themes swapped
    back and forth (146 theme switches in one short session) and every key took about 5 s."""
    from textual.app import App

    from nuzehub_tui.demo import DemoBackend

    st = Settings(tmp_path / "state")
    st.save({"theme": "tokyo-night", "theme_migrated_020": True})  # 0.2.0: past the one-time HUD switch
    switches: list[str] = []
    orig = App._watch_theme

    def counting(self, name):
        switches.append(name)
        return orig(self, name)

    App._watch_theme = counting  # type: ignore[method-assign]
    try:
        app = NuzeHubApp(DemoBackend(), settings=st, clock=lambda: "09:30:00")
        async with app.run_test(size=(100, 30)) as pilot:
            await settle(pilot)
            for key in "1234":
                await pilot.press(key)
                await settle(pilot, 1)
            assert app.theme == "tokyo-night" and app.query_one("#theme-select").value == "tokyo-night"
    finally:
        App._watch_theme = orig  # type: ignore[method-assign]
    assert len(switches) <= 2, switches[:6]
    assert st.load()["theme"] == "tokyo-night"
