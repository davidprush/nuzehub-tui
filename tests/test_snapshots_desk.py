"""0.2.0 §7.2 Desk snapshots: 80x24, 120x40, 200x50, the Inspector (see-through), stale, offline and empty, each in
HUDdy and GitHub Dark. The demo clock is fixed in headless runs, so the tape, alerts and clocks are still."""

from __future__ import annotations

import pytest

from nuzehub_tui.client import NuzeHubError
from nuzehub_tui.demo import DESK_NOW_MS
from uihelp import demo_app, settle

THEMES = ["huddy", "github-dark"]


def _down(*a, **k):
    raise NuzeHubError("connection refused")



@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", [(80, 24), (120, 40), (200, 50)])
def test_desk(snap_compare, size, theme):
    async def before(pilot):
        await settle(pilot)

    assert snap_compare(demo_app(theme=theme), terminal_size=size, run_before=before)


@pytest.mark.parametrize("theme", THEMES)
def test_desk_inspector(snap_compare, theme):
    async def before(pilot):
        await settle(pilot)
        pilot.app.query_one("DeskView").open_inspector()
        await settle(pilot)

    assert snap_compare(demo_app(theme=theme), terminal_size=(120, 40), run_before=before)


@pytest.mark.parametrize("theme", THEMES)
def test_desk_stale(snap_compare, theme):
    clock = [float(DESK_NOW_MS)]
    app = demo_app(theme=theme, now=lambda: clock[0])

    async def before(pilot):
        await settle(pilot)
        for name in ("get_markets", "get_hazards", "fetch_news"):
            setattr(app.backend, name, _down)
        clock[0] += 5 * 60_000
        await app._desk_markets()  # one after another, so the activity lines keep one order
        await app._desk_hazards()
        await app._desk_news()
        await settle(pilot, 4)

    assert snap_compare(app, terminal_size=(120, 40), run_before=before)


@pytest.mark.parametrize("theme", THEMES)
def test_desk_offline(snap_compare, theme):
    app = demo_app(theme=theme)
    for name in ("get_markets", "get_hazards", "fetch_news"):
        setattr(app.backend, name, _down)

    async def before(pilot):
        await settle(pilot, 6)
        # 0.2.3 test-only fix: the start-up workers fail at once, so their ERROR lines arrived in any order (flaky in
        # 0.2.2 too); keep every line and its slot, and put only the ERROR lines in one fixed (sorted) order.
        lines = list(app._activity)
        slots = [i for i, line in enumerate(lines) if " ERROR " in line]
        for i, line in zip(slots, sorted(lines[i] for i in slots), strict=True):
            lines[i] = line
        app._activity.clear()
        app._activity.extend(lines)
        app._update_status()
        await settle(pilot)

    assert snap_compare(app, terminal_size=(120, 40), run_before=before)


@pytest.mark.parametrize("theme", THEMES)
def test_desk_empty(snap_compare, theme):
    app = demo_app(theme=theme)
    b = app.backend
    b.fetch_news = lambda urls: {"stories": [], "errors": []}
    b.get_markets = lambda symbols, rng, sources=None: {"quotes": []}
    b.get_hazards = lambda window, kinds=None: {"results": []}
    inst = b.instance
    inst["desk"] = {k: v for k, v in (inst.get("desk") or {}).items()
                    if k not in ("tasks", "events", "brief", "automationNotices", "focus")}

    async def before(pilot):
        await settle(pilot, 6)

    assert snap_compare(app, terminal_size=(120, 40), run_before=before)
