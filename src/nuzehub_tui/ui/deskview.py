"""0.2.0 Desk tab (key 0): the web desk's OPS layout in the terminal (brief §4, §6).

≥120 columns: three columns (SITREP + LAYERS | ALERTS, map, Day dock | INTEL FEED + WATCHLIST) over the MKT tape.
100-119: the same with narrower sides. <100: one scrolling column in the order Alerts, Sitrep, map, Day dock, Intel,
Watchlist, Layers, with the map collapsed to one line (m shows it). Read-only except Focus 25m/50m.

The app owns the data (it fetches); this module owns how the Desk looks and its view state (layers, map view,
selected country, Intel filter, alert rotation, tape offset).
"""

from __future__ import annotations

import math
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.strip import Strip
from textual.visual import Visual, visualize
from textual.widget import Widget
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from nuzehub_tui import deskdata as D
from nuzehub_tui import mapgfx, rank
from nuzehub_tui.themes import Palette, mix
from nuzehub_tui.ui.dialogs import NzModal

BLOCKS = "▁▂▃▄▅▆▇█"
ASCII_SPARK = "_.-^"

DESK_CSS = """
#tab-desk { padding: 0; }
DeskView { height: 1fr; width: 100%; }
#desk-grid { layout: grid; grid-size: 3 4; grid-columns: 30 1fr 38; grid-rows: 1 1fr 7 5; grid-gutter: 0 1;
             height: 1fr; width: 100%; }
#desk-sitrep, #desk-intel, #desk-map, #desk-layers, #desk-watch { row-span: 2; }
.desk-panel { border: round $primary 40%; background: $background; padding: 0 1; height: 1fr; width: 100%;
              border-title-color: $accent; border-title-style: bold; border-subtitle-color: $text-muted; }
.desk-panel:focus-within { border: round $primary; }
App.-cfb .desk-panel { border: round $pane-fallback; }
App.-cfb .desk-panel:focus-within { border: round $primary; }
App.-ascii .desk-panel { border: ascii $primary 40%; }
App.-ascii .desk-panel:focus-within { border: ascii $primary; }
#desk-alerts { height: 1; width: 100%; background: $surface; padding: 0 1; text-wrap: nowrap; text-overflow: ellipsis; }
#desk-tape { height: 1; width: 100%; background: $surface; text-wrap: nowrap; }
#desk-tape:focus { background: $primary 12%; }
#sitrep-scroll { height: 1fr; scrollbar-size-vertical: 1; }
#sitrep-body { height: auto; width: 100%; }
#sitrep-head { height: 1; width: 100%; }
#sitrep-greet { width: 1fr; height: 1; text-style: bold; }
.chip { width: auto; height: 1; padding: 0 1; margin: 0 0 0 1; background: $surface; color: $btn-neutral-text; }
.chip:hover { color: $btn-neutral-text-hover; }
.chip:focus { background: $btn-primary-focus; color: $background; text-style: none; }
#layer-actions.-tight .chip { margin: 0; }
.toggle { width: 100%; height: 1; }
.toggle:focus { background: $primary 12%; color: $primary; text-style: none; }
#layer-views, #layer-actions { height: 1; width: 100%; }
#layer-views .toggle { width: auto; margin: 0 2 0 0; }
#desk-map { padding: 0; }
MapView { height: 1fr; width: 100%; }
MapView #map-canvas { height: 1fr; width: 100%; }
MapView #map-image { height: 1fr; width: 100%; }
MapView #map-note { height: 1; width: 100%; color: $text-muted; padding: 0 1; }
#desk-day { layout: horizontal; padding: 0; }
.day-cell { width: 1fr; height: 100%; padding: 0 1; }
#focus-chips { height: 1; width: 100%; }
#intel-list, #watch-list { height: 1fr; border: none; padding: 0; background: transparent; }
#desk-grid.-narrow { layout: vertical; overflow-y: auto; height: 1fr; }
#desk-grid.-narrow #desk-alerts { height: 1; }
#desk-grid.-narrow #desk-sitrep { height: 14; }
#desk-grid.-narrow #desk-map { height: 3; }
#desk-grid.-narrow #desk-map.-open { height: 16; }
#desk-grid.-narrow #desk-day { height: 5; }
#desk-grid.-narrow #desk-intel { height: 14; }
#desk-grid.-narrow #desk-watch { height: 12; }
#desk-grid.-narrow #desk-layers { height: 12; }
App.-c16 .toggle:focus, App.-c16 .chip:focus, App.-c16 OptionList:focus { text-style: reverse; }
InspectorModal, BriefModal { align: center middle; background: transparent; }
#inspector-body, #brief-body { height: auto; width: 100%; }
"""

WIDE_ORDER = ("desk-sitrep", "desk-alerts", "desk-intel", "desk-map", "desk-layers", "desk-watch", "desk-day")
NARROW_ORDER = ("desk-alerts", "desk-sitrep", "desk-map", "desk-day", "desk-intel", "desk-watch", "desk-layers")


