"""0.2.0 §7.5 feature pilots and §7.6 state flows for the Desk, on the demo backend (synthetic data) with a
controllable clock."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import settle
from nuzehub_tui.client import NuzeHubError
from nuzehub_tui.demo import DESK_NOW_MS, DemoBackend
from nuzehub_tui.settings import TABS, Settings
from nuzehub_tui.ui.app import NuzeHubApp
from nuzehub_tui.ui.deskview import ROTATE_STEP, DeskView, InspectorModal, MapView, Tape, Toggle
from uihelp import screen_lines

THEMES = ("huddy", "github-dark")


class Clock:
    def __init__(self) -> None:
        self.t = float(DESK_NOW_MS)

    def __call__(self) -> float:
        return self.t


def make(theme: str = "huddy", backend: DemoBackend | None = None, clock: Clock | None = None) -> NuzeHubApp:
    st = Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]))
    st.save({"theme": theme, "theme_migrated_020": True})
    return NuzeHubApp(backend or DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00", now=clock)


def screen(app) -> str:
    return "\n".join(screen_lines(app))


def all_timers(app) -> int:
    return len(app._timers) + sum(len(w._timers) for w in app.query("*")) + sum(len(s._timers) for s in app.screen_stack)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", [(80, 24), (120, 40), (200, 50)])
async def test_desk_panels(theme, size):
    app = make(theme)
    async with app.run_test(size=size) as pilot:
        await settle(pilot)
        assert app._active() == "tab-desk" and app.theme == theme
        text = screen(app)
        for needle in ("SITREP", "ALERTS", "PRICE MOVES", "NVDA +1.20%", "STORIES", "MKT"):
            assert needle in text, (needle, size)
        if size[0] >= 100:
            for needle in ("LAYERS", "INTEL FEED", "WATCHLIST", "TASKS", "FOCUS", "FEEDS", "UTC"):
                assert needle in text, (needle, size)
            assert "STORIGEO" not in text
        dv = app.query_one(DeskView)
        assert dv.narrow == app.query_one("#desk-grid").has_class("-narrow") == (size[0] < 100)
        assert len(dv.intel_rows) == 5 and len(dv.quote_rows) == 3


async def test_layers_alt_keys_and_glyphs():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        heat = app.query_one("#layer-heat", Toggle)
        assert heat.value and heat.render().plain.startswith("■ NEWS HEAT")
        await pilot.press("alt+1")
        await settle(pilot, 1)
        assert not heat.value and heat.render().plain.startswith("□")
        assert app.query_one(DeskView).map_layers["heat"] is False
        await pilot.press("alt+1")
        await settle(pilot, 1)
        assert heat.value
        radios = [t for t in app.query(Toggle) if t.radio]
        assert {t.render().plain[0] for t in radios} == {"◆", "◇"}


async def test_map_inspector_filter_and_escape():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        dv = app.query_one(DeskView)
        assert dv.mdata.ranked, "demo has a located story"
        app.query_one(MapView).focus()
        await pilot.press("right")
        await settle(pilot, 1)
        assert dv.selected == dv.mdata.ranked[0][0].id
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, InspectorModal)
        await pilot.press("c")
        await settle(pilot)
        assert len(app.screen_stack) == 1 and dv.filter == dv.selected
        assert 0 < len(dv.intel_rows) < 5
        await pilot.press("escape")
        await settle(pilot, 1)
        assert dv.filter is None and len(dv.intel_rows) == 5


async def test_narrow_map_toggle():
    app = make()
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        mv = app.query_one(MapView)
        assert mv.collapsed and "press m" in str(app.query_one("#map-note").render())
        await pilot.press("m")
        await settle(pilot)
        assert not mv.collapsed
        await pilot.press("m")
        await settle(pilot)
        assert mv.collapsed


async def test_focus_chip_is_the_only_write_and_merges():
    backend = DemoBackend()
    before = backend.load_instance()
    clock = Clock()
    app = make(backend=backend, clock=clock)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        calls = list(backend.calls)
        app.query_one("#chip-25").focus()
        await pilot.press("enter")
        await settle(pilot)
        after = backend.load_instance()
        assert after["desk"]["focus"] == {"taskId": None, "label": "Focus", "endsAt": DESK_NOW_MS + 25 * 60_000}
        rest = {k: v for k, v in after["desk"].items() if k != "focus"}
        assert rest == {k: v for k, v in before["desk"].items() if k != "focus"}
        assert after.get("brain") == before.get("brain")
        writes = [c for c in backend.calls[len(calls):] if c.startswith("save")]
        assert len(writes) == 1
        assert "25:00" in screen(app)
        clock.t += 61_000
        app._desk_clock_tick()
        await settle(pilot, 1)
        assert "23:59" in screen(app)


async def test_enter_on_intel_and_watch_opens_news_and_markets():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.query_one("#intel-list").focus()
        await pilot.press("down", "enter")
        await settle(pilot)
        assert app._active() == "tab-news"
        await pilot.press("escape")
        await pilot.press("0")
        await settle(pilot)
        app.query_one("#watch-list").focus()
        await pilot.press("down", "enter")
        await settle(pilot)
        assert app._active() == "tab-markets"


async def test_tape_moves_only_when_stepped_biggest_movers_first():
    clock = Clock()
    app = make(clock=clock)
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        dv = app.query_one(DeskView)
        assert app.live_mode is False and app.desk_timer_states()["tape"] is False  # 0.2.1: Live Mode off by default
        first_line = app.query_one(Tape)._line.plain
        clock.t += 60_000
        await settle(pilot, 2)
        assert dv.tape_offset == 0 and app.query_one(Tape)._line.plain == first_line  # time alone never moves it
        starts = dv._tape_starts
        assert len(starts) > 2
        await pilot.click("#desk-tape")
        await settle(pilot)
        assert app.focused is app.query_one(Tape)
        await pilot.press("right")
        assert dv.tape_offset == starts[1]
        await pilot.press("right", "left")
        assert dv.tape_offset == starts[1]
        await pilot.press("left", "left")
        assert dv.tape_offset == starts[-1]  # wraps
        await pilot.press("home")
        assert dv.tape_offset == 0
        tape = app.query_one(Tape)
        tape.on_mouse_scroll_down(__import__("types").SimpleNamespace(stop=lambda: None))
        assert dv.tape_offset == starts[1]
        tape.on_mouse_scroll_up(__import__("types").SimpleNamespace(stop=lambda: None))
        assert dv.tape_offset == 0


async def test_map_moves_only_by_hand_no_spin():
    clock = Clock()
    app = make(clock=clock)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        dv, mv = app.query_one(DeskView), app.query_one(MapView)
        assert not app.query("#chip-spin") and not hasattr(dv, "toggle_spin") and not hasattr(dv, "_spin")
        renders, lon = mv.render_count, dv.view.lon
        for _ in range(3):
            clock.t += 5_000  # same minute: nothing moves on its own
            await settle(pilot, 2)
        assert mv.render_count == renders and dv.view.lon == lon
        await pilot.click("#chip-rot-right")
        await settle(pilot)
        assert dv.view.lon == lon + ROTATE_STEP
        await pilot.click("#chip-rot-left")
        await settle(pilot)
        assert dv.view.lon == lon
        mv.focus()
        await pilot.press("shift+right", "shift+right")
        assert dv.view.lon == lon + 2 * ROTATE_STEP
        lat = dv.view.lat
        await pilot.press("shift+up")
        assert dv.view.lat == lat + 10
        mv.on_mouse_scroll_up(__import__("types").SimpleNamespace(stop=lambda: None))
        assert dv.view.lon == lon + ROTATE_STEP
        await settle(pilot)
        assert mv.render_count > renders
        assert "rotate" in str(app.query_one("#map-note").render()) and "spin" not in str(app.query_one("#map-note").render())
        await pilot.press("home")
        assert dv.view.lon == 10.0 and dv.selected is None


async def test_idle_clock_tick_repaints_only_what_changed():
    clock = Clock()
    app = make(clock=clock)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        box = app.query_one("#main-tabs")
        hud = app.query_one("#hud")
        calls = {"refresh": 0, "hud": 0}
        real_refresh, real_update = box.refresh, hud.update

        def spy_refresh(*a, **k):
            calls["refresh"] += 1
            return real_refresh(*a, **k)

        def spy_update(*a, **k):
            calls["hud"] += 1
            return real_update(*a, **k)

        box.refresh, hud.update = spy_refresh, spy_update
        app._desk_clock_tick()
        app._desk_clock_tick()  # same second: nothing changed
        assert calls == {"refresh": 0, "hud": 0}
        clock.t += 1000
        app._desk_clock_tick()  # next second: only the HUD clock row
        assert calls == {"refresh": 0, "hud": 1}
        assert app._desk_clock() in str(hud.render())


# ---- §7.6 state flows ----


async def test_fast_tab_switching_stacks_no_timers_and_hidden_pauses():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        app.set_live(True)  # 0.2.1: with Live Mode on every Desk timer runs while the Desk shows
        states = app.desk_timer_states()
        assert len(states) == 8 and all(states.values())
        count = all_timers(app)
        for _ in range(3):
            for key in "01234560":
                await pilot.press(key)
        await settle(pilot)
        assert all_timers(app) == count
        assert app._active() == "tab-desk" and all(app.desk_timer_states().values())
        await pilot.press("1")
        await settle(pilot, 1)
        assert not any(app.desk_timer_states().values())  # hidden: clock, alerts and polls paused
        await pilot.press("0")
        await settle(pilot, 1)
        assert all(app.desk_timer_states().values())
        app.action_help()
        await settle(pilot, 1)
        await pilot.press("escape")
        await settle(pilot, 1)
        assert all_timers(app) == count  # a dialog round trip stacks nothing either


async def test_legacy_static_tape_setting_is_ignored():
    st = Settings(Path(os.environ["NUZEHUB_TUI_STATE_DIR"]))
    st.root.mkdir(parents=True, exist_ok=True)
    st.path.write_text('{"theme": "github-dark", "theme_migrated_020": true, "static_tape": true}', "utf-8")
    assert "static_tape" not in st.load() and st.load()["theme"] == "github-dark"
    app = NuzeHubApp(DemoBackend(), settings=st, demo=True, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.theme == "github-dark" and app.live_mode is False and app.desk_timer_states()["clock"] is True


async def test_stale_then_offline_then_reconnect():
    backend, clock = DemoBackend(), Clock()
    app = make(backend=backend, clock=clock)
    real = backend.get_markets
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        dv = app.query_one(DeskView)
        rows = len(dv.quote_rows)

        def down(*a, **k):
            raise NuzeHubError("connection refused")

        backend.get_markets = down  # type: ignore[method-assign]
        clock.t += 5 * 60_000
        app._desk_refresh_markets()
        await settle(pilot)
        assert len(dv.quote_rows) == rows  # kept, not blanked
        assert "stale 5m" in str(app.query_one("#desk-watch").border_subtitle)
        backend.get_markets = real  # type: ignore[method-assign]
        await pilot.press("r")
        await settle(pilot, 6)
        assert len(dv.quote_rows) == rows and "stale" not in str(app.query_one("#desk-watch").border_subtitle)
        assert len(dv.intel_rows) == 5  # no duplicated rows


async def test_offline_at_start_then_r_recovers():
    backend = DemoBackend()
    real = {n: getattr(backend, n) for n in ("get_markets", "get_hazards", "fetch_news")}

    def down(*a, **k):
        raise NuzeHubError("connection refused")

    for n in real:
        setattr(backend, n, down)
    app = make(backend=backend)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert "offline" in str(app.query_one("#desk-watch").border_subtitle)
        for n, f in real.items():
            setattr(backend, n, f)
        await pilot.press("r")
        await settle(pilot, 6)
        dv = app.query_one(DeskView)
        assert len(dv.quote_rows) == 3 and len(dv.intel_rows) == 5
        assert "offline" not in str(app.query_one("#desk-watch").border_subtitle)


async def test_theme_switch_while_the_desk_runs():
    app = make()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        assert app.desk_timer_states()["clock"]
        for theme in ("github-dark", "huddy", "github-dark"):
            app._apply_theme(theme)
            await settle(pilot, 2)
            assert app.theme == theme and app.desk_timer_states()["clock"]
        assert app.settings.load()["theme"] == "github-dark"


async def test_resize_while_the_map_shows():
    app = make()
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot)
        for size in ((120, 40), (80, 24), (200, 50), (99, 30), (100, 30)):
            await pilot.resize_terminal(*size)
            await settle(pilot)
            lines = screen_lines(app)
            assert len(lines) == size[1] and all(len(line) == size[0] for line in lines)
            assert app.query_one(MapView).collapsed == (size[0] < 100)


def test_tabs_start_with_the_desk():
    assert TABS[0] == "tab-desk" and len(TABS) == 7
