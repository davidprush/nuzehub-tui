"""0.2.1 Live Mode: one switch (default OFF) for globe spin, ticker scroll and background updates, on the demo
backend (synthetic data) with a controllable clock."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import settle
from nuzehub_tui.demo import DemoBackend
from nuzehub_tui.settings import LIVE_KEYS, Settings
from nuzehub_tui.ui.app import NuzeHubApp
from nuzehub_tui.ui.deskview import DeskView, LiveChip
from test_desk_ui import Clock, make, screen

POLLS = ("alerts", "news", "markets", "hazards", "instance")
MOTION = ("spin", "tape")


def states(app) -> dict[str, bool]:
    return app.desk_timer_states()


def assert_off(app) -> None:
    s = states(app)
    assert s["clock"] is True
    assert not any(s[n] for n in POLLS + MOTION), s


def assert_on(app) -> None:
    assert all(states(app).values()), states(app)


def activity(app) -> str:
    return "\n".join(app._activity)


# ---- settings ----


def test_live_mode_defaults_off_and_persists(tmp_path):
    # 0.2.2: the one switch became three elements; a 0.2.1 file with live_mode true loads with all three on
    st = Settings(tmp_path / "s")
    assert not any(st.load()[k] for k in LIVE_KEYS)
    st.root.mkdir(parents=True)
    st.path.write_text('{"live_mode": true}', "utf-8")
    assert all(st.load()[k] for k in LIVE_KEYS)
    st.save({k: False for k in LIVE_KEYS})
    assert not any(st.load()[k] for k in LIVE_KEYS) and "live_mode" not in json.loads(st.path.read_text("utf-8"))


def test_legacy_static_tape_and_bad_values_load_off(tmp_path):
    st = Settings(tmp_path / "s")
    st.root.mkdir(parents=True)
    for raw in ('{"theme": "github-dark", "theme_migrated_020": true, "static_tape": true}',
                '{"theme": "github-dark", "static_tape": false, "live_mode": "yes"}',
                '{"live_mode": 1}', '{"live_mode": null}'):
        st.path.write_text(raw, "utf-8")
        data = st.load()
        assert not any(data[k] for k in LIVE_KEYS) and "static_tape" not in data


def test_intervals_match_the_brief():
    e = NuzeHubApp.DESK_EVERY
    # 0.2.2 addendum defaults: Auto-Update every 30 s, Live Speed "smooth" (+1.5 deg at 8 fps, 1 cell / 0.14 s)
    assert (e["news"], e["markets"], e["hazards"], e["instance"], e["alerts"]) == (30.0, 30.0, 30.0, 30.0, 7.0)
    assert e["spin"] == 0.125 and e["tape"] == 0.14 and e["clock"] == 1.0 and NuzeHubApp.SPIN_STEP == 1.5


# ---- OFF / ON timer states ----


async def test_default_off_only_the_clock_runs_and_nothing_moves():
    clock = Clock()
    app = make(clock=clock)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.live_mode is False
        assert_off(app)
        dv = app.query_one(DeskView)
        lon, off = dv.view.lon, dv.tape_offset
        app._desk_spin_step()
        app._desk_tape_step()
        clock.t += 60_000
        await settle(pilot, 2)
        assert dv.view.lon == lon and dv.tape_offset == off == 0
        assert "◇ LIVE" in screen(app)


async def test_hotkey_L_toggles_and_logs_and_saves():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("L")
        await settle(pilot, 2)
        assert app.live_mode is True and all(app.settings.load()[k] for k in LIVE_KEYS)
        assert_on(app)
        assert "Live Mode ON" in activity(app) and "◆ LIVE" in screen(app)
        await pilot.press("L")
        await settle(pilot, 2)
        assert app.live_mode is False and not any(app.settings.load()[k] for k in LIVE_KEYS)
        assert_off(app)  # all three stop at once
        assert "Live Mode OFF" in activity(app) and "◇ LIVE" in screen(app)


async def test_hotkey_only_on_the_desk():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("1")
        await settle(pilot, 1)
        await pilot.press("L")
        await settle(pilot, 1)
        assert app.live_mode is False


async def test_live_chip_click_toggles():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        chip = app.query_one(LiveChip)
        assert chip.region.width > 0
        await pilot.click("#chip-live")
        await settle(pilot, 2)
        assert app.live_mode is True
        assert_on(app)
        await pilot.click("#chip-live")
        await settle(pilot, 2)
        assert app.live_mode is False
        assert_off(app)


async def test_live_chip_fits_at_100_columns():
    app = make()
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        chip, actions = app.query_one(LiveChip), app.query_one("#layer-actions")
        assert actions.has_class("-tight") and chip.region.right <= actions.region.right and chip.region.width >= 6


async def test_view_menu_entry_shows_state_and_toggles():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        view = next(m for m in app.menus if m.title == "View")
        item = next(i for i in view.items() if i.label == "Live Mode (All)")
        assert item.key == "L" and item.checked() is False
        app.run_menu_action(item.action)
        await settle(pilot, 2)
        assert app.live_mode is True and item.checked() is True
        assert_on(app)
        app.run_menu_action(item.action)
        await settle(pilot, 2)
        assert app.live_mode is False
        assert_off(app)


async def test_saved_on_starts_live():
    st = Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]))
    st.root.mkdir(parents=True, exist_ok=True)
    st.path.write_text('{"theme_migrated_020": true, "live_mode": true}', "utf-8")  # a 0.2.1 file
    app = NuzeHubApp(DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.live_mode is True
        assert_on(app)


async def test_auto_pause_hidden_modal_unfocused():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live(True)
        await settle(pilot, 1)
        assert_on(app)
        # a modal: spin and tape pause, the polls keep running
        app.action_help()
        await settle(pilot, 1)
        s = states(app)
        assert not s["spin"] and not s["tape"] and all(s[n] for n in POLLS)
        await pilot.press("escape")
        await settle(pilot, 2)
        assert_on(app)
        # the terminal loses focus: same
        app.on_app_blur()
        s = states(app)
        assert not s["spin"] and not s["tape"] and all(s[n] for n in POLLS)
        app.on_app_focus()
        assert_on(app)
        # leaving the Desk: everything pauses
        await pilot.press("1")
        await settle(pilot, 1)
        assert not any(states(app).values())
        await pilot.press("0")
        await settle(pilot, 2)
        assert_on(app)
        # the step jobs themselves do nothing while paused conditions hold
        dv = app.query_one(DeskView)
        app.on_app_blur()
        lon = dv.view.lon
        app._desk_spin_step()
        assert dv.view.lon == lon
        app.on_app_focus()


async def test_spin_and_tape_steps_when_live():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        dv = app.query_one(DeskView)
        assert dv.tape_offset == 0  # biggest movers first
        app.set_live(True)
        await settle(pilot, 1)
        assert states(app)["spin"] and states(app)["tape"]
        for name in MOTION:  # drive the steps by hand below, so a real 0.5 s tick cannot race the asserts
            app._desk_timers[name].pause()
        lon = dv.view.lon
        app._desk_spin_step()
        assert round((dv.view.lon - lon) % 360, 6) == NuzeHubApp.SPIN_STEP
        before = app.query_one("#desk-tape")._line.plain
        app._desk_tape_step()
        app._desk_tape_step()
        assert dv.tape_offset == 2 and app.query_one("#desk-tape")._line.plain != before
        # manual controls still work while live
        await pilot.click("#desk-tape")
        await pilot.press("home")
        assert dv.tape_offset == 0
        app.query_one("#chip-reset").action_press()
        await settle(pilot, 1)
        assert dv.view.lon == 10.0


async def test_manual_r_refreshes_while_off():
    backend = DemoBackend()
    calls = {"news": 0}
    real = backend.fetch_news

    def counted(*a, **k):
        calls["news"] += 1
        return real(*a, **k)

    backend.fetch_news = counted  # type: ignore[method-assign]
    app = make(backend=backend)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        start = calls["news"]
        assert start >= 1  # the startup load still runs with Live Mode off
        assert_off(app)
        await pilot.press("r")
        await settle(pilot, 6)
        assert calls["news"] > start


async def test_toggle_on_refreshes_stale_sources():
    backend, clock = DemoBackend(), Clock()
    calls = {"markets": 0}
    real = backend.get_markets

    def counted(*a, **k):
        calls["markets"] += 1
        return real(*a, **k)

    backend.get_markets = counted  # type: ignore[method-assign]
    app = make(backend=backend, clock=clock)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        start = calls["markets"]
        clock.t += 10 * 60_000  # everything is now older than its Live interval
        await settle(pilot, 1)
        assert calls["markets"] == start  # OFF: no polling
        app.set_live(True)
        await settle(pilot, 6)
        assert calls["markets"] > start


async def test_sitrep_header_labels_do_not_touch():
    for size in ((80, 24), (120, 40), (200, 50)):
        app = make()
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            text = screen(app)
            assert "STORIES" in text and "STORIESGEO" not in text, size
            assert "STORIES GEO" in text.replace("  ", " ") or "STORIES " in text, size