def spark(values: list[float], width: int, ascii_only: bool = False, braille: bool = False) -> str:
    vals = [float(v) for v in values if isinstance(v, int | float)]
    if not vals or width <= 0:
        return ""
    if braille:
        n = width * 2
        pts = [vals[min(len(vals) - 1, int(i * len(vals) / n))] for i in range(n)] if len(vals) >= n else vals
        lo, hi = min(pts), max(pts)
        span = hi - lo or 1.0
        levels = [min(3, int((v - lo) / span * 3.999)) for v in pts]
        left = (0x40, 0x04, 0x02, 0x01)
        right = (0x80, 0x20, 0x10, 0x08)
        out = []
        for i in range(0, len(levels), 2):
            bits = left[levels[i]]
            if i + 1 < len(levels):
                bits |= right[levels[i + 1]]
            out.append(chr(0x2800 + bits))
        return "".join(out)
    if len(vals) > width:
        vals = [vals[min(len(vals) - 1, int(i * len(vals) / width))] for i in range(width)]
    lo, hi = min(vals), max(vals)
    span = hi - lo or 1.0
    chars = ASCII_SPARK if ascii_only else BLOCKS
    top = len(chars) - 1
    return "".join(chars[min(top, int((v - lo) / span * (top + 0.999)))] for v in vals)


# ---- small focusable controls ------------------------------------------------------------------------------------


