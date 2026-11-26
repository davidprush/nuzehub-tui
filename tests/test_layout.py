"""Border fit at 80x24, 120x40 and 200x50; button widths at 120x40, 100x30, 80x24 and 70x24 (SSHush checks)."""

from __future__ import annotations

import pytest
from textual.widgets import Button

from nuzehub_tui.ui.menubar import MenuScreen
from uihelp import DIALOG_ACTIONS, TABS, demo_app, open_article, screen_lines, settle

CORNERS = ("╭", "╮", "╰", "╯")


def _check_borders(app) -> int:
    screen = app.screen
    lines = screen_lines(app)
    width, height = app.size
    assert all(len(line) == width for line in lines), "a row is wider or narrower than the screen"
    checked = 0
    for widget in screen.query("*"):
        if not widget.display or widget.styles.border_top[0] != "round":
            continue
        region = widget.region
        if region.width < 2 or region.height < 2:
            continue
        corners = ((region.x, region.y), (region.right - 1, region.y),
                   (region.x, region.bottom - 1), (region.right - 1, region.bottom - 1))
        for glyph, (x, y) in zip(CORNERS, corners, strict=True):
            if not (0 <= x < width and 0 <= y < height):
                continue
            try:
                top, _ = screen.get_widget_at(x, y)
            except Exception:  # noqa: BLE001 - clipped by a scroll view
                continue
            if top is not widget:
                continue
            assert lines[y][x] == glyph, (widget, glyph, x, y, lines[y])
        checked += 1
    return checked


@pytest.mark.parametrize("theme", ["huddy", "github-dark"])  # 0.2.0: both required themes
@pytest.mark.parametrize("size", [(80, 24), (120, 40), (200, 50)])
async def test_every_bordered_row_fits_its_border(tmp_path, size, theme):
    app = demo_app(tmp_path / "s", theme=theme)
    async with app.run_test(size=size) as pilot:
        await settle(pilot)
        await open_article(app, pilot)
        total = 0
        for tab in TABS:
            app.action_show_tab(tab)
            await settle(pilot)
            total += _check_borders(app)
        for index in range(len(app.menus)):
            app.action_open_menu(index)
            await settle(pilot)
            assert isinstance(app.screen, MenuScreen)
            total += _check_borders(app)
            await pilot.press("escape")
            await settle(pilot)
        for action in DIALOG_ACTIONS:
            getattr(app, f"action_{action}")()
            await settle(pilot, 4)
            assert len(app.screen_stack) == 2, action
            total += _check_borders(app)
            await pilot.press("escape")
            await settle(pilot)
            assert len(app.screen_stack) == 1, action
        assert total > (10 if size[1] < 30 else 20)  # short screens use frameless one-row buttons


def _assert_content_sized(app) -> int:
    width = app.size.width
    n = 0
    for button in app.screen.query(Button):
        if not (button.display and button.size.width > 0 and button.region.height > 0):
            continue
        label = str(button.label)
        assert button.size.width <= len(label) + 6, (button.id, label, button.size.width, width)
        assert button.region.x >= 0 and button.region.right <= width, (button.id, button.region, width)
        assert str(button.styles.width) == "auto", button.id
        n += 1
    return n


@pytest.mark.parametrize("size", [(120, 40), (100, 30), (80, 24), (70, 24)])
async def test_action_buttons_match_their_labels(tmp_path, size):
    app = demo_app(tmp_path / "s")
    async with app.run_test(size=size) as pilot:
        await settle(pilot)
        await open_article(app, pilot)
        tabs = app.query_one("#main-tabs")
        assert tabs.region.right <= size[0]
        seen = 0
        for sidebar in (None, False):
            if sidebar is not None:
                app._sidebar_choice = sidebar
                app._apply_sidebar(size[0])
                app._fit_rows()
                await settle(pilot)
            for tab in TABS:
                app.action_show_tab(tab)
                await settle(pilot)
                seen += _assert_content_sized(app)
        for action in DIALOG_ACTIONS:
            getattr(app, f"action_{action}")()
            await settle(pilot, 4)
            seen += _assert_content_sized(app)
            await pilot.press("escape")
            await settle(pilot)
        assert seen > 10


@pytest.mark.parametrize("size", [(80, 24), (70, 24)])
async def test_usable_at_small_sizes(tmp_path, size):
    """Every tab's main controls are on screen at 80x24 and 70x24, and the HUD keeps two rows."""
    app = demo_app(tmp_path / "s")
    must = {"tab-news": "#news-open", "tab-markets": "#symbol-search", "tab-geo": "#win-24h",
            "tab-brain": "#note-filter", "tab-wiki": "#wiki-search", "tab-status": "#status-refresh"}
    async with app.run_test(size=size) as pilot:
        await settle(pilot)
        for tab, sel in must.items():
            app.action_show_tab(tab)
            await settle(pilot)
            w = app.query_one(sel)
            assert w.region.height > 0 and w.region.right <= size[0] and w.region.bottom <= size[1] - 2, (tab, w.region)
        lines = screen_lines(app)
        assert "CONN" in lines[-2] and "HELP" in lines[-1]
