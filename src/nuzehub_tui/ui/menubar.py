"""A euporie-style menu bar: Dirlume 1.7.3's menubar, used by SSHush 0.7.0 and NuzeHub TUI.

Copyright (c) 2026 Dirlume contributors, MIT. Adapted for SSHush (imports only).
Keyboard: F10 opens the first menu, alt+letter opens a menu by its underlined
letter. Inside a menu, arrows move, left/right switch menus, Enter runs, Esc
closes. Mouse: click a title to open, click an item to run it, click elsewhere
to close. Menus open over a see-through backdrop: only the drop-down box is opaque.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class layout:  # noqa: N801 - Dirlume layout tokens used by the menu (Dirlume layout.py, MIT)
    MENU_MAX_W = 72
    MENU_MAX_H = 40
    SCROLLBAR_W = 1
    MENUBAR_H = 1


class themes:  # noqa: N801 - Dirlume fallbacks when a theme has no colour set
    FALLBACK_ACCENT = "#7dcfff"
    FALLBACK_PRIMARY = "#7aa2f7"
    FALLBACK_BACKGROUND = "#000000"


@dataclass
class Item:
    label: str
    action: str = ""                          # app action, e.g. "scan" or "set_theme('nord')"
    key: str = ""                             # shortcut shown on the right
    checked: Callable[[], bool] | bool | None = None
    enabled: Callable[[], bool] | None = None
    radio: bool = False                       # ● instead of ✓
    why: str = ""                             # 1.6.8: why the item is disabled (else the app's menu_disabled_reason)

    @property
    def is_separator(self) -> bool:
        return self.label == "-"


SEP = Item("-")


@dataclass
class Menu:
    title: str
    items: Callable[[], list[Item]]
    hotkey: str = ""                          # letter for alt+letter

    def __post_init__(self) -> None:
        self.hotkey = (self.hotkey or self.title[0]).lower()


def tidy_separators(items: list[Item]) -> list[Item]:
    """No separator at the top or bottom of a menu and never two in a row (1.6.3: even rhythm)."""
    out: list[Item] = []
    for it in items:
        if it.is_separator and (not out or out[-1].is_separator):
            continue
        out.append(it)
    while out and out[-1].is_separator:
        out.pop()
    return out


def screen_width(node) -> int:
    """The terminal width, or 'unlimited' when there is no running app (unit tests of the row builder)."""
    try:
        return int(node.app.size.width) or 10_000
    except Exception:
        return 10_000


class MenuBar(Widget):
    """The bar itself. Renders titles; the open one is highlighted."""

    DEFAULT_CSS = """
    MenuBar { height: 1; width: 1fr; background: $panel; color: $foreground; }
    """
    can_focus = False

    def __init__(self, menus: list[Menu], brand: str = "", **kw):
        super().__init__(**kw)
        self.menus = menus
        self.brand = brand
        self.open_index: int | None = None
        self.spans: list[tuple[int, int]] = []

    def render(self) -> Text:
        t = Text(no_wrap=True, overflow="crop")
        self.spans = []
        styles = self.app.current_theme
        accent = styles.accent or themes.FALLBACK_ACCENT
        primary = styles.primary or themes.FALLBACK_PRIMARY
        bg = styles.background or themes.FALLBACK_BACKGROUND
        titles_w = sum(len(m.title) + 2 for m in self.menus)
        brand = self.brand
        if brand and self.size.width and Text(brand).cell_len + 3 + titles_w > self.size.width:   # 1.6.3: titles first
            brand = brand.split()[0] if len(brand.split()[0]) + 3 + titles_w <= self.size.width else ""
        if brand:
            t.append(f" {brand} ", style=f"bold {bg} on {primary}")
            t.append(" ")
        for i, m in enumerate(self.menus):
            start = t.cell_len
            label = Text(f" {m.title} ")
            pos = m.title.lower().find(m.hotkey)
            if pos >= 0:
                label.stylize("underline", pos + 1, pos + 2)
            if i == self.open_index:
                label.stylize(f"bold {bg} on {accent}")
            t.append_text(label)
            self.spans.append((start, t.cell_len))
        return t

    def index_at(self, x: int) -> int | None:
        for i, (a, b) in enumerate(self.spans):
            if a <= x < b:
                return i
        return None

    def on_click(self, event: events.Click) -> None:
        i = self.index_at(event.x)
        if i is not None:
            self.app.open_menu(i)  # type: ignore[attr-defined]


class MenuScreen(ModalScreen[str | None]):
    """One open drop-down. Dismisses with the chosen action (or None)."""

    DEFAULT_CSS = """
    MenuScreen { background: transparent; align: left top; padding: 0; }
    MenuScreen > #dropdown { width: auto; height: auto; max-height: 90%; background: $surface;
                              border: round $accent; padding: 0; }
    MenuScreen #menu-why { height: auto; padding: 0; background: $surface; }
    MenuScreen OptionList { width: auto; height: auto; max-height: 40; border: none; background: $surface;
                            padding: 0; scrollbar-size-vertical: 1; overflow-x: hidden; }
    MenuScreen OptionList:focus { border: none; }
    MenuScreen OptionList > .option-list--option-highlighted { background: $accent 35%; text-style: bold; }
    """
    BINDINGS = [
        Binding("escape,f10", "close", "Close", show=False),
        Binding("left", "switch(-1)", "Previous menu", show=False),
        Binding("right", "switch(1)", "Next menu", show=False),
    ]

    def __init__(self, bar: MenuBar, index: int):
        super().__init__()
        self.bar = bar
        self.index = index
        self.items = tidy_separators(bar.menus[index].items())

    MAX_WIDTH = layout.MENU_MAX_W

    def rows(self) -> list[Text | None]:
        """One row per item, every row exactly the same CELL width (1.6.2): label left, shortcut right-aligned, nothing
        after the shortcut and nothing past the box. Widths use Text.cell_len (not len), labels that would not fit are
        cut with an ellipsis, and rows never wrap — a row wider than the box made some terminals (Ghostty) draw a
        continuation glyph at the right edge of the drop-down."""
        live = [it for it in self.items if not it.is_separator]
        keyw = max((Text(it.key).cell_len for it in live), default=0)
        labw = max((Text(it.label).cell_len for it in live), default=10)
        # 1.6.3: never wider than the screen (2 cells of border, 1 of scrollbar room)
        room_w = screen_width(self) - 2 - layout.SCROLLBAR_W
        inner = max(8, min(self.MAX_WIDTH, room_w, max(20, 3 + labw + 2 + keyw + 1)))
        out: list[Text | None] = []
        for it in self.items:
            if it.is_separator:
                out.append(None)
                continue
            mark = " "
            if it.checked is not None:
                on = it.checked() if callable(it.checked) else it.checked
                mark = ("●" if it.radio else "✓") if on else " "
            room = inner - 3 - 2 - keyw - 1
            label = Text(it.label, no_wrap=True, overflow="ellipsis")
            if label.cell_len > room:
                label.truncate(room, overflow="ellipsis")
            row = Text(f" {mark} ", no_wrap=True, overflow="crop")
            row.append_text(label)
            row.append(" " * max(2, inner - row.cell_len - keyw - 1))
            row.append(it.key.rjust(keyw), style="dim")
            row.append(" ")
            row.truncate(inner, overflow="crop")
            out.append(row)
        self.inner_width = inner
        return out

    def compose(self) -> ComposeResult:
        opts: list[Option | None] = []
        for n, (it, row) in enumerate(zip(self.items, self.rows(), strict=True)):
            if row is None:
                opts.append(None)
                continue
            disabled = bool(it.enabled is not None and not it.enabled())
            opts.append(Option(row, id=f"m{n}", disabled=disabled))
        # 1.6.8: every disabled item says why, in a dim footer under the list (one line per distinct reason)
        reason_of = getattr(self.app, "menu_disabled_reason", None)
        why: dict[str, list[str]] = {}
        for it in self.items:
            if not it.is_separator and it.enabled is not None and not it.enabled():
                r = it.why or (reason_of(it) if reason_of else "") or "not available right now"
                why.setdefault(r, []).append(it.label.rstrip("…"))
        with Vertical(id="dropdown"):
            yield OptionList(*opts, id="menu-list")
            if why:
                foot = Text(no_wrap=True, overflow="ellipsis")
                for i, (r, labels) in enumerate(why.items()):
                    what = labels[0] if len(labels) == 1 else f"{len(labels)} items"
                    line = Text(("\n" if i else "") + f" ✗ {what}: {r}", style="dim")
                    foot.append_text(line)
                yield Static(foot, id="menu-why")

    def on_mount(self) -> None:
        x = self.bar.spans[self.index][0] if self.bar.spans else 0
        box = self.query_one("#dropdown")
        outer = self.inner_width + 2 + (layout.SCROLLBAR_W if len(self.items) > layout.MENU_MAX_H else 0)
        x = max(0, min(x, screen_width(self) - outer))        # 1.6.3: the box always ends inside the screen
        box.styles.offset = (x, layout.MENUBAR_H)
        ol = self.query_one(OptionList)
        ol.styles.width = self.inner_width + (layout.SCROLLBAR_W if len(self.items) > layout.MENU_MAX_H else 0)   # exact: rows never wrap or overrun
        for why in self.query("#menu-why"):
            why.styles.width = ol.styles.width
        ol.focus()
        for i in range(ol.option_count):
            if not ol.get_option_at_index(i).disabled:
                ol.highlighted = i
                break
        self.bar.open_index = self.index
        self.bar.refresh()

    def on_unmount(self) -> None:
        if self.bar.open_index == self.index:
            self.bar.open_index = None
            self.bar.refresh()

    @on(OptionList.OptionSelected)
    def chosen(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        n = int(str(event.option.id)[1:])
        self.dismiss(self.items[n].action or None)

    def on_click(self, event: events.Click) -> None:
        # clicks on the drop-down are handled by the OptionList; anything else closes or switches
        widget = event.widget
        if widget is not None and widget is not self:
            return
        if event.screen_y == 0:
            i = self.bar.index_at(event.screen_x)
            if i is not None and i != self.index:
                self.dismiss(f"__menu__{i}")
                return
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_switch(self, d: int) -> None:
        self.dismiss(f"__menu__{(self.index + d) % len(self.bar.menus)}")
