"""0.2.0 §0.1 one-time switch to HUDdy (tests 1-5), §0.3 contrast for both required themes and §0.7 the
startup tab. Every test uses a temp ``NUZEHUB_TUI_STATE_DIR`` (conftest)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import settle
from nuzehub_tui import themes
from nuzehub_tui.demo import DemoBackend
from nuzehub_tui.settings import MIGRATED_NOTE, TABS, Settings
from nuzehub_tui.ui.app import NuzeHubApp

P = {p.id: p for p in themes.PALETTES}


def state() -> Settings:
    return Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]))


def saved() -> dict:
    return json.loads((Path(os.environ["NUZEHUB_TUI_STATE_DIR"]) / "settings.json").read_text())


async def launch(size=(120, 40)) -> tuple[str, list[str], str]:
    """One app launch: (theme shown, activity lines, tab shown)."""
    app = NuzeHubApp(DemoBackend(), settings=state(), demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=size) as pilot:
        await settle(pilot)
        return app.theme, [str(a) for a in app._activity], app._active()


async def test_1_no_flag_saved_github_dark_switches_once():
    state().save({"theme": "github-dark"})
    assert "theme_migrated_020" not in json.loads((Path(os.environ["NUZEHUB_TUI_STATE_DIR"]) / "settings.json").read_text()) \
        or saved()["theme_migrated_020"] is False
    theme, log, _ = await launch()
    assert theme == "huddy"
    assert saved()["theme"] == "huddy" and saved()["theme_migrated_020"] is True
    assert sum(MIGRATED_NOTE in line for line in log) == 1
    assert MIGRATED_NOTE == "Theme: switched to HUDdy once; press T or use the Themes menu to change."


async def test_2_flag_and_github_dark_stays_across_two_launches():
    state().save({"theme": "github-dark", "theme_migrated_020": True})
    for _ in range(2):
        theme, log, _ = await launch()
        assert theme == "github-dark" and saved()["theme"] == "github-dark"
        assert not any(MIGRATED_NOTE in line for line in log)


async def test_3_flag_and_other_themes_stay():
    for name in ("nord", "powerlevel10k"):
        assert name in P
        state().save({"theme": name, "theme_migrated_020": True})
        theme, _, _ = await launch()
        assert theme == name and saved()["theme"] == name


async def test_4_fresh_install_gets_hud_and_the_flag():
    assert not (Path(os.environ["NUZEHUB_TUI_STATE_DIR"]) / "settings.json").exists()
    theme, log, _ = await launch()
    assert theme == "huddy" and saved()["theme_migrated_020"] is True
    assert sum(MIGRATED_NOTE in line for line in log) == 1


async def test_5_a_choice_after_migration_persists():
    app = NuzeHubApp(DemoBackend(), settings=state(), demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.theme == "huddy"
        app._apply_theme("github-dark")  # what t / T / the Themes menu / the dropdown call
        await settle(pilot)
    for _ in range(2):
        theme, log, _ = await launch()
        assert theme == "github-dark" and not any(MIGRATED_NOTE in line for line in log)


def test_migration_is_one_save_and_unknown_theme_falls_back(monkeypatch):
    st = state()
    st.save({"theme": "tokyo-night"})
    saves: list[dict] = []
    orig = Settings.save
    monkeypatch.setattr(Settings, "save", lambda self, patch: (saves.append(dict(patch)), orig(self, patch))[1])
    assert st.migrate_theme() is True and saves == [{"theme": "huddy", "theme_migrated_020": True}]
    assert st.migrate_theme() is False and len(saves) == 1
    st.save({"theme": "no-such-theme"})
    assert st.load()["theme"] == themes.DEFAULT == "huddy"


# ---- §0.7 startup tab ----


async def test_saved_news_tab_opens_on_the_desk_and_keys_reach_every_tab():
    state().save({"active_tab": "tab-news", "theme_migrated_020": True})
    app = NuzeHubApp(DemoBackend(), settings=state(), demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app._active() == "tab-desk" == TABS[0]
        for key, tab in zip("123456", TABS[1:], strict=True):
            await pilot.press(key)
            await settle(pilot, 1)
            assert app._active() == tab, (key, tab)
        await pilot.press("0")
        await settle(pilot, 1)
        assert app._active() == "tab-desk"
        app.action_show_tab("tab-markets")  # what the View menu does
        await settle(pilot, 1)
        assert app._active() == "tab-markets"


# ---- §0.3 contrast (T§2.1), both required themes ----


def test_contrast_both_required_themes():
    gh, hud = P["github-dark"], P["huddy"]
    # text on the accent is the background colour
    assert round(themes.contrast("#0d1117", gh.primary), 2) == 6.11 and gh.primary == "#4493f8"
    assert round(themes.contrast(hud.background, hud.primary), 2) == 12.59  # 0.2.3 soft background
    for p in (gh, hud):
        assert themes.contrast(p.background, p.primary) >= 4.5
        assert themes.contrast(p.foreground, p.panel) >= 4.5  # menu bar and status bar text on $panel
    # muted / accent on $panel fail for GitHub Dark, so readable() is what may sit there
    assert round(themes.contrast(gh.muted, gh.panel), 2) == 3.97 and round(themes.contrast(gh.primary, gh.panel), 2) == 3.94
    assert (themes.readable(gh.muted, gh.panel, 4.5), themes.readable(gh.primary, gh.panel, 4.5)) == ("#979fa8", "#60a3f9")
    assert (themes.readable(hud.muted, hud.panel, 4.5), themes.readable(hud.primary, hud.panel, 4.5)) == ("#7d93ad", "#5ee1ff")


async def test_panel_rows_use_foreground_and_the_status_fallback_is_the_new_accent():
    from textual.widgets import Static

    from nuzehub_tui.ui.menubar import MenuBar
    src = Path(__file__).parents[1].joinpath("src/nuzehub_tui/ui/app.py").read_text()
    assert "'#58a6ff'" not in src and "theme.primary or '#4493f8'" in src
    for theme in ("huddy", "github-dark"):
        state().save({"theme": theme, "theme_migrated_020": True})
        app = NuzeHubApp(DemoBackend(), settings=state(), demo=True, clock=lambda: "09:30:00")
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            p = P[theme]
            for widget in (app.query_one("#hud", Static), app.query_one(MenuBar)):
                assert widget.styles.background.hex.lower() == p.panel
                assert widget.styles.color.hex.lower() == p.foreground


async def test_focused_checkbox_and_layer_toggle_are_accent_not_bold():
    from textual.widgets import Checkbox

    from nuzehub_tui.ui.deskview import Toggle
    for theme in ("huddy", "github-dark"):
        state().save({"theme": theme, "theme_migrated_020": True})
        app = NuzeHubApp(DemoBackend(), settings=state(), demo=True, clock=lambda: "09:30:00")
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            p = P[theme]
            toggle = app.query(Toggle).first()
            toggle.focus()
            await settle(pilot, 1)
            assert toggle.styles.color.hex.lower() == p.primary and not toggle.styles.text_style.bold
            label = toggle.render().spans[1]  # type: ignore[attr-defined]  # glyph, label, hint
            from textual.color import Color
            assert Color.parse(str(label.style)).hex.lower() == p.primary
            box = app.query(Checkbox).first()
            app.action_show_tab(next(t for t in TABS if box in app.query_one(f"#{t}").query(Checkbox)))
            await settle(pilot, 1)
            box.focus()
            await settle(pilot, 1)
            assert box.has_focus
            assert box.styles.color.hex.lower() == p.primary
            assert not box.styles.text_style.bold
