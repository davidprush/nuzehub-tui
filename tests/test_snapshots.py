"""pytest-textual-snapshot pictures: every tab, 80x24 main, every menu, the gate, Cite/Save and the theme dropdown."""

from __future__ import annotations

import pytest

from uihelp import TABS, demo_app, open_article, settle


@pytest.mark.parametrize("tab", TABS)
def test_snapshot_tabs(snap_compare, tab):
    async def before(pilot):
        await settle(pilot)
        if tab == "tab-wiki":
            await open_article(pilot.app, pilot)
        pilot.app.action_show_tab(tab)
        await settle(pilot)

    assert snap_compare(demo_app(), terminal_size=(120, 40), run_before=before)


@pytest.mark.parametrize("size", [(80, 24), (70, 24)])
def test_snapshot_main_small(snap_compare, size):
    async def before(pilot):
        await settle(pilot)

    assert snap_compare(demo_app(), terminal_size=size, run_before=before)


@pytest.mark.parametrize("index", range(5))
def test_snapshot_menus(snap_compare, index):
    async def before(pilot):
        await settle(pilot)
        pilot.app.action_open_menu(index)
        await settle(pilot)

    assert snap_compare(demo_app(), terminal_size=(120, 40), run_before=before)


def test_snapshot_gate(snap_compare):
    async def before(pilot):
        await settle(pilot)

    assert snap_compare(demo_app(needs_key=True), terminal_size=(120, 40), run_before=before)


@pytest.mark.parametrize("action", ["wiki_cite", "wiki_save"])
def test_snapshot_cite_save(snap_compare, action):
    async def before(pilot):
        await settle(pilot)
        await open_article(pilot.app, pilot)
        getattr(pilot.app, f"action_{action}")()
        await settle(pilot, 4)

    assert snap_compare(demo_app(), terminal_size=(120, 40), run_before=before)


def test_snapshot_theme_dropdown(snap_compare):
    async def before(pilot):
        await settle(pilot)
        pilot.app.action_show_tab("tab-status")
        await settle(pilot)
        pilot.app.query_one("#theme-select").expanded = True
        await settle(pilot)

    assert snap_compare(demo_app(), terminal_size=(120, 40), run_before=before)


