"""0.2.2 Polish: the HUDdy rename (and the gods-eye-hud alias), per-element Live Mode with the master L memory, the
smoother ticker/globe cadence, tab switches without no-op repaints (Pilot rapid cycling) and the coloured Markets
graphs. Demo backend (synthetic data) only."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import settle
from nuzehub_tui import themes
from nuzehub_tui.demo import DemoBackend
from nuzehub_tui.settings import LIVE_KEYS, Settings
from nuzehub_tui.themes import contrast_ratio, fallback_colours
from nuzehub_tui.ui.app import NuzeHubApp
from nuzehub_tui.ui.deskview import DeskView
from test_desk_ui import make, screen

POLLS = ("alerts", "news", "markets", "hazards", "instance")
TABS = ("tab-desk", "tab-news", "tab-markets", "tab-geo", "tab-brain", "tab-wiki", "tab-status")


def states(app) -> dict[str, bool]:
    return app.desk_timer_states()


def activity(app) -> str:
    return "\n".join(app._activity)


def raw_settings(payload: dict) -> Settings:
    st = Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]))
    st.root.mkdir(parents=True, exist_ok=True)
    st.path.write_text(json.dumps(payload), "utf-8")
    return st


# ---- 1. HUDdy ----


def test_huddy_name_id_and_unchanged_palette():
    p = themes.get("huddy")  # 0.2.3: the four soft-contrast tokens moved (Spec 1.0); everything else is unchanged
    assert themes.DEFAULT == "huddy" and p.name == "HUDdy"
    assert themes.get("gods-eye-hud") is p  # legacy id
    assert (p.background, p.surface, p.panel, p.foreground, p.muted, p.primary, p.accent, p.success, p.warning, p.error) == (
        "#080e19", "#0d192c", "#112138", "#c2cfdc", "#7d93ad", "#5ee1ff", "#5ee1ff", "#3dffa8", "#ffb547", "#ff5470")
    assert "God's Eye HUD" not in [x.name for x in themes.PALETTES] and "gods-eye-hud" not in themes.NAMES


@pytest.mark.parametrize("saved", ["huddy", "gods-eye-hud"])
def test_settings_accept_huddy_and_the_legacy_id(saved, tmp_path):
    st = Settings(tmp_path / "s")
    st.root.mkdir(parents=True)
    st.path.write_text(json.dumps({"theme": saved, "theme_migrated_020": True}), "utf-8")
    assert st.load()["theme"] == "huddy"
    assert st.migrate_theme() is False and st.load()["theme_migrated_020"] is True  # flag intact, no re-switch
    st.path.write_text(json.dumps({"theme": "nord", "theme_migrated_020": True}), "utf-8")
    assert st.migrate_theme() is False and st.load()["theme"] == "nord"  # a saved choice is never overridden


async def test_legacy_theme_starts_as_huddy_everywhere_visible():
    st = raw_settings({"theme": "gods-eye-hud", "theme_migrated_020": True})
    app = NuzeHubApp(DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.theme == "huddy" and "HUDdy" in screen(app) and "God's Eye" not in screen(app)
        menu = next(m for m in app.menus if m.title == "Themes")
        labels = [i.label for i in menu.items()]
        assert "HUDdy" in labels and not any("God's Eye" in x for x in labels)
        assert next(i for i in menu.items() if i.label == "HUDdy").checked()


async def test_fresh_install_notice_names_huddy():
    app = NuzeHubApp(DemoBackend(), settings=Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]) / "fresh"), demo=True,
                     clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.theme == "huddy" and "switched to HUDdy once" in activity(app)


# ---- 2. per-element Live settings ----


def test_live_elements_default_off_and_persist(tmp_path):
    st = Settings(tmp_path / "s")
    data = st.load()
    assert all(data[k] is False for k in LIVE_KEYS) and data["live_last"] is None
    st.save({"live_ticker": True, "live_updates": True})
    raw = json.loads(st.path.read_text("utf-8"))
    assert raw["live_ticker"] is True and raw["live_updates"] is True and raw["live_globe"] is False
    assert "live_mode" not in raw


def test_legacy_live_mode_maps_to_all_three(tmp_path):
    st = Settings(tmp_path / "s")
    st.root.mkdir(parents=True)
    st.path.write_text('{"theme": "github-dark", "live_mode": true, "static_tape": true}', "utf-8")
    data = st.load()
    assert all(data[k] is True for k in LIVE_KEYS) and "static_tape" not in data and "live_mode" not in data
    # per-element keys present: they win over the legacy switch
    st.path.write_text('{"live_mode": true, "live_ticker": true}', "utf-8")
    data = st.load()
    assert (data["live_globe"], data["live_ticker"], data["live_updates"]) == (False, True, False)
    for raw in ('{"live_mode": false}', '{"live_mode": "yes"}', '{"live_globe": 1, "live_ticker": null}',
                '{"live_last": ["bogus"]}', '{"live_last": "live_globe"}'):
        st.path.write_text(raw, "utf-8")
        data = st.load()
        assert not any(data[k] for k in LIVE_KEYS) and data["live_last"] is None, raw


# ---- 2. per-element Live in the app ----


async def test_ticker_and_updates_with_globe_off_runs_only_those_timers():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("K")
        await pilot.press("U")
        await settle(pilot, 2)
        s = states(app)
        assert s["tape"] and all(s[n] for n in POLLS) and s["clock"] and not s["spin"], s
        assert app.live == {"globe": False, "ticker": True, "updates": True} and app.live_state() == "partial"
        saved = app.settings.load()
        assert (saved["live_globe"], saved["live_ticker"], saved["live_updates"]) == (False, True, True)
        assert "◈ LIVE" in screen(app)
        assert "Live: Auto-Updates ON. Active: Stock Ticker, Auto-Updates." in activity(app)
        dv = app.query_one(DeskView)
        lon = dv.view.lon
        app._desk_spin_step()  # globe off: the spin job does nothing
        assert dv.view.lon == lon


@pytest.mark.parametrize("key,element,timers", [("G", "globe", ("spin",)), ("K", "ticker", ("tape",)),
                                                 ("U", "updates", POLLS)])
async def test_each_element_alone(key, element, timers):
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press(key)
        await settle(pilot, 2)
        s = states(app)
        running = {n for n, on in s.items() if on}
        assert running == {"clock", *timers}, s
        assert app.live_state() == "partial" and app.live[element] is True
        await pilot.press(key)
        await settle(pilot, 2)
        assert {n for n, on in states(app).items() if on} == {"clock"} and app.live_state() == "off"
        assert "◇ LIVE" in screen(app)


async def test_element_keys_only_on_the_desk():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("3")
        await settle(pilot, 1)
        for key in ("G", "K", "U", "L"):
            await pilot.press(key)
        await settle(pilot, 1)
        assert app.live_state() == "off"


async def test_master_L_remembers_and_restores_the_last_combination():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("L")  # nothing remembered yet: all three
        await settle(pilot, 2)
        assert app.live_state() == "full" and "◆ LIVE" in screen(app) and "Live Mode ON (all)." in activity(app)
        await pilot.press("G")  # globe off: ticker + updates
        await settle(pilot, 2)
        assert app.live_state() == "partial"
        await pilot.press("L")  # any on: all off, the mix is remembered
        await settle(pilot, 2)
        assert app.live_state() == "off" and "Live Mode OFF. Active: none." in activity(app)
        assert app.settings.load()["live_last"] == ["live_ticker", "live_updates"]
        await pilot.press("L")
        await settle(pilot, 2)
        assert app.live == {"globe": False, "ticker": True, "updates": True}
        assert "Live Mode ON (partial). Active: Stock Ticker, Auto-Updates." in activity(app)
        # the chip is the same master switch
        await pilot.click("#chip-live")
        await settle(pilot, 2)
        assert app.live_state() == "off"
        await pilot.click("#chip-live")
        await settle(pilot, 2)
        assert app.live == {"globe": False, "ticker": True, "updates": True}


async def test_remembered_combination_survives_a_restart():
    st = raw_settings({"theme": "huddy", "theme_migrated_020": True, "live_last": ["live_globe"]})
    app = NuzeHubApp(DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.live_state() == "off"
        await pilot.press("L")
        await settle(pilot, 2)
        assert app.live == {"globe": True, "ticker": False, "updates": False}


async def test_view_menu_lists_master_and_three_toggles():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        view = next(m for m in app.menus if m.title == "View")
        items = {i.label: i for i in view.items() if not i.is_separator}
        names = ("Live Mode (All)", "Live: Globe Spin", "Live: Stock Ticker", "Live: Auto-Updates")
        assert all(n in items for n in names) and [items[n].key for n in names] == ["L", "G", "K", "U"]
        assert not any(items[n].checked() for n in names)
        app.run_menu_action(items["Live: Stock Ticker"].action)
        await settle(pilot, 2)
        assert items["Live: Stock Ticker"].checked() and not items["Live Mode (All)"].checked()
        app.run_menu_action(items["Live Mode (All)"].action)  # partial -> off
        await settle(pilot, 2)
        assert app.live_state() == "off"
        app.run_menu_action(items["Live Mode (All)"].action)  # restores the ticker only
        await settle(pilot, 2)
        assert app.live == {"globe": False, "ticker": True, "updates": False}
        app.set_live(True)
        await settle(pilot, 1)
        assert all(items[n].checked() for n in names)


async def test_partial_live_auto_pauses_and_resumes():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live_elements({"globe": False, "ticker": True, "updates": True})
        await settle(pilot, 1)
        app.action_help()
        await settle(pilot, 1)
        s = states(app)
        assert not s["tape"] and not s["spin"] and all(s[n] for n in POLLS)
        await pilot.press("escape")
        await settle(pilot, 2)
        assert states(app)["tape"]
        app.on_app_blur()
        assert not states(app)["tape"]
        app.on_app_focus()
        assert states(app)["tape"]
        await pilot.press("2")
        await settle(pilot, 1)
        assert not any(states(app).values())
        await pilot.press("0")
        await settle(pilot, 2)
        assert states(app)["tape"] and not states(app)["spin"]


async def test_manual_r_refresh_with_updates_off():
    backend = DemoBackend()
    calls = {"n": 0}
    real = backend.fetch_news

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    backend.fetch_news = counted  # type: ignore[method-assign]
    app = make(backend=backend)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live_elements({"globe": True, "ticker": True, "updates": False})
        start = calls["n"]
        await pilot.press("r")
        await settle(pilot, 6)
        assert calls["n"] > start


# ---- 3. smoother cadence ----


def test_speed_presets_match_the_addendum():
    from nuzehub_tui.ui.app import SPEEDS

    assert SPEEDS == {"eco": (1 / 3, 3.0, 0.28), "smooth": (0.125, 1.5, 0.14), "ultra": (1 / 12, 1.0, 0.08)}
    assert 0.25 <= SPEEDS["eco"][2] <= 0.30  # eco keeps the original 0.2.2 brief cadence (3 fps, 1 cell / 0.28 s)


def test_speed_and_interval_settings_validate(tmp_path):
    st = Settings(tmp_path / "s")
    assert st.load()["live_speed"] == "smooth" and st.load()["live_update_interval"] == 30
    st.root.mkdir(parents=True)
    for raw, speed, every in (('{"live_speed": "ultra", "live_update_interval": 45}', "ultra", 45),
                              ('{"live_speed": "warp", "live_update_interval": 2}', "smooth", 5),
                              ('{"live_speed": 3, "live_update_interval": 9000}', "smooth", 600),
                              ('{"live_update_interval": "60"}', "smooth", 30), ('{"live_update_interval": true}', "smooth", 30),
                              ('{"live_update_interval": 60.0}', "smooth", 60), ('{"live_update_interval": 7.5}', "smooth", 30)):
        st.path.write_text(raw, "utf-8")
        assert (st.load()["live_speed"], st.load()["live_update_interval"]) == (speed, every), raw


async def test_live_speed_cycles_persists_and_reconfigures_timers():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live(True)
        await settle(pilot, 1)
        assert app.live_speed == "smooth" and app._desk_timers["spin"]._interval == 0.125
        old = app._desk_timers["spin"]
        await pilot.press("S")
        await settle(pilot, 1)
        assert app.live_speed == "ultra" and app.settings.load()["live_speed"] == "ultra"
        assert app._desk_timers["spin"] is not old and abs(app._desk_timers["spin"]._interval - 1 / 12) < 1e-9
        assert app._desk_timers["tape"]._interval == 0.08 and app.spin_step == 1.0
        assert states(app)["spin"] and states(app)["tape"]  # the new timers run while live
        assert "Live Speed: Ultra" in activity(app)
        await pilot.press("S")
        await settle(pilot, 1)
        assert app.live_speed == "eco" and app._desk_timers["tape"]._interval == 0.28 and app.spin_step == 3.0
        dv = app.query_one(DeskView)
        for name in ("spin", "tape"):
            app._desk_timers[name].pause()
        lon = dv.view.lon
        app._desk_spin_step()
        assert round((dv.view.lon - lon) % 360, 6) == 3.0
        view = next(m for m in app.menus if m.title == "View")
        assert any(i.label == "Live Speed: Eco" and i.key == "S" for i in view.items())
        app.set_live(False)
        await settle(pilot, 1)
        app.set_live_speed("smooth")
        assert not states(app)["spin"] and not states(app)["tape"]  # re-created timers stay paused while off


async def test_update_interval_cycles_persists_and_reconfigures_polls():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.live_update_interval == 30
        assert all(app._desk_timers[n]._interval == 30.0 for n in ("news", "markets", "hazards", "instance"))
        await pilot.press("U")
        await pilot.press("I")
        await settle(pilot, 1)
        assert app.live_update_interval == 60 and app.settings.load()["live_update_interval"] == 60
        assert all(app._desk_timers[n]._interval == 60.0 for n in ("news", "markets", "hazards", "instance"))
        assert app._desk_timers["alerts"]._interval == 7.0 and all(states(app)[n] for n in POLLS)
        for expected in (120, 15, 30):
            app.action_cycle_update_interval()
            assert app.live_update_interval == expected
        app.set_update_interval(45)
        app.action_cycle_update_interval()
        assert app.live_update_interval == 60
        app.set_update_interval(1)
        assert app.live_update_interval == 5
        view = next(m for m in app.menus if m.title == "View")
        assert any(i.label == "Auto-Update: every 5s" and i.key == "I" for i in view.items())


async def test_saved_speed_and_interval_are_used_at_start():
    st = raw_settings({"theme": "huddy", "theme_migrated_020": True, "live_speed": "eco", "live_update_interval": 120})
    app = NuzeHubApp(DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert abs(app._desk_timers["spin"]._interval - 1 / 3) < 1e-9 and app._desk_timers["news"]._interval == 120.0


async def test_one_cell_and_one_small_step_per_tick():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live(True)
        await settle(pilot, 1)
        for name in ("spin", "tape"):
            app._desk_timers[name].pause()
        dv = app.query_one(DeskView)
        lon = dv.view.lon
        app._desk_spin_step()
        assert round((dv.view.lon - lon) % 360, 6) == NuzeHubApp.SPIN_STEP
        assert dv.tape_offset == 0  # biggest movers first
        app._desk_tape_step()
        assert dv.tape_offset == 1
        await pilot.click("#desk-tape")
        await pilot.press("home")
        assert dv.tape_offset == 0


def test_fast_globe_rings_match_the_projection():
    from nuzehub_tui import mapgfx

    for lon in (-170.0, -33.3, 0.0, 10.0, 47.5, 179.9):
        for lat in (20.0, -35.0):
            view = mapgfx.View("tactical", lon, lat)
            proj = mapgfx._project(view, 92, 60)
            expected = []
            for cid, polys in mapgfx.world():
                for poly in polys:
                    for ring in poly:
                        pts = [proj(a, b) for a, b in ring]
                        if any(f for _, _, f in pts):
                            expected.append((cid, [(x, y) for x, y, _ in pts]))
            assert mapgfx._rings(view, 92, 60) == expected


# ---- 4. tab transitions ----


async def test_rapid_tab_cycling_keeps_data_and_ends_clean():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, 4)
        stories, quotes = len(app.stories), len(app.quotes)
        assert stories and quotes
        for _ in range(4):
            for key in "01234560":
                await pilot.press(key)
        for key in "6543210":
            await pilot.press(key)
        await settle(pilot, 2)
        assert app._active() == "tab-desk" and app.query_one("#main-tabs").border_title == "NuzeHub: Desk"
        assert len(app.stories) == stories and len(app.quotes) == quotes  # nothing wiped or re-fetched
        for n, tab in enumerate(TABS):
            await pilot.press(str(n))
            await pilot.pause()
            assert app._active() == tab
        await settle(pilot, 2)
        assert "Watchlist" not in str(app.query_one("#sidebar").border_title) or app._active() == "tab-markets"


async def test_no_op_title_rewrites_on_same_tab_and_clock_ticks():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("2")
        await settle(pilot, 2)
        tabs, side = app.query_one("#main-tabs"), app.query_one("#sidebar")
        before = (id(tabs._border_title), id(tabs._border_subtitle), id(side._border_title), id(side._border_subtitle))
        await pilot.press("2")  # the same tab again
        await settle(pilot, 1)
        app._render_list()
        app._update_status()
        app._render_markets()
        after = (id(tabs._border_title), id(tabs._border_subtitle), id(side._border_title), id(side._border_subtitle))
        assert before == after
        await pilot.press("0")
        await settle(pilot, 1)
        title = id(tabs._border_title)
        for _ in range(3):
            app._desk_clock_tick()
        assert id(tabs._border_title) == title


async def test_desk_paints_once_on_return_only_when_stale():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        dv = app.query_one(DeskView)
        calls = {"n": 0}
        real = dv.render_all

        def counted() -> None:
            calls["n"] += 1
            real()

        dv.render_all = counted  # type: ignore[method-assign]
        await pilot.press("1")
        await settle(pilot, 1)
        await pilot.press("0")
        await settle(pilot, 1)
        assert calls["n"] == 0  # nothing changed while hidden: the Desk is reused as it was
        await pilot.press("1")
        await settle(pilot, 1)
        app._render_desk()  # e.g. a refresh while hidden
        assert calls["n"] == 0
        await pilot.press("0")
        await settle(pilot, 1)
        assert calls["n"] == 1


# ---- 5. Markets graphs ----


@pytest.mark.parametrize("theme", ["huddy", "github-dark"])
async def test_markets_rows_have_coloured_sparklines_and_arrows(theme):
    app = make(theme)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("2")
        await settle(pilot, 2)
        p = app.desk_palette()
        rows = app._market_rows()
        good = [q for q in app.quotes if not q.get("error")]
        assert rows and good
        seen = set()
        for q, row in zip(app.quotes, rows, strict=True):
            if q.get("error"):
                continue
            cp = float(q.get("changePct") or 0)
            glyph, colour = ("▲", p.success) if cp > 0 else ("▼", p.error) if cp < 0 else ("–", p.muted)
            assert glyph in row.plain
            styles = {str(sp.style) for sp in row.spans}
            assert colour in styles
            assert any(ch in row.plain for ch in "▁▂▃▄▅▆▇█")  # the trend sparkline
            seen.add(glyph)
        assert {"▲", "▼"} <= seen
        text = screen(app)
        assert "▲" in text and "▼" in text


def test_markets_colours_meet_contrast():
    for theme in ("huddy", "github-dark"):
        p = themes.get(theme)
        for role in (p.success, p.error, p.muted):
            assert contrast_ratio(role, p.background) >= 4.5, (theme, role)


@pytest.mark.parametrize("system", ["256", "standard"])
async def test_markets_colours_use_the_256_16_fallback(system):
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.colour_system = system
        mapped = fallback_colours("huddy", system)
        assert mapped is not None
        up = next(q for q in app.quotes if not q.get("error") and float(q.get("changePct") or 0) > 0)
        down = next(q for q in app.quotes if not q.get("error") and float(q.get("changePct") or 0) < 0)
        assert app._trend(up)[1] == mapped["up"]
        assert app._trend(down)[1].split(" on ")[-1] == mapped["down"]
