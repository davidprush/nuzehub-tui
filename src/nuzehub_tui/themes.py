"""Theme palettes from Dirlume 1.1.1, reused under its MIT license.

Copyright (c) 2026 Dirlume contributors.

Established themes use their published palettes. Pride, Lux Marble, Koi,
Starship, and Powerlevel10k are Dirlume originals. Names and semantic colors
are unchanged. See NOTICE and docs/THEMES.md.

0.2.0: the default is God's Eye HUD (the web desk's own palette, brief §0.1-0.2), the 23rd theme. A settings file
from before 0.2.0 is switched to it once (``Settings.migrate_theme``); after that a saved theme is never overridden.
0.2.2: that theme is now called HUDdy (id ``huddy``); its palette is unchanged. The old id ``gods-eye-hud`` is still
accepted wherever a theme id is read (``canonical``), so saved settings keep working.
GitHub Dark is the required second theme; 0.2.0 moves its primary to #4493f8 and muted to #8b949e (§0.3).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import cache
from typing import Any

DEFAULT = "huddy"
LEGACY_IDS = {"gods-eye-hud": "huddy"}  # 0.2.2: the pre-rename id of HUDdy


def canonical(theme_id: str) -> str:
    """A theme id with the legacy ``gods-eye-hud`` mapped to ``huddy``; any other id is returned unchanged."""
    return LEGACY_IDS.get(theme_id, theme_id)


# 0.7.0: Dirlume 1.7.x outline buttons. The ``btn-*`` theme variables come from
# each palette (Dirlume layout.button_tokens, MIT). Colour helpers below are the
# same small functions Dirlume uses.
BUTTON_ROLES = ("primary", "neutral", "dismiss", "danger")


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """``a`` moved ``t`` (0..1) of the way towards ``b``, as #rrggbb."""
    (r1, g1, b1), (r2, g2, b2) = _hex(a), _hex(b)
    return "#{:02x}{:02x}{:02x}".format(*(round(x + (y - x) * t) for x, y in ((r1, r2), (g1, g2), (b1, b2))))