class Toggle(Static, can_focus=True):
    """A LAYERS control: ■/□ checkbox or ◆/◇ radio; on in $accent, off in $text-muted (brief §0.5)."""

    BINDINGS = [Binding("enter,space", "flip", show=False)]

    class Changed(Message):
        def __init__(self, toggle: Toggle) -> None:
            super().__init__()
            self.toggle = toggle

    def __init__(self, label: str, value: bool, *, radio: bool = False, hint: str = "", id: str | None = None) -> None:
        super().__init__("", id=id, classes="toggle")
        self.label = label
        self.value = value
        self.radio = radio
        self.hint = hint

    def on_mount(self) -> None:
        self.paint()

    def paint(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        if self.radio:
            glyph = ("(*)" if self.value else "( )") if ascii_only else ("◆" if self.value else "◇")
        else:
            glyph = ("[x]" if self.value else "[ ]") if ascii_only else ("■" if self.value else "□")
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(glyph, style=p.accent if self.value else p.muted)
        label_style = p.primary if self.has_focus else p.foreground if self.value else p.muted  # focus: accent, never bold
        text.append(" " + self.label.upper(), style=label_style)
        if self.hint:
            text.append(f" {self.hint}", style=p.muted)
        self.update(text)

    def on_focus(self) -> None:
        self.call_after_refresh(self.paint)

    def on_blur(self) -> None:
        self.call_after_refresh(self.paint)

    def action_flip(self) -> None:
        if self.radio and self.value:
            return
        self.value = not self.value
        self.paint()
        self.post_message(self.Changed(self))

    def on_click(self) -> None:
        self.action_flip()


class Chip(Static, can_focus=True):
    """A one-row HUD chip (the web's ``hud-chip``): Brief ↗, 25m, 50m, ◀ ▶ (rotate), Reset."""

    BINDINGS = [Binding("enter,space", "press", show=False)]

    class Pressed(Message):
        def __init__(self, chip: Chip) -> None:
            super().__init__()
            self.chip = chip

    def __init__(self, label: str, *, id: str | None = None) -> None:
        super().__init__(label.upper(), id=id, classes="chip")

    def action_press(self) -> None:
        self.post_message(self.Pressed(self))

    def on_click(self) -> None:
        self.action_press()


class LiveChip(Chip):
    """0.2.1 LIVE chip beside ◀ ▶ RESET: ◆ LIVE in $accent when Live Mode is on, ◇ LIVE muted when off; focus is the
    chip's own colours (border-free, never bold), like the other chips. 0.2.2: ◈ LIVE (accent glyph, warning label)
    when only some elements are on; ASCII * / + / o."""

    def __init__(self) -> None:
        super().__init__("Live", id="chip-live")

    def on_mount(self) -> None:
        self.paint()

    def paint(self) -> None:
        app: Any = self.app
        state = app.live_state()
        on = state != "off"
        ascii_only = app.desk_ascii()
        glyphs = {"off": ("o", "◇"), "partial": ("+", "◈"), "full": ("*", "◆")}[state]
        glyph = glyphs[0] if ascii_only else glyphs[1]
        if self.has_focus:
            self.update(f"{glyph} LIVE")
            return
        p = app.desk_palette()
        text = Text(no_wrap=True)
        text.append(glyph, style=p.accent if on else p.muted)
        text.append(" LIVE", style=p.warning if state == "partial" else p.foreground if on else p.muted)
        self.update(text)

    def on_focus(self) -> None:
        self.call_after_refresh(self.paint)

    def on_blur(self) -> None:
        self.call_after_refresh(self.paint)


class Panel(Vertical):
    def __init__(self, title: str, *, id: str) -> None:
        super().__init__(id=id, classes="desk-panel")
        self.title_text = title

    def set_title(self, ascii_only: bool) -> None:
        self.border_title = f"{'#' if ascii_only else '■'} {self.title_text}"


# ---- map ---------------------------------------------------------------------------------------------------------


ROTATE_STEP = 15.0  # degrees per manual rotate step (key, wheel notch or chip)
TILT_STEP = 10.0


class MapView(Widget, can_focus=True):
    """The map (row 20): Kitty image when the ladder allows, else Braille, else a text table. With Live Mode off it moves
    only when the user moves it (0.2.2 Live: Globe Spin also turns it, +1.5° at 8 fps by default; View > Live Speed): ←/→ step through the countries in the news, Shift+←/→ (or the mouse wheel, or the
    ◀ ▶ chips) rotate, Shift+↑/↓ tilt the globe, Enter opens the Inspector, Home resets."""

    BINDINGS = [
        Binding("left", "step(-1)", show=False),
        Binding("right", "step(1)", show=False),
        Binding("shift+left", "rotate(-1)", show=False),
        Binding("shift+right", "rotate(1)", show=False),
        Binding("shift+up", "tilt(1)", show=False),
        Binding("shift+down", "tilt(-1)", show=False),
        Binding("enter", "inspect", show=False),
        Binding("home", "reset", show=False),
    ]

    def __init__(self, graphics: mapgfx.Graphics) -> None:
        super().__init__()
        self.graphics = graphics
        self.collapsed = False
        self.render_count = 0
        self._dirty = False
        self._key: tuple | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="map-canvas")
        if self.graphics.widget is not None:
            img = self.graphics.widget(id="map-image")
            img.display = False
            yield img
        yield Static("", id="map-note")

    def schedule(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.call_after_refresh(self.redraw)

    def on_resize(self) -> None:
        self.schedule()

    def desk(self) -> DeskView:
        return self.app.query_one(DeskView)

    def redraw(self) -> None:
        self._dirty = False
        if not self.is_mounted:
            return
        dv = self.desk()
        app: Any = self.app
        p = app.desk_palette()
        canvas = self.query_one("#map-canvas", Static)
        note = self.query_one("#map-note", Static)
        imgs = self.query("#map-image")
        md = dv.mdata
        n = len(md.ranked)
        if self.collapsed:
            canvas.display = False
            for img in imgs:
                img.display = False
            note.update(f"Map: {n} countr{'y' if n == 1 else 'ies'} · press m")
            note.display = True
            return
        sel = rank.country_by_id(dv.selected)
        mode = self.graphics.mode
        view_name = "Tactical" if dv.view.kind == "tactical" else "Flat"
        note.update(f"{view_name} · {mode} · {n} countr{'y' if n == 1 else 'ies'}" + (f" · {sel.name}" if sel else "")
                    + " · ←→ country  ⇧←→ rotate  Enter inspect")
        size = canvas.size if canvas.display or not imgs else imgs.first().size
        cols, rows = max(10, self.size.width), max(3, self.size.height - 1)
        key = (mode, cols, rows, dv.view.kind, round(dv.view.lon, 1), dv.view.lat, dv.selected, tuple(sorted(dv.map_layers.items())),
               tuple(sorted(md.counts.items())), len(md.locations), len(md.arcs), app.theme, dv.minute)
        del size
        if key == self._key:
            return
        self._key = key
        scene = mapgfx.scene_from(md, dv.now_ms, dv.selected)
        if mode == "text":
            canvas.display = True
            canvas.update(mapgfx.render_table(md, rows, cols, p), layout=False)
        elif mode == "kitty" and imgs:
            canvas.display = False
            img = imgs.first()
            img.display = True
            cw, ch = self.graphics.cell
            w, h = cols * cw, rows * ch
            scale = min(1.0, 1600 / max(w, 1), 1000 / max(h, 1))
            img.image = mapgfx.render_image(scene, dv.view, dv.map_layers, int(w * scale), int(h * scale), p)  # type: ignore[attr-defined]
        else:
            canvas.display = True
            canvas.update(mapgfx.render_braille(scene, dv.view, dv.map_layers, cols, rows, p), layout=False)
        self.render_count += 1

    def action_step(self, d: int) -> None:
        self.desk().step_country(int(d))

    def action_rotate(self, d: int) -> None:
        self.desk().rotate(int(d) * ROTATE_STEP)

    def action_tilt(self, d: int) -> None:
        self.desk().tilt(int(d) * TILT_STEP)

    def on_mouse_scroll_down(self, event: Any) -> None:
        event.stop()
        self.desk().rotate(ROTATE_STEP)

    def on_mouse_scroll_up(self, event: Any) -> None:
        event.stop()
        self.desk().rotate(-ROTATE_STEP)

    def action_inspect(self) -> None:
        self.desk().open_inspector()

    def action_reset(self) -> None:
        self.desk().reset_view()


# ---- the Desk ----------------------------------------------------------------------------------------------------


class Tape(Widget, can_focus=True):
    """The MKT tape row. With Live Mode off it moves only when the user steps it: Left/Right step one item, Home goes
    back to the biggest movers, the mouse wheel steps, a click focuses it (0.2.1 Live Mode also scrolls it 2 cells/s). One line drawn straight from render_line as a
    cached Strip (the same Visual.to_strips conversion Static uses): set_line() repaints this row only, no re-layout."""

    BINDINGS = [
        Binding("left", "step(-1)", show=False),
        Binding("right", "step(1)", show=False),
        Binding("home", "home", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._line = Text(no_wrap=True)
        self._strip: Strip | None = None
        self._strip_key: tuple[Any, ...] | None = None

    def set_line(self, line: Text) -> None:
        self._line = line
        self._strip = None
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        style = self.visual_style
        if y != 0:
            return Strip.blank(width, style.rich_style)
        key = (width, style)
        if self._strip is None or self._strip_key != key:
            # the same conversion Static uses (Visual.to_strips), done once per line change instead of per refresh+layout
            strips = Visual.to_strips(self, visualize(self, self._line, markup=False), width, 1, style)
            self._strip = strips[0] if strips else Strip.blank(width, style.rich_style)
            self._strip_key = key
        return self._strip

    def _desk(self) -> Any:
        return self.app.query_one(DeskView)

    def action_step(self, d: int) -> None:
        self._desk().step_tape(int(d))

    def action_home(self) -> None:
        self._desk().tape_home()

    def on_mouse_scroll_down(self, event: Any) -> None:
        event.stop()
        self._desk().step_tape(1)

    def on_mouse_scroll_up(self, event: Any) -> None:
        event.stop()
        self._desk().step_tape(-1)


class DeskView(Vertical):
    def __init__(self, graphics: mapgfx.Graphics) -> None:
        super().__init__()
        self.graphics = graphics
        self.map_layers = dict(D.LAYER_DEFAULTS)
        self.view = mapgfx.View()
        self.selected: str | None = None
        self.filter: str | None = None
        self.alert_index = 0
        self.tape_offset = 0
        self.map_open = False
        self.narrow: bool | None = None
        self.now_ms = 0.0
        self.minute = 0
        self.ranked: list[dict] = []
        self.mdata = rank.MapData()
        self.alerts: list[dict] = []
        self.intel_rows: list[dict] = []
        self.quote_rows: list[dict] = []
        self._tape_text = Text()
        self._tape_starts: list[int] = [0]

    # ---- compose ----
    def compose(self) -> ComposeResult:
        with Container(id="desk-grid"):
            with Panel("SITREP", id="desk-sitrep"):
                with Horizontal(id="sitrep-head"):
                    yield Label("", id="sitrep-greet")
                    yield Chip("Brief ↗", id="chip-brief")
                with VerticalScroll(id="sitrep-scroll"):
                    yield Static("", id="sitrep-body")
            yield Static("", id="desk-alerts")
            with Panel("INTEL FEED", id="desk-intel"):
                yield OptionList(id="intel-list")
            with Panel("MAP", id="desk-map"):
                yield MapView(self.graphics)
            with Panel("LAYERS", id="desk-layers"):
                for i, (lid, label) in enumerate(D.LAYERS, start=1):
                    yield Toggle(label, self.map_layers[lid], hint=f"⌥{i}", id=f"layer-{lid}")
                with Horizontal(id="layer-views"):
                    yield Toggle("Tactical", True, radio=True, id="view-tactical")
                    yield Toggle("Flat", False, radio=True, id="view-flat")
                with Horizontal(id="layer-actions"):
                    yield Chip("◀", id="chip-rot-left")
                    yield Chip("▶", id="chip-rot-right")
                    yield Chip("Reset", id="chip-reset")
                    yield LiveChip()
            with Panel("WATCHLIST", id="desk-watch"):
                yield OptionList(id="watch-list")
            with Panel("DAY", id="desk-day"):
                yield Static("", id="day-next", classes="day-cell")
                yield Static("", id="day-tasks", classes="day-cell")
                with Vertical(id="day-focus", classes="day-cell"):
                    yield Static("", id="focus-text")
                    with Horizontal(id="focus-chips"):
                        yield Chip("25m", id="chip-25")
                        yield Chip("50m", id="chip-50")
        yield Tape(id="desk-tape")

    def on_mount(self) -> None:
        self.query_one("#desk-day").styles.padding = 0
        self.apply_width(self.app.size.width)

    # ---- layout ----
    def apply_width(self, width: int) -> None:
        grid = self.query_one("#desk-grid")
        narrow = width < 100
        if width >= 180:
            grid.styles.grid_columns = "40 1fr 50"
        elif width >= 120:
            grid.styles.grid_columns = "30 1fr 38"
        else:
            grid.styles.grid_columns = "26 1fr 32"
        if narrow != self.narrow:
            self.narrow = narrow
            grid.set_class(narrow, "-narrow")
            order = NARROW_ORDER if narrow else WIDE_ORDER
            for wid in reversed(order):
                grid.move_child(grid.query_one(f"#{wid}"), before=0)
        self.query_one("#layer-actions").set_class(not narrow and width < 120, "-tight")  # 0.2.1: LIVE fits at 100-119
        mv = self.query_one(MapView)
        collapsed = narrow and not self.map_open
        self.query_one("#desk-map").set_class(narrow and self.map_open, "-open")
        if mv.collapsed != collapsed:
            mv.collapsed = collapsed
            mv._key = None
        mv.schedule()
        self.paint_sitrep()

    def toggle_map(self) -> None:
        self.map_open = not self.map_open
        self.apply_width(self.app.size.width)

    # ---- data ----
    def recompute(self) -> None:
        app: Any = self.app
        self.now_ms = app.now_ms()
        self.minute = int(self.now_ms // 60000)
        self.ranked = D.ranked_stories(app.instance, app.stories, self.now_ms)
        self.mdata = D.map_data(app.instance, app.stories, self.now_ms)
        price = D.price_alerts(app.instance, app.desk_watch, app.desk_at.get("markets"), app.desk_failed("markets"))
        self.alerts = D.alert_items(app.instance, app.stories, self.mdata, self.now_ms, price)
        self.alert_index = int(self.now_ms // 7000) % max(1, len(self.alerts))
        self.quote_rows = D.watch_rows(app.desk_watch)
        if self.selected and self.selected not in self.mdata.counts:
            self.selected = None

    def render_all(self) -> None:
        if not self.is_mounted:
            return
        self.recompute()
        ascii_only = self.app.desk_ascii()  # type: ignore[attr-defined]
        for panel in self.query(Panel):
            panel.set_title(ascii_only)
        for t in self.query(Toggle):
            t.paint()
        self.paint_live()
        self.paint_sitrep()
        self.paint_alerts()
        self.paint_intel()
        self.paint_watch()
        self.paint_day()
        self.build_tape()
        self.paint_tape()
        self.query_one(MapView).schedule()
        self.call_after_refresh(self._after_layout)

    def _after_layout(self) -> None:
        if self.is_mounted:
            self.paint_sitrep()
            self.paint_day()
            self.paint_watch()
            self.paint_tape()  # 0.2.2: the tape is cut to the laid-out width, not the first one

    def on_resize(self) -> None:
        self.call_after_refresh(self._after_layout)

    def stale_meta(self, source: str) -> str:
        app: Any = self.app
        if app.desk_failed(source) and app.desk_at.get(source):
            return f"stale {D.age_label(app.desk_at[source], self.now_ms)}"
        if app.desk_failed(source):
            return "offline"
        return ""

    # ---- SITREP (rows 10-16) ----
    def paint_sitrep(self) -> None:
        if not self.is_mounted or not self.ranked and not self.app.instance:  # type: ignore[attr-defined]
            pass
        app: Any = self.app
        p: Palette = app.desk_palette()
        ascii_only = app.desk_ascii()
        s = D.sitrep(app.instance, self.ranked, self.mdata, self.now_ms) if self.now_ms else None
        panel = self.query_one("#desk-sitrep", Panel)
        stale = self.stale_meta("news")
        panel.border_subtitle = " · ".join(x for x in (D.sitrep_date(self.now_ms) if self.now_ms else "", stale) if x)
        self.query_one("#sitrep-greet", Label).update(
            Text(D.greeting(self.now_ms, s["name"]) if s else "Loading the desk…", style=f"bold {p.foreground}"))
        body = Text(no_wrap=False)
        if s is None:
            self.query_one("#sitrep-body", Static).update(body)
            return
        tiles = (("STORIES", s["stories"], p.foreground), ("GEO", s["geo"], p.foreground),
                 ("<2H", s["breaking"], p.warning if s["breaking"] else p.foreground), ("TASKS", s["tasks"], p.foreground))
        width = max(24, self.query_one("#sitrep-body").size.width or 26)
        cell = max(7, width // 4)
        base = [len(label) + 1 for label, _, _ in tiles]  # 0.2.1: a label always keeps one space after it
        spare = max(0, width - sum(base))
        cells = [cell] * 4 if cell > max(base) - 1 else [b + spare // 4 + (i < spare % 4) for i, b in enumerate(base)]
        for (label, _, _), w in zip(tiles, cells, strict=True):
            body.append(label.ljust(w)[:w], style=p.muted)
        body.append("\n")
        for (_, value, colour), w in zip(tiles, cells, strict=True):
            body.append(str(value).ljust(w)[:w], style=f"bold {colour}")
        body.append("\n")
        hz = D.hazard_line(app.desk_hazards)
        body.append("HAZARDS ", style=p.muted)
        body.append(hz["digest"], style=p.muted)
        if hz["top"]:
            body.append(" · ")
            role = {"muted": p.muted, "accent": p.accent, "warning": p.warning, "error": p.error}[hz["top"]["role"]]
            body.append(hz["top"]["label"] + " ", style=role)
            body.append(str(hz["top"]["text"] or ""), style=p.foreground)
        elif app.desk_failed("hazards"):
            body.append(" · " + (self.stale_meta("hazards") or "offline"), style=p.muted)
        else:
            body.append(" · loading…" if not app.desk_at.get("hazards") else " · none", style=p.muted)
        body.append("\n")
        # Brief §9 Q2: on small windows the brief is truncated first
        avail = self.query_one("#sitrep-scroll").size.height or 12
        world_rows = max(1, len(s["world"])) * 2 + 1
        clamp = max(1, min(5, avail - 3 - world_rows - 2))
        if s["brief"]:
            body.append(f"LAST BRIEF · {D.age_label(s['brief_at'], self.now_ms)} ago\n", style=p.muted)
            words = s["brief"].split()
            lines: list[str] = []
            cur = ""
            for w in words:
                if len(cur) + len(w) + 1 > width:
                    lines.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}".strip()
            if cur:
                lines.append(cur)
            if len(lines) > clamp:
                lines = lines[:clamp]
                lines[-1] = lines[-1][: max(0, width - 1)] + ("..." if ascii_only else "…")
            body.append("\n".join(lines) + "\n", style=p.foreground)
        else:
            body.append("No brief yet. ", style=p.muted)
            body.append("Write the brief on your model " + ("->" if ascii_only else "↗") + "\n", style=p.accent)
        body.append("WORLD DEVELOPMENTS\n", style=f"bold {p.accent}")
        if not s["world"]:
            body.append("No geopolitical items in the last week of your feeds yet.", style=p.muted)
        for i, story in enumerate(s["world"]):
            num, title, meta = D.world_row(i, story, self.mdata)
            body.append(f"{num} ", style=p.accent)
            body.append(title + "\n", style=p.foreground)
            body.append(f"   {meta}\n" if i < len(s["world"]) - 1 else f"   {meta}", style=p.muted)
        self.query_one("#sitrep-body", Static).update(body)

    # ---- ALERTS (row 21) ----
    def paint_alerts(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append("! " if ascii_only else "■ ", style=p.warning)  # not the bell emoji: 2 cells wide in some terminals
        t.append("ALERTS ", style=f"bold {p.warning}")
        if not self.alerts:
            t.append(D.QUIET, style=p.muted)
        else:
            a = self.alerts[self.alert_index % len(self.alerts)]
            t.append(D.hhmm(a.get("at")) + " ", style=p.muted)
            t.append(str(a.get("tag") or "").upper() + " ", style=f"bold {p.accent}")
            t.append(str(a.get("text") or ""), style=p.foreground)
            if len(self.alerts) >= 2:
                t.append(f"  {self.alert_index % len(self.alerts) + 1}/{len(self.alerts)}", style=p.muted)
        self.query_one("#desk-alerts", Static).update(t, layout=False)  # fixed 1 row

    def rotate_alerts(self) -> None:
        """Every 7 s (the app's alerts timer); the index follows the clock, so a fixed clock shows a fixed item."""
        if len(self.alerts) >= 2:
            self.alert_index = int(self.app.now_ms() // 7000) % len(self.alerts)  # type: ignore[attr-defined]
            self.paint_alerts()

    # ---- INTEL FEED (row 22) ----
    def paint_intel(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        rows = self.ranked
        if self.filter:
            rows = [s for s in rows if self.mdata.country_for_url.get(s.get("url", "")) == self.filter
                    or any(e["url"] == s.get("url") and e["countryId"] == self.filter for e in self.mdata.extras)]
        self.intel_rows = rows[:60]
        panel = self.query_one("#desk-intel", Panel)
        country = rank.country_by_id(self.filter)
        loading = not app.desk_at.get("news") and not app.desk_failed("news")
        meta = "syncing…" if loading else f"{len(self.intel_rows)}" + ("" if self.filter else f" of {len(self.ranked)}")
        stale = self.stale_meta("news")
        panel.border_subtitle = " · ".join(x for x in ((country.name + " · Esc clears") if country else "", meta, stale) if x)
        lst = self.query_one("#intel-list", OptionList)
        keep = lst.highlighted
        lst.clear_options()
        if not self.intel_rows:
            msg = ("Pulling your feeds…" if loading else f"Nothing ranked for {country.name} this week." if country
                   else "No stories yet.")
            lst.add_option(Option(Text(msg, style=p.muted), disabled=True))
            return
        for s in self.intel_rows:
            age = D.age_label(s.get("publishedAt"), self.now_ms)
            ms = rank.parse_ms(s.get("publishedAt"))
            fresh = math.isfinite(ms) and self.now_ms - ms < 2 * 3600_000
            t = Text()
            t.append(str(s.get("sourceName") or ""), style=p.muted)
            if age:
                t.append(f" · {age}", style=p.muted)
            if fresh:
                t.append(" *" if ascii_only else " ●", style=p.warning)
            c = rank.country_by_id(self.mdata.country_for_url.get(s.get("url", "")))
            if c:
                t.append(f"  {c.iso2}", style=p.accent)
            t.append("\n" + str(s.get("title") or ""), style=p.foreground)
            lst.add_option(Option(t, id=str(s.get("url"))))
        if keep is not None:
            lst.highlighted = min(keep, len(self.intel_rows) - 1)

    def filter_country(self) -> bool:
        """``c`` on the Desk: filter INTEL to the highlighted row's country (or the selected map country)."""
        lst = self.query_one("#intel-list", OptionList)
        cid = None
        if lst.has_focus and lst.highlighted is not None and lst.highlighted < len(self.intel_rows):
            cid = self.mdata.country_for_url.get(self.intel_rows[lst.highlighted].get("url", ""))
        cid = cid or self.selected
        if not cid:
            return False
        self.filter = cid
        lst.highlighted = None
        self.paint_intel()
        return True

    def clear_filter(self) -> bool:
        if not self.filter:
            return False
        self.filter = None
        self.paint_intel()
        return True

    # ---- WATCHLIST (row 24) ----
    def paint_watch(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        panel = self.query_one("#desk-watch", Panel)
        panel.border_subtitle = " · ".join(x for x in (f"{len(self.quote_rows)} sym", self.stale_meta("markets")) if x)
        lst = self.query_one("#watch-list", OptionList)
        keep = lst.highlighted
        lst.clear_options()
        if not self.quote_rows:
            text = "Loading quotes…" if not app.desk_at.get("markets") and not app.desk_failed("markets") else "No quotes."
            lst.add_option(Option(Text(text, style=p.muted), disabled=True))
            return
        width = max(20, panel.size.width - 4)
        sw = max(4, width - 8 - 10 - 9)
        for row in self.quote_rows:
            colour = p.success if row["up"] else p.error
            t = Text(no_wrap=True, overflow="ellipsis")
            t.append(str(row["symbol"])[:7].ljust(8), style=f"bold {p.foreground}")
            t.append(row["price"].rjust(9) + " ", style=p.foreground)
            pct = row["pct"]
            if ascii_only:
                pct = pct.replace("▲", "+").replace("▼", "-")
            t.append(pct.rjust(8) + " ", style=self.down_style(colour, row["up"]))
            t.append(spark(row["closes"], sw, ascii_only, braille=app.size.width >= 120 and not ascii_only), style=colour)
            lst.add_option(Option(t, id=str(row["symbol"])))
        if keep is not None:
            lst.highlighted = min(keep, len(self.quote_rows) - 1)

    def down_style(self, colour: str, up: bool) -> str:
        """16 colours: a down value on blue is a reverse chip (black on bright_red), brief §0.4."""
        if not up and getattr(self.app, "colour_system", "truecolor") == "standard":
            return f"#000000 on {colour}"
        return colour

    # ---- Day dock (rows 25-27) ----
    def paint_day(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        inst = app.instance
        cellw = max(8, (self.query_one("#desk-day").size.width - 6) // 3)
        nxt = D.next_event(inst, self.now_ms) if self.now_ms else None
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append("NEXT EVENT\n", style=p.muted)
        if nxt:
            t.append(nxt["when"] + "\n", style=p.accent)
            t.append(nxt["title"], style=p.foreground)
        else:
            t.append("Calendar clear", style=p.muted)
        self.query_one("#day-next", Static).update(t)
        ts = D.tasks_summary(inst, self.now_ms or 0)
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append("TASKS ", style=p.muted)
        t.append(f"{ts['done']}/{ts['total']}\n", style=p.foreground)
        filled, rest = D.bar(ts["done"] / ts["total"] if ts["total"] else 0, cellw, ascii_only)
        t.append(filled, style=p.accent)
        t.append(rest + "\n", style=p.panel if p.panel != p.background else p.muted)
        t.append(ts["first"], style=p.foreground)
        self.query_one("#day-tasks", Static).update(t)
        self.paint_focus()

    def paint_focus(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        left = D.focus_left(app.instance, self.now_ms) if self.now_ms else None
        cellw = max(8, (self.query_one("#desk-day").size.width - 6) // 3)
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append("FOCUS\n", style=p.muted)
        if left is not None:
            t.append(D.focus_text(left) + "\n", style=f"bold {p.accent}")
            filled, rest = D.bar(min(1.0, left / D.FOCUS_TOTAL_MS), cellw, ascii_only)
            t.append(filled, style=p.accent)
            t.append(rest, style=p.panel if p.panel != p.background else p.muted)
        self.query_one("#focus-text", Static).update(t)
        self.query_one("#focus-chips").display = left is None

    def focus_running(self) -> bool:
        return D.focus_left(self.app.instance, self.now_ms) is not None  # type: ignore[attr-defined]

    # ---- MKT tape (row 28) ----
    def build_tape(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        ascii_only = app.desk_ascii()
        items = D.tape_items(app.desk_tape, app.desk_watch)
        t = Text(no_wrap=True)
        starts: list[int] = []
        sep = " | " if ascii_only else " │ "
        sep_style = p.panel if p.panel != p.background else p.muted
        for it in items:
            colour = p.success if it["up"] else p.error
            starts.append(len(t.plain))
            t.append(f"{it['label']} ", style=p.muted)
            t.append(f"{it['price']} ", style=p.foreground)
            arrow = ("+" if it["up"] else "-") if ascii_only else ("▲" if it["up"] else "▼")
            t.append(f"{arrow}{it['pct']}", style=self.down_style(colour, it["up"]))
            t.append(sep, style=sep_style)
        if not items:
            stale = self.stale_meta("tape")
            t.append("Loading the tape…" if not stale else f"Tape {stale}", style=p.muted)
        self._tape_text = t
        self._tape_starts = starts or [0]

    def paint_tape(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        head = Text(" MKT ", style=f"bold {p.background} on {p.accent}")
        width = max(1, self.size.width - 6)
        body = self._tape_text
        n = len(body.plain)
        if n and n > width and self.tape_offset:
            off = self.tape_offset % n
            loop = Text.assemble(body, body)
            window = loop[off: off + width]
        else:
            window = body[:width] if n else body
        stale = self.stale_meta("tape")
        line = Text.assemble(head, " ", window)
        if stale and n:
            line = Text.assemble(head, Text(f" {stale} ", style=p.muted), window)
        tape = getattr(self, "_tape_widget", None)
        if tape is None or not tape.is_attached:
            tape = self._tape_widget = self.query_one("#desk-tape", Tape)
        tape.set_line(line)  # one row, drawn by Tape.render_line (no re-layout)  # fixed 1 row: repaint only (§5 CPU)

    def step_tape(self, d: int) -> None:
        """Manual only: one item left or right (wrapping); the tape never moves on its own."""
        starts = self._tape_starts
        if len(self._tape_text.plain) <= max(1, self.size.width - 6) or len(starts) < 2:
            return
        n = len(self._tape_text.plain)
        cur = self.tape_offset % n
        idx = max(i for i, st in enumerate(starts) if st <= cur)
        self.tape_offset = starts[(idx + d) % len(starts)]
        self.paint_tape()

    def scroll_tape(self) -> None:
        """Live: Stock Ticker: one cell left per tick (0.14 s by default; View > Live Speed), wrapping; manual steps
        and Home still work."""
        n = len(self._tape_text.plain)
        if n <= max(1, self.size.width - 6):
            return
        self.tape_offset = (self.tape_offset + 1) % n
        self.paint_tape()

    def tape_home(self) -> None:
        """Back to offset 0: the biggest movers."""
        if self.tape_offset:
            self.tape_offset = 0
            self.paint_tape()

    # ---- map / layers ----
    def set_layer(self, index: int) -> None:
        lid = D.LAYERS[index][0]
        self.map_layers[lid] = not self.map_layers[lid]
        tog = self.query_one(f"#layer-{lid}", Toggle)
        tog.value = self.map_layers[lid]
        tog.paint()
        self.query_one(MapView).schedule()

    def paint_live(self) -> None:
        for chip in self.query(LiveChip):
            chip.paint()

    def on_toggle_changed(self, event: Toggle.Changed) -> None:
        event.stop()
        tid = str(event.toggle.id or "")
        if tid.startswith("layer-"):
            self.map_layers[tid[6:]] = event.toggle.value
        elif tid in ("view-tactical", "view-flat"):
            kind = tid[5:]
            self.view = mapgfx.View(kind, self.view.lon, 20.0 if kind == "tactical" else 0.0)
            for other in ("view-tactical", "view-flat"):
                tg = self.query_one(f"#{other}", Toggle)
                tg.value = other == tid
                tg.paint()
        self.query_one(MapView).schedule()

    def on_chip_pressed(self, event: Chip.Pressed) -> None:
        event.stop()
        cid = str(event.chip.id or "")
        app: Any = self.app
        if cid in ("chip-rot-left", "chip-rot-right"):
            self.rotate(-ROTATE_STEP if cid == "chip-rot-left" else ROTATE_STEP)
        elif cid == "chip-reset":
            self.reset_view()
        elif cid in ("chip-25", "chip-50"):
            app.desk_start_focus(25 if cid == "chip-25" else 50)
        elif cid == "chip-brief":
            self.open_brief()
        elif cid == "chip-live":
            app.action_toggle_live()  # 0.2.2: the master switch (remembers the last combination)

    def rotate(self, degrees: float) -> None:
        """Manual rotation (tactical globe) or pan (flat map) in longitude."""
        self.view = mapgfx.View(self.view.kind, (self.view.lon + degrees + 180) % 360 - 180, self.view.lat)
        self.query_one(MapView).schedule()

    def tilt(self, degrees: float) -> None:
        """Manual tilt of the tactical globe (latitude of the centre, kept within ±60°)."""
        if self.view.kind == "tactical":
            self.view = mapgfx.View(self.view.kind, self.view.lon, max(-60.0, min(60.0, self.view.lat + degrees)))
            self.query_one(MapView).schedule()

    def reset_view(self) -> None:
        self.view = mapgfx.View(self.view.kind, 10.0, 20.0 if self.view.kind == "tactical" else 0.0)
        self.selected = None
        self.query_one(MapView).schedule()

    def step_country(self, d: int) -> None:
        ids = [c.id for c, _ in self.mdata.ranked]
        if not ids:
            return
        pos = ids.index(self.selected) if self.selected in ids else (-1 if d > 0 else 0)
        self.selected = ids[(pos + d) % len(ids)]
        c = rank.country_by_id(self.selected)
        if c:
            self.view = mapgfx.View(self.view.kind, c.lon, (20.0 if self.view.kind == "tactical" else 0.0))
        self.query_one(MapView).schedule()

    def open_inspector(self) -> None:
        if not self.selected:
            self.step_country(1)
        if self.selected:
            self.app._overlay(InspectorModal(self), None)  # type: ignore[attr-defined]

    def open_brief(self) -> None:
        app: Any = self.app
        brief = D.desk_of(app.instance).get("brief")
        text = brief.get("text") if isinstance(brief, dict) else ""
        app._overlay(BriefModal(str(text or "")), None)

    # ---- lists: Enter opens the existing tabs (Decision 4) ----
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        app: Any = self.app
        if event.option_list.id == "intel-list" and event.option.id:
            app.desk_open_story(str(event.option.id))
        elif event.option_list.id == "watch-list" and event.option.id:
            app.desk_open_symbol(str(event.option.id))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()


# ---- Inspector (row 23) and Brief: see-through modals -----------------------------------------------------------


class InspectorModal(NzModal):
    BINDINGS = [Binding("left", "step(-1)", show=False), Binding("right", "step(1)", show=False),
                Binding("c", "filter", show=False)]

    def __init__(self, desk_view: DeskView) -> None:
        super().__init__()
        self.dv = desk_view

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="inspector-dialog"):
            yield Label("Inspector", classes="dlg-title")
            with VerticalScroll():
                yield Static("", id="inspector-body")
            yield Label("← → country · c filter Intel · Esc close", classes="hint")

    def on_mount(self) -> None:
        super().on_mount()
        self.paint()

    def paint(self) -> None:
        app: Any = self.app
        p = app.desk_palette()
        c = rank.country_by_id(self.dv.selected)
        t = Text()
        if c is None:
            t.append("No country selected.", style=p.muted)
        else:
            n = self.dv.mdata.counts.get(c.id, 0)
            pos = next((i for i, (cc, _) in enumerate(self.dv.mdata.ranked) if cc.id == c.id), 0) + 1
            t.append(f"{c.name.upper()}  ", style=f"bold {p.accent}")
            t.append(f"{c.iso2} · {c.lat:.2f}, {c.lon:.2f}\n", style=p.muted)
            t.append(f"Stories {n} · heat {rank.heat_level(n)}/5 · rank {pos} of {len(self.dv.mdata.ranked)}\n", style=p.foreground)
            urls = [a["url"] for a in self.dv.mdata.displayed if a["countryId"] == c.id]
            urls += [e["url"] for e in self.dv.mdata.extras if e["countryId"] == c.id]
            stories = [s for s in self.dv.ranked if s.get("url") in urls][:6]
            for s in stories:
                t.append("\n" + str(s.get("title", "")) + "\n", style=p.foreground)
                t.append(f"{s.get('sourceName', '')} · {D.age_label(s.get('publishedAt'), self.dv.now_ms)}", style=p.muted)
            if not stories:
                t.append("\nNo ranked stories this week.", style=p.muted)
        self.query_one("#inspector-body", Static).update(t)

    def action_step(self, d: int) -> None:
        self.dv.step_country(int(d))
        self.paint()

    def action_filter(self) -> None:
        self.dv.filter = self.dv.selected
        self.dv.paint_intel()
        self.dismiss(None)


class BriefModal(NzModal):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall", id="brief-dialog"):
            yield Label("Brief", classes="dlg-title")
            with VerticalScroll():
                yield Static(self.text or "No brief yet. Write the brief on your model in the NuzeHub web desk.",
                             id="brief-body", markup=False)
            yield Label("Esc close", classes="hint")


__all__ = ["DESK_CSS", "BriefModal", "Chip", "DeskView", "InspectorModal", "MapView", "Toggle", "mix", "spark"]
