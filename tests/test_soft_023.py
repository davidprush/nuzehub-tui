"""0.2.3 HUDdy Soft Contrast (Spec 1.0, Template 1.1 §2.1.1 / §2.5): the soft tokens, the hue guard, the contrast
pairs and the selection rule (dark text on the accent fill) checked on the rendered screen."""

from __future__ import annotations

import colorsys

import pytest
from rich.color import Color

from nuzehub_tui import themes
from nuzehub_tui.themes import contrast, get
from uihelp import demo_app, settle

OLD = {"background": "#03060b", "surface": "#0a1322", "panel": "#0f1c30", "foreground": "#d6e4f2"}
NEW = {"background": "#080e19", "surface": "#0d192c", "panel": "#112138", "foreground": "#c2cfdc"}
FROZEN = {"muted": "#7d93ad", "primary": "#5ee1ff", "accent": "#5ee1ff", "secondary": "#93a8bf", "success": "#3dffa8",
          "warning": "#ffb547", "error": "#ff5470"}
BRANCHES = ("#5ee1ff", "#3dffa8", "#ffb547", "#ff5470", "#93a8bf", "#7d93ad", "#3ef0ff", "#64d2ff")


def _hue(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def test_huddy_soft_tokens():
    p = get("huddy")
    assert {k: getattr(p, k) for k in NEW} == NEW
    assert p.name == "HUDdy" and themes.DEFAULT == "huddy" and themes.canonical("gods-eye-hud") == "huddy"
    assert themes.FALLBACK_256["huddy"] == dict(bg=16, surface=234, panel=236, pane=24, focus=81, text=189, muted=103,
                                                up=85, warn=215, down=203)


def test_huddy_soft_hue_guard():
    p = get("huddy")
    for k, old in OLD.items():
        d = abs(_hue(getattr(p, k)) - _hue(old))
        assert min(d, 360 - d) <= 2.0, (k, old, getattr(p, k))
    assert {k: getattr(p, k) for k in FROZEN} == FROZEN
    assert p.branches == BRANCHES
    gh = get("github-dark")
    assert (gh.background, gh.foreground, gh.primary) == ("#0d1117", "#e6edf3", "#4493f8")


PAIRS = [  # Spec 1.0 §2: (colour, on, minimum)
    ("#c2cfdc", "#080e19", 4.5), ("#c2cfdc", "#0d192c", 4.5), ("#c2cfdc", "#112138", 4.5), ("#d6e4f2", "#080e19", 4.5),
    ("#7d93ad", "#080e19", 4.5), ("#7d93ad", "#0d192c", 4.5), ("#7d93ad", "#112138", 4.5), ("#93a8bf", "#080e19", 4.5),
    ("#93a8bf", "#112138", 4.5), ("#5ee1ff", "#080e19", 4.5), ("#5ee1ff", "#0d192c", 4.5), ("#5ee1ff", "#112138", 4.5),
    ("#3dffa8", "#0d192c", 4.5), ("#ffb547", "#0d192c", 4.5), ("#ff5470", "#0d192c", 4.5), ("#3ef0ff", "#080e19", 4.5),
    ("#64d2ff", "#080e19", 4.5), ("#c2cfdc", "#142c3d", 4.5), ("#080e19", "#5ee1ff", 4.5), ("#080e19", "#3dffa8", 4.5),
    ("#080e19", "#ffb547", 4.5), ("#080e19", "#ff5470", 4.5), ("#1b2e41", "#0d192c", 1.2), ("#275e6d", "#080e19", 2.5),
    ("#0d1117", "#4493f8", 4.5),
]


@pytest.mark.parametrize(("colour", "on", "minimum"), PAIRS)
def test_huddy_soft_contrast(colour, on, minimum):
    assert contrast(colour, on) >= minimum


def test_huddy_buttons_and_no_white():
    p = get("huddy")
    tokens = themes.button_tokens(p)
    for k, v in tokens.items():
        assert v.lower() != "#ffffff", k
        if k.endswith("-text") or k.endswith("-text-hover"):
            if k != "btn-disabled-text":
                assert contrast(v, p.surface) >= 4.5, k
    assert "#ffffff" not in {v.lower() for v in p.textual().variables.values()}


def test_selection_tokens_rule():
    for p in themes.PALETTES:
        sel = themes.selection_tokens(p)
        if p.dark and contrast(p.background, p.primary) >= 4.5:
            assert sel == {"block-cursor-foreground": p.background, "block-cursor-background": p.primary}
        else:
            assert sel == {}
    assert themes.selection_tokens(get("huddy"))["block-cursor-foreground"] == "#080e19"
    assert themes.selection_tokens(get("github-dark")) == {"block-cursor-foreground": "#0d1117",
                                                          "block-cursor-background": "#4493f8"}


def _filled_cells(app, widget, fill: str) -> list:
    """Rendered styles of the cells inside ``widget`` whose background is ``fill`` (the screen as drawn)."""
    want = Color.parse(fill).triplet
    r = widget.region
    out = []
    for y in range(r.y, r.y + r.height):
        for x in range(r.x, r.x + r.width):
            st = app.screen.get_style_at(x, y)
            if st.bgcolor is not None and st.bgcolor.get_truecolor() == want:
                out.append(st)
    return out


@pytest.mark.parametrize("theme", ["huddy", "github-dark"])
async def test_selected_text_dark_on_accent(theme, tmp_path):
    p = get(theme)
    app = demo_app(tmp_path, theme=theme)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        tabs = app.query_one("#main-tabs Tabs")
        tabs.focus()
        await settle(pilot, 2)
        cells = _filled_cells(app, tabs, p.primary)
        assert cells, "no accent-filled focused tab"
        assert {c.color.get_truecolor() for c in cells if c.color} == {Color.parse(p.background).triplet}
        app.action_show_tab("tab-markets")
        await settle(pilot, 2)
        lst = app.query_one("#item-list")
        lst.focus()
        if lst.highlighted is None:
            lst.highlighted = 0
        await settle(pilot, 2)
        rows = _filled_cells(app, lst, p.primary)
        assert rows, "no accent-filled focused list row"
        assert {c.color.get_truecolor() for c in rows if c.color} == {Color.parse(p.background).triplet}