def _lum(c: str) -> float:
    def ch(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = _hex(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable(colour: str, on: str, minimum: float = 3.0) -> str:
    """``colour`` moved towards black or white (away from ``on``) until it has ``minimum`` contrast on ``on``."""
    target = "#000000" if _lum(on) > 0.18 else "#ffffff"
    for i in range(21):
        c = mix(colour, target, i / 20)
        if contrast(c, on) >= minimum:
            return c
    return target


def button_tokens(p: Any) -> dict[str, str]:
    """Cached: Textual asks for a theme's variables often, and the contrast search is not free."""
    return dict(_button_tokens(p))


@cache
def _button_tokens(p: Any) -> tuple[tuple[str, str], ...]:
    return tuple(_compute_button_tokens(p).items())


def _compute_button_tokens(p: Any) -> dict[str, str]:
    """The ``btn-*`` theme variables for palette ``p`` (Dirlume 1.7.x): accept = success, danger = error,
    neutral = foreground/background grey, dismiss = muted, focus = primary. Labels read 4.5:1."""
    fg, bg, sf = p.foreground, p.background, p.surface
    hues = {"primary": p.success, "neutral": mix(fg, bg, 0.3), "dismiss": p.muted, "danger": p.error}
    out: dict[str, str] = {}
    for role, hue in hues.items():
        out[f"btn-{role}-border"] = mix(hue, bg, 0.45)
        out[f"btn-{role}-hover"] = hue
        out[f"btn-{role}-pressed"] = mix(hue, fg, 0.25)
        out[f"btn-{role}-pressed-bg"] = mix(hue, bg, 0.86)
        base = mix(hue, fg, 0.15) if role in ("primary", "danger") else hue
        text = readable(base, bg, 4.5)
        if contrast(text, sf) < 4.5:
            text = readable(text, sf, 4.5)
        out[f"btn-{role}-text"] = text
        out[f"btn-{role}-text-hover"] = readable(mix(text, fg, 0.4), sf, 4.5)
        out[f"btn-{role}-focus"] = p.primary
    out["btn-disabled-text"] = mix(p.muted, bg, 0.35)
    out["btn-disabled-border"] = mix(p.muted, bg, 0.65)
    return out


def selection_tokens(p: Any) -> dict[str, str]:
    """0.2.3 selection rule (Template 1.1 §2.5): on an accent-filled item (focused tab, menu item, list row) the text is
    the theme background, for every dark theme whose background reaches 4.5:1 on its primary. Light themes and dark
    themes that fail the check keep Textual's automatic contrast."""
    if p.dark and contrast(p.background, p.primary) >= 4.5:
        return {"block-cursor-foreground": p.background, "block-cursor-background": p.primary}
    return {}


@dataclass(frozen=True)
class Palette:
    id: str
    name: str
    dark: bool
    background: str
    surface: str
    panel: str
    foreground: str
    muted: str
    primary: str
    secondary: str
    accent: str
    success: str
    warning: str
    error: str
    branches: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["branches"] = list(self.branches)
        return data

    def textual(self) -> Any:
        from textual.theme import Theme

        return Theme(
            name=self.id,
            primary=self.primary,
            secondary=self.secondary,
            accent=self.accent,
            foreground=self.foreground,
            background=self.background,
            surface=self.surface,
            panel=self.panel,
            warning=self.warning,
            error=self.error,
            success=self.success,
            dark=self.dark,
            variables={"text-muted": self.muted, "footer-key-foreground": self.accent, **button_tokens(self),
                       "pane-fallback": pane_fallback(self), **selection_tokens(self)},
        )


PALETTES: tuple[Palette, ...] = (
    Palette(
        "tokyo-night",
        "Tokyo Night",
        True,
        "#1a1b26",
        "#24283b",
        "#414868",
        "#c0caf5",
        "#787c99",
        "#7aa2f7",
        "#bb9af7",
        "#7dcfff",
        "#9ece6a",
        "#e0af68",
        "#f7768e",
        ("#7aa2f7", "#bb9af7", "#7dcfff", "#9ece6a", "#e0af68", "#f7768e", "#73daca", "#ff9e64"),
    ),
    Palette(
        "solarized-dark",
        "Solarized Dark",
        True,
        "#002b36",
        "#073642",
        "#0d4a58",
        "#93a1a1",
        "#839496",
        "#268bd2",
        "#6c71c4",
        "#2aa198",
        "#859900",
        "#b58900",
        "#dc322f",
        ("#268bd2", "#2aa198", "#859900", "#b58900", "#cb4b16", "#d33682", "#6c71c4", "#dc322f"),
    ),
    Palette(
        "solarized-light",
        "Solarized Light",
        False,
        "#fdf6e3",
        "#eee8d5",
        "#e4dcc4",
        "#586e75",
        "#7d8f95",
        "#268bd2",
        "#6c71c4",
        "#2aa198",
        "#859900",
        "#b58900",
        "#dc322f",
        ("#268bd2", "#2aa198", "#859900", "#b58900", "#cb4b16", "#d33682", "#6c71c4", "#dc322f"),
    ),
    Palette(
        "gruvbox",
        "Gruvbox",
        True,
        "#282828",
        "#3c3836",
        "#504945",
        "#ebdbb2",
        "#a89984",
        "#83a598",
        "#d3869b",
        "#8ec07c",
        "#b8bb26",
        "#fabd2f",
        "#fb4934",
        ("#83a598", "#d3869b", "#8ec07c", "#b8bb26", "#fabd2f", "#fe8019", "#fb4934", "#458588"),
    ),
    Palette(
        "dracula",
        "Dracula",
        True,
        "#282a36",
        "#343746",
        "#44475a",
        "#f8f8f2",
        "#6272a4",
        "#bd93f9",
        "#ff79c6",
        "#8be9fd",
        "#50fa7b",
        "#f1fa8c",
        "#ff5555",
        ("#bd93f9", "#ff79c6", "#8be9fd", "#50fa7b", "#f1fa8c", "#ffb86c", "#ff5555", "#6272a4"),
    ),
    Palette(
        "monokai",
        "Monokai",
        True,
        "#272822",
        "#33342c",
        "#49483e",
        "#f8f8f2",
        "#75715e",
        "#66d9ef",
        "#ae81ff",
        "#a6e22e",
        "#a6e22e",
        "#e6db74",
        "#f92672",
        ("#66d9ef", "#a6e22e", "#e6db74", "#fd971f", "#f92672", "#ae81ff", "#78dce8", "#ab9df2"),
    ),
    Palette(
        "tomorrow-night",
        "Tomorrow Night",
        True,
        "#1d1f21",
        "#282a2e",
        "#373b41",
        "#c5c8c6",
        "#969896",
        "#81a2be",
        "#b294bb",
        "#8abeb7",
        "#b5bd68",
        "#f0c674",
        "#cc6666",
        ("#81a2be", "#b294bb", "#8abeb7", "#b5bd68", "#f0c674", "#de935f", "#cc6666", "#c5c8c6"),
    ),
    Palette(
        "material-dark",
        "Material Dark",
        True,
        "#212121",
        "#292929",
        "#3a3a3a",
        "#eeffff",
        "#808080",
        "#82aaff",
        "#c792ea",
        "#89ddff",
        "#c3e88d",
        "#ffcb6b",
        "#f07178",
        ("#82aaff", "#c792ea", "#89ddff", "#c3e88d", "#ffcb6b", "#f78c6c", "#f07178", "#80cbc4"),
    ),
    Palette(
        "github-dark",
        "GitHub Dark",
        True,
        "#0d1117",
        "#161b22",
        "#30363d",
        "#e6edf3",
        "#8b949e",
        "#4493f8",
        "#bc8cff",
        "#39c5cf",
        "#3fb950",
        "#d29922",
        "#f85149",
        ("#58a6ff", "#bc8cff", "#39c5cf", "#3fb950", "#d29922", "#db6d28", "#f85149", "#ff7b72"),
    ),
    Palette(
        "github-light",
        "GitHub Light",
        False,
        "#ffffff",
        "#f6f8fa",
        "#d0d7de",
        "#1f2328",
        "#656d76",
        "#0969da",
        "#8250df",
        "#1b7c83",
        "#1a7f37",
        "#9a6700",
        "#cf222e",
        ("#0969da", "#8250df", "#1b7c83", "#1a7f37", "#9a6700", "#bc4c00", "#cf222e", "#bf3989"),
    ),
    Palette(
        "pride",
        "Pride",
        True,
        "#1b1a22",
        "#24222e",
        "#353244",
        "#f5f3ff",
        "#a19cb8",
        "#4d7cff",
        "#b25cff",
        "#5bcefa",
        "#3ccf6e",
        "#ffe14d",
        "#ff4d4d",
        ("#ff4d4d", "#ff9f1c", "#ffe14d", "#3ccf6e", "#4d7cff", "#b25cff", "#5bcefa", "#f5a9b8"),
    ),
    Palette(
        "lux-marble",
        "Lux Marble",
        False,
        "#f4f1ea",
        "#ebe6dc",
        "#d6cfc2",
        "#2b2622",
        "#7d7468",
        "#9c7a2c",
        "#5c6b73",
        "#8a6f4d",
        "#4f7a5a",
        "#b07d1f",
        "#a23b3b",
        ("#9c7a2c", "#5c6b73", "#8a6f4d", "#4f7a5a", "#b07a85", "#3e5170", "#4a4a4a", "#4f7c7a"),
    ),
    Palette(
        "koi",
        "Koi",
        True,
        "#0e1b22",
        "#142833",
        "#1f3a47",
        "#e8efe9",
        "#86a3a6",
        "#ff7a3d",
        "#e8473f",
        "#f2c14e",
        "#7fbf7f",
        "#f2c14e",
        "#ff5a4f",
        ("#ff7a3d", "#f2c14e", "#e8473f", "#f4f1e8", "#6fc3df", "#7fbf7f", "#c9a0dc", "#ffb3a7"),
    ),
    Palette(
        "starship",
        "Starship",
        True,
        "#0b0e1a",
        "#121729",
        "#1e2540",
        "#e6e9f5",
        "#7e86a8",
        "#5fd7ff",
        "#c678dd",
        "#ff6ac1",
        "#3ad97f",
        "#ffd166",
        "#ff5f6d",
        ("#5fd7ff", "#c678dd", "#ff6ac1", "#ffd166", "#3ad97f", "#ff8c42", "#7aa2ff", "#f8f8f2"),
    ),
    Palette(
        "powerlevel10k",
        "Powerlevel10k",
        True,
        "#121212",
        "#1c1c1c",
        "#303030",
        "#d0d0d0",
        "#8a8a8a",
        "#00afff",
        "#af5fff",
        "#ffaf00",
        "#5fd700",
        "#ffaf00",
        "#ff3030",
        ("#00afff", "#5fd700", "#ffaf00", "#af5fff", "#00d7d7", "#ff8700", "#ff5fd7", "#87afff"),
    ),
    Palette(
        "catppuccin",
        "Catppuccin Mocha",
        True,
        "#1e1e2e",
        "#313244",
        "#45475a",
        "#cdd6f4",
        "#9399b2",
        "#89b4fa",
        "#cba6f7",
        "#94e2d5",
        "#a6e3a1",
        "#f9e2af",
        "#f38ba8",
        ("#89b4fa", "#cba6f7", "#94e2d5", "#a6e3a1", "#f9e2af", "#fab387", "#f5c2e7", "#89dceb"),
    ),
    Palette(
        "catppuccin-latte",
        "Catppuccin Latte",
        False,
        "#eff1f5",
        "#e6e9ef",
        "#ccd0da",
        "#4c4f69",
        "#8c8fa1",
        "#1e66f5",
        "#8839ef",
        "#04a5e5",
        "#40a02b",
        "#df8e1d",
        "#d20f39",
        ("#1e66f5", "#8839ef", "#04a5e5", "#40a02b", "#df8e1d", "#fe640b", "#d20f39", "#179299"),
    ),
    Palette(
        "nord",
        "Nord",
        True,
        "#2e3440",
        "#3b4252",
        "#434c5e",
        "#eceff4",
        "#9aa5b8",
        "#88c0d0",
        "#81a1c1",
        "#8fbcbb",
        "#a3be8c",
        "#ebcb8b",
        "#bf616a",
        ("#88c0d0", "#b48ead", "#a3be8c", "#ebcb8b", "#d08770", "#81a1c1", "#8fbcbb", "#bf616a"),
    ),
    Palette(
        "one-dark",
        "One Dark",
        True,
        "#282c34",
        "#21252b",
        "#3e4451",
        "#abb2bf",
        "#7f848e",
        "#61afef",
        "#c678dd",
        "#56b6c2",
        "#98c379",
        "#e5c07b",
        "#e06c75",
        ("#61afef", "#c678dd", "#56b6c2", "#98c379", "#e5c07b", "#d19a66", "#e06c75", "#be5046"),
    ),
    Palette(
        "rose-pine",
        "Rosé Pine",
        True,
        "#191724",
        "#1f1d2e",
        "#26233a",
        "#e0def4",
        "#908caa",
        "#9ccfd8",
        "#c4a7e7",
        "#ebbcba",
        "#31748f",
        "#f6c177",
        "#eb6f92",
        ("#9ccfd8", "#c4a7e7", "#ebbcba", "#f6c177", "#eb6f92", "#31748f", "#e0def4", "#908caa"),
    ),
    Palette(
        "everforest",
        "Everforest",
        True,
        "#2d353b",
        "#343f44",
        "#475258",
        "#d3c6aa",
        "#859289",
        "#7fbbb3",
        "#d699b6",
        "#83c092",
        "#a7c080",
        "#dbbc7f",
        "#e67e80",
        ("#7fbbb3", "#d699b6", "#83c092", "#a7c080", "#dbbc7f", "#e69875", "#e67e80", "#d3c6aa"),
    ),
    Palette(
        "kanagawa",
        "Kanagawa",
        True,
        "#1f1f28",
        "#2a2a37",
        "#363646",
        "#dcd7ba",
        "#727169",
        "#7e9cd8",
        "#957fb8",
        "#7fb4ca",
        "#98bb6c",
        "#e6c384",
        "#ff5d62",
        ("#7e9cd8", "#957fb8", "#7fb4ca", "#98bb6c", "#e6c384", "#ffa066", "#d27e99", "#7aa89f"),
    ),
    # 0.2.0: the web desk's HUD palette (nuzehub styles.css / lib/desk/theme.ts). secondary and the branch list are
    # proposed (brief §0.2) and wait for David's review. 0.2.2: renamed HUDdy (was God's Eye HUD, id gods-eye-hud).
    # 0.2.3: HUDdy Soft Contrast (Spec 1.0 §2): background, surface, panel and foreground only; hues within 2°.
    Palette(
        "huddy",
        "HUDdy",
        True,
        "#080e19",  # 0.2.3 soft contrast (Template 1.1 §2.1.1): was #03060b
        "#0d192c",  # was #0a1322
        "#112138",  # was #0f1c30
        "#c2cfdc",  # was #d6e4f2 (body text)
        "#7d93ad",
        "#5ee1ff",
        "#93a8bf",
        "#5ee1ff",
        "#3dffa8",
        "#ffb547",
        "#ff5470",
        ("#5ee1ff", "#3dffa8", "#ffb547", "#ff5470", "#93a8bf", "#7d93ad", "#3ef0ff", "#64d2ff"),
    ),
)

BY_ID = {palette.id: palette for palette in PALETTES}
NAMES = [palette.id for palette in PALETTES]


def get(theme_id: str | None) -> Palette:
    return BY_ID.get(canonical(theme_id or DEFAULT), BY_ID[DEFAULT])


def mix(c1: str, c2: str, t: float) -> str:  # type: ignore[no-redef]  # noqa: F811 - as in SSHush 1.0.0
    """Blend two #rrggbb colours. t=0 returns c1 and t=1 returns c2."""
    left = [int(c1[i : i + 2], 16) for i in (1, 3, 5)]
    right = [int(c2[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(left, right, strict=False))


def rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def contrast_ratio(foreground: str, background: str) -> float:
    def channel(value: int) -> float:
        s = value / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    def luminance(color: str) -> float:
        r, g, b = rgb(color)
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    lighter = max(luminance(foreground), luminance(background))
    darker = min(luminance(foreground), luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


# ---- 0.2.0 (brief §0.4): 256- and 16-colour fallbacks for the two required themes -----------------------------------
# Applied when the colour system is 256 or 16 (Rich/Textual would otherwise pick the nearest colour themselves). The
# 256 values are xterm indexes; the 16 values are the standard colour names. Proposed values; David reviews them.
FALLBACK_ROLES = ("bg", "surface", "panel", "pane", "focus", "text", "muted", "up", "warn", "down")
FALLBACK_256: dict[str, dict[str, int]] = {
    "huddy": dict(bg=16, surface=234, panel=236, pane=24, focus=81, text=189, muted=103, up=85, warn=215, down=203),
    "github-dark": dict(bg=16, surface=234, panel=236, pane=25, focus=69, text=195, muted=246, up=71, warn=172, down=203),
}
FALLBACK_16: dict[str, str] = dict(bg="black", surface="blue", panel="bright_black", pane="cyan", focus="bright_cyan",
                                   text="bright_white", muted="white", up="bright_green", warn="bright_yellow",
                                   down="bright_red")


def _hex_of(triplet: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*triplet)


def _rgb3(c: Any) -> tuple[int, int, int]:
    return int(c[0]), int(c[1]), int(c[2])


def fallback_colours(theme_id: str, system: str) -> dict[str, str] | None:
    """Role -> exact #rrggbb of the mapped 256/16 colour (``system`` is Rich's "256" or "standard"), so the console's
    own downgrade lands on exactly the mapped index. None for truecolor or themes without a map."""
    from rich._palettes import EIGHT_BIT_PALETTE, STANDARD_PALETTE
    from rich.color import ANSI_COLOR_NAMES

    if system == "256" and theme_id in FALLBACK_256:
        return {role: _hex_of(_rgb3(EIGHT_BIT_PALETTE[i])) for role, i in FALLBACK_256[theme_id].items()}
    if system == "standard" and theme_id in FALLBACK_256:
        return {role: _hex_of(_rgb3(STANDARD_PALETTE[ANSI_COLOR_NAMES[name]])) for role, name in FALLBACK_16.items()}
    return None


def fallback_palette(p: Palette, system: str) -> Palette:
    """``p`` with its roles replaced by the 256/16-colour map (same id and name), or ``p`` unchanged."""
    from dataclasses import replace

    c = fallback_colours(p.id, system)
    if c is None:
        return p
    return replace(p, background=c["bg"], surface=c["surface"], panel=c["panel"], foreground=c["text"], muted=c["muted"],
                   primary=c["focus"], secondary=c["muted"], accent=c["focus"], success=c["up"], warning=c["warn"],
                   error=c["down"])


def pane_fallback(p: Palette) -> str:
    """The pane-border colour used in 256/16-colour mode (brief §0.4); elsewhere the CSS keeps ``$primary 40%``."""
    for system in ("256", "standard"):
        c = fallback_colours(p.id, system)
        if c is not None and p.background == c["bg"] and p.primary == c["focus"]:
            return c["pane"]
    return mix(p.background, p.primary, 0.4)
