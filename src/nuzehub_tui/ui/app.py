"""NuzeHub TUI main screen: SSHush 0.7.0 chrome around six NuzeHub screens.

Menu bar, a list pane (left) and a tabbed detail pane (right) in rounded borders, an activity panel and the
2-row status bar. Every screen reads the running NuzeHub through its existing server functions; nothing here
fetches markets or hazards itself, or runs ``brain``.

0.2.0: the Desk tab (key 0, the start tab) is the web desk's OPS layout (ui/deskview.py). It ranks stories and
places them on the map with exact ports of the web's rankStories / computeMapData (rank.py), refreshes on timers
only while it is visible, and writes nothing except Focus 25m/50m (a saveInstance merge).

0.2.2: per-element Live Mode (globe spin, stock ticker, auto-updates, each on its own; L / the LIVE chip is the master
switch and remembers the last combination), a smoother spin and ticker, tab switches painted once (no no-op title
rewrites, one batched update) and coloured trend sparklines with ▲/▼ on the Markets tab.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.strip import Strip
from textual.widgets import Button, Checkbox, Input, Label, OptionList, Select, Static, TabbedContent, TabPane
from textual.widgets.option_list import Option

from nuzehub_tui import __version__, desk, deskdata, mapgfx
from nuzehub_tui.client import AccessDenied, NuzeHubError
from nuzehub_tui.remote import force_truecolor
from nuzehub_tui.settings import LIVE_KEYS, LIVE_SPEEDS, MIGRATED_NOTE, TABS, UPDATE_MAX, UPDATE_MIN, Settings
from nuzehub_tui.themes import DEFAULT, NAMES, PALETTES, fallback_palette, get
from nuzehub_tui.ui.deskview import DESK_CSS, DeskView, spark
from nuzehub_tui.ui.dialogs import (
    DIALOG_CSS,
    NEW_NOTE,
    AboutModal,
    CiteDialog,
    GateScreen,
    HelpModal,
    SaveDialog,
    ThemeModal,
)
from nuzehub_tui.ui.dlayout import ACTIVITY_H, SHORT_CLASS, SHORT_H, button_tcss, button_width, style_buttons
from nuzehub_tui.ui.menubar import SEP, Item, Menu, MenuBar, MenuScreen

LIST_TITLES = {
    "tab-desk": ("Desk", "0 opens the Desk"),
    "tab-news": ("Stories", "Enter opens · Related: button"),
    "tab-markets": ("Watchlist", "Enter shows a symbol"),
    "tab-geo": ("Hazards", "Enter shows details"),
    "tab-brain": ("Notes", "Enter opens a note"),
    "tab-wiki": ("Results", "Enter reads an article"),
    "tab-status": ("Checks", "r refreshes"),
}
HAZARD_WINDOWS = ("1h", "24h", "7d", "30d")
HAZARD_KINDS = ("quake", "volcano", "storm")
RANGES = ("5d", "1mo", "6mo")
LIVE_ELEMENTS = tuple(k[5:] for k in LIVE_KEYS)  # 0.2.2: ("globe", "ticker", "updates")
LIVE_NAMES = {"globe": "Globe Spin", "ticker": "Stock Ticker", "updates": "Auto-Updates"}
# 0.2.2 addendum: live_speed -> (globe step seconds, globe degrees per step, ticker seconds per cell)
# ultra is capped at 12 fps (the addendum asked for 15): at 15 fps a test machine measured 40.80 % CPU with full Live on,
# over the 40 % ceiling, and the addendum allows a cap in that case (evidence/performance.txt)
SPEEDS = {"eco": (1 / 3, 3.0, 0.28), "smooth": (0.125, 1.5, 0.14), "ultra": (1 / 12, 1.0, 0.08)}
SPEED_NAMES = {"eco": "Eco", "smooth": "Smooth", "ultra": "Ultra"}
UPDATE_CHOICES = (15, 30, 60, 120)  # View menu cycle; settings.json may hold any whole number of seconds in 5..600


class ItemList(OptionList):
    """0.2.3 selection rule (Template 1.1 §2.5): the focused, highlighted row is drawn entirely in the block-cursor text
    colour, so a Markets row's own foreground/up/down colours never sit on the accent fill."""

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        try:
            index = self._lines[self.scroll_offset.y + y][0]
        except IndexError:
            return strip
        if not self.has_focus or index != self.highlighted or self.options[index].disabled:
            return strip
        colour = self.get_visual_style("option-list--option", "option-list--option-highlighted").rich_style.color
        if colour is None:
            return strip
        fix = RichStyle(color=colour)
        return Strip([Segment(text, style + fix if style else fix, ctl) for text, style, ctl in strip], strip.cell_length)


class NuzeHubApp(App[None]):
    TITLE = "NuzeHub TUI"
    SUB_TITLE = __version__
    ENABLE_COMMAND_PALETTE = False
    ESCAPE_TO_MINIMIZE = False
    CSS = DIALOG_CSS + button_tcss() + DESK_CSS + """
    Screen { background: $background; color: $foreground; }
    GateScreen, CiteDialog, SaveDialog, ThemeModal, HelpModal, AboutModal { align: center middle; background: transparent; }
    #menubar { dock: top; height: 1; width: 100%; }
    #theme-select { width: 22; height: 1; }
    #theme-select > SelectCurrent { height: 1; border: none; padding: 0 1; }
    #theme-select > SelectOverlay { max-height: 24; width: 24; background: $surface; border: round $accent; }
    #body { height: 1fr; }
    #sidebar { width: 38%; min-width: 24; height: 1fr; padding: 0; border: round $primary 40%; }
    #sidebar:focus-within { border: round $primary; }
    #view-label { width: 100%; height: 1; padding: 0 1; color: $text-muted; background: $boost; }
    #sidebar-note { height: 1; color: $text-muted; padding: 0 1; }
    #sidebar.narrow-hidden { display: none; }
    #item-list { height: 1fr; background: transparent; border: none; padding: 0; }
    #main-tabs { width: 1fr; height: 1fr; margin: 0 0 0 1; border: round $primary 40%; }
    #main-tabs:focus-within { border: round $primary; }
    #main-tabs Tabs Tab { padding: 0; margin: 0 1 0 0; }
    TabPane { padding: 0 1; }
    #activity { height: 8; padding: 0 1; background: $surface; border-top: solid $panel; color: $foreground;
                text-wrap: nowrap; text-overflow: ellipsis; }
    #activity.hidden { display: none; }
    #hud { height: 2; padding: 0; background: $panel; color: $foreground; text-wrap: nowrap; text-overflow: ellipsis; }
    .detail { height: auto; width: 100%; padding: 0; }
    .muted { color: $text-muted; }
    #wiki-status { height: auto; color: $text-muted; }
    #wiki-notice, #news-notice, #market-notice, #geo-notice, #brain-notice { height: auto; color: $accent; }
    #wiki-links { height: auto; max-height: 8; border: none; padding: 0; background: transparent; }
    Input { height: 1; padding: 0 1; border: none; background: $surface; }
    Checkbox { height: 1; border: none; padding: 0; background: transparent; width: auto; margin: 0 2 0 0; }
    Checkbox:focus { border: none; color: $primary; text-style: none; }
    Select { height: 1; }
    Select > SelectCurrent { height: 1; border: none; padding: 0 1; }
    Button { max-width: 100%; }
    Input, Select { min-width: 0; max-width: 100%; }
    TabPane Label { width: 100%; height: auto; }
    .row { height: auto; width: 100%; }
    .buttons { width: 100%; height: auto; }
    .buttons Button { width: auto; max-width: 100%; min-width: 0; margin: 0 1 0 0; }
    MenuScreen { background: transparent; }
    #theme-label { width: 14; color: $text-muted; }
    """
    BINDINGS = [
        Binding("f10", "open_menu(0)", show=False),
        Binding("q", "quit", show=False),
        Binding("t", "next_theme", show=False),
        Binding("T", "theme_modal", show=False),
        Binding("b", "toggle_sidebar", show=False),
        Binding("A", "toggle_activity", show=False),
        Binding("r", "refresh", show=False),
        Binding("question_mark", "help", show=False),
        Binding("slash", "wiki_focus", show=False),
        Binding("c", "wiki_cite", show=False),
        Binding("s", "wiki_save", show=False),
        Binding("u", "undo", show=False),
        Binding("escape", "wiki_back", show=False),
        Binding("m", "desk_map", show=False),
        Binding("L", "toggle_live(True)", show=False),
        Binding("l", "toggle_live(True)", show=False),
        Binding("G", "toggle_live_globe(True)", show=False),  # 0.2.2 per-element Live Mode (Desk only)
        Binding("K", "toggle_live_ticker(True)", show=False),
        Binding("U", "toggle_live_updates(True)", show=False),
        Binding("S", "cycle_live_speed(True)", show=False),  # 0.2.2 addendum (Desk only)
        Binding("I", "cycle_update_interval(True)", show=False),
        Binding("0", "show_tab('tab-desk')", show=False),
        *[Binding(str(n), f"show_tab('{tab}')", show=False) for n, tab in enumerate(TABS[1:], start=1)],
    ]
    _MAIN_ONLY = {
        "quit", "next_theme", "theme_modal", "toggle_sidebar", "toggle_activity", "refresh", "help", "show_tab",
        "wiki_focus", "wiki_cite", "wiki_save", "undo", "wiki_back", "desk_map", "toggle_live",
        "toggle_live_globe", "toggle_live_ticker", "toggle_live_updates", "cycle_live_speed", "cycle_update_interval",
    }
    _TAB_LABELS = {
        "tab-desk": ("Desk", "Desk", "Desk"),
        "tab-news": ("News", "News", "News"),
        "tab-markets": ("Markets", "Markets", "Mkts"),
        "tab-geo": ("GEO", "GEO", "GEO"),
        "tab-brain": ("Brain", "Brain", "Brain"),
        "tab-wiki": ("Wikipedia", "Wiki", "Wiki"),
        "tab-status": ("Status", "Status", "Stat"),
    }

    def __init__(self, backend: Any, *, settings: Settings | None = None, demo: bool = False,
                 clock: Callable[[], str] | None = None, now: Callable[[], float] | None = None) -> None:
        super().__init__()
        self.backend = backend
        self.settings = settings or Settings()
        self.demo = demo
        self._clock = clock or (lambda: time.strftime("%H:%M:%S"))
        # 0.2.0: the Desk's clock in ms (the demo desk keeps a fixed time so its pictures do not change)
        self._now_given = now
        self._now: Callable[[], float] = now or (lambda: time.time() * 1000)
        # 0.2.0 one-time theme switch, before the theme is read anywhere (brief §0.1)
        self._migrated = self.settings.migrate_theme()
        self.colour_system = "truecolor"  # set from the real console in on_mount (headless runs are truecolor)
        self.graphics = mapgfx.detect()
        self.desk_watch: list[dict[str, Any]] = []
        self.desk_tape: list[dict[str, Any]] = []
        self.desk_hazards: list[dict[str, Any]] = []
        self.desk_at: dict[str, float] = {}
        self._desk_fail: set[str] = set()
        self._desk_timers: dict[str, Any] = {}
        self._app_focused = True
        self._ticks = 0
        saved = self.settings.load()
        self._sidebar_choice: bool | None = saved["sidebar_hidden"]
        # 0.2.2: three independent Live Mode elements (default all OFF) and the last active combination for L
        self.live: dict[str, bool] = {k: saved[f"live_{k}"] is True for k in LIVE_ELEMENTS}
        self._live_last: list[str] | None = [k[5:] for k in saved["live_last"]] if saved["live_last"] else None
        self.live_speed: str = saved["live_speed"]  # 0.2.2 addendum
        self.live_update_interval: int = saved["live_update_interval"]
        self.desk_every: dict[str, float] = {}
        self.spin_step = 1.5
        self._apply_cadence()
        self._tabs_ready = False
        self._desk_stale = True
        self._menu_open = False
        self._handoff = False
        self._return_focus: Any = None
        self._activity: deque[str] = deque(maxlen=ACTIVITY_H - 3)
        self.menus = self._build_menus()
        # desk state (kept while switching screens)
        self.access: dict[str, Any] = {}
        self.conn = "connecting"
        self.instance: dict[str, Any] = {}
        self.stories: list[dict[str, Any]] = []
        self.feed_errors: list[dict[str, Any]] = []
        self.quotes: list[dict[str, Any]] = []
        self.symbol_hits: list[dict[str, Any]] = []
        self.market_range = "1mo"
        self.hazards: list[dict[str, Any]] = []
        self.hazard_window = "24h"
        self.hazard_kinds = list(HAZARD_KINDS)
        self.note_filter = ""
        self.engines: dict[str, Any] | None = None
        self.model_state: dict[str, Any] | None = None
        self.wiki_named: dict[str, Any] | None = None
        self.wiki_results: list[dict[str, Any]] = []
        self.wiki_query = ""
        self.wiki_heading = ""
        self.wiki_article: dict[str, Any] | None = None
        self.wiki_links: list[dict[str, Any]] = []
        self.wiki_history: list[str] = []
        self.cite_target: str | None = None
        self.undo_brain: tuple[dict[str, Any], int, str] | None = None
        self.selected: dict[str, int] = {}
        self.opened: dict[str, str] = {}
        self._list_key: tuple[str, tuple[str, ...], str] = ("", (), "")

    # ---- themes ---------------------------------------------------------------------------------
    # The 22 Theme objects are built once rather than on every lookup.
    _THEMES: dict[str, Any] | None = None

    _THEMES_BY_SYSTEM: dict[str, dict[str, Any]] = {}

    @property
    def available_themes(self) -> dict[str, Any]:
        system = getattr(self, "colour_system", "truecolor")
        if system in ("256", "standard"):  # 0.2.0 §0.4: the mapped 256/16-colour roles for the two required themes
            if system not in NuzeHubApp._THEMES_BY_SYSTEM:
                NuzeHubApp._THEMES_BY_SYSTEM[system] = {p.id: fallback_palette(p, system).textual() for p in PALETTES}
            return NuzeHubApp._THEMES_BY_SYSTEM[system]
        if NuzeHubApp._THEMES is None:
            NuzeHubApp._THEMES = {palette.id: palette.textual() for palette in PALETTES}
        return NuzeHubApp._THEMES

    def get_theme(self, theme_name: str) -> Any:
        themes = self.available_themes
        return themes.get(theme_name) or themes[DEFAULT]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in self._MAIN_ONLY and len(self.screen_stack) > 1:
            return False
        return True

    # ---- compose ----------------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        options = [(p.name, p.id) for p in PALETTES]
        yield MenuBar(self.menus, brand=f"NuzeHub TUI {__version__}", id="menubar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar") as sidebar:
                sidebar.border_title = "Stories"
                yield Label("Enter opens", id="view-label")
                yield Static("", id="sidebar-note")
                yield ItemList(id="item-list")
            with TabbedContent(id="main-tabs") as tabs:
                tabs.border_title = "NuzeHub"
                with TabPane("Desk", id="tab-desk"):
                    yield DeskView(self.graphics)
                with TabPane("News", id="tab-news"):
                    with VerticalScroll():
                        yield Static("Loading the desk's feeds…", id="news-detail", classes="detail")
                        with Horizontal(classes="buttons"):
                            yield Button("Open article", id="news-open")
                            yield Button("Related in Wikipedia", id="news-related")
                        yield Static("", id="news-notice")
                        yield Static("", id="news-article", classes="detail")
                with TabPane("Markets", id="tab-markets"):
                    with VerticalScroll():
                        with Horizontal(classes="buttons"):
                            for rng in RANGES:
                                yield Button(rng, id=f"rng-{rng}")
                        yield Static("Loading the watchlist…", id="market-detail", classes="detail")
                        yield Input(placeholder="Symbol search, for example nvidia", id="symbol-query")
                        with Horizontal(classes="buttons"):
                            yield Button("Search symbols", id="symbol-search")
                        yield Static("", id="market-notice")
                with TabPane("GEO", id="tab-geo"):
                    with VerticalScroll():
                        with Horizontal(classes="buttons"):
                            for win in HAZARD_WINDOWS:
                                yield Button(win, id=f"win-{win}")
                        with Horizontal(classes="row"):
                            for kind in HAZARD_KINDS:
                                yield Checkbox(kind.capitalize(), True, id=f"kind-{kind}")
                        yield Static("", id="geo-notice")
                        yield Static("Loading hazards…", id="geo-detail", classes="detail")
                with TabPane("Brain", id="tab-brain"):
                    with VerticalScroll():
                        yield Input(placeholder="Filter notes by title, tag or text", id="note-filter")
                        with Horizontal(classes="buttons"):
                            yield Button("Related in Wikipedia", id="note-related")
                            yield Button("Use as Cite target", id="note-target")
                        yield Static("", id="brain-notice")
                        yield Static("Loading notes…", id="note-detail", classes="detail")
                with TabPane("Wikipedia", id="tab-wiki"):
                    with VerticalScroll(id="wiki-scroll"):
                        yield Static("Library: checking…", id="wiki-status")
                        yield Input(placeholder="Search the Wikipedia library", id="wiki-query")
                        with Horizontal(classes="buttons"):
                            yield Button("Search", id="wiki-search")
                            yield Button("Back", id="wiki-back")
                        with Horizontal(classes="buttons"):
                            yield Button("Cite…", id="wiki-cite")
                            yield Button("Save to Brain", id="wiki-save")
                            yield Button("Related", id="wiki-related")
                            yield Button("Undo", id="wiki-undo")
                        yield Static("", id="wiki-notice")
                        yield Static("", id="wiki-reader", classes="detail")
                        yield OptionList(id="wiki-links")
                with TabPane("Status", id="tab-status"):
                    with VerticalScroll():
                        yield Static("Checking…", id="status-body", classes="detail")
                        with Horizontal(classes="row"):
                            yield Label("Theme", id="theme-label")
                            yield Select(options, value=self.settings.load()["theme"], prompt="Theme", id="theme-select", allow_blank=False)
                        with Horizontal(classes="buttons"):
                            yield Button("Refresh", id="status-refresh")
                            yield Button("Choose theme", id="theme-open")
        yield Static("", id="activity", markup=False)
        yield Static("", id="hud")

    async def on_mount(self) -> None:
        if not self.is_headless:
            self.colour_system = str(getattr(self.console, "color_system", None) or "truecolor")
        frozen = getattr(self.backend, "desk_now_ms", None)
        if self._now_given is None and frozen:
            # the demo desk: a fixed time in headless runs (snapshots), a running clock from that time otherwise
            start = time.monotonic()
            self._now = (lambda: float(frozen)) if self.is_headless else (lambda: float(frozen) + (time.monotonic() - start) * 1000)
        for palette in self.available_themes.values():
            self.register_theme(palette)
        saved = self.settings.load()
        self.theme = str(saved["theme"])
        select = self.query_one("#theme-select", Select)
        if select.value != self.theme:
            select.value = self.theme
        # 0.2.0 §0.7: always open on the Desk; the saved tab is no longer restored
        self.query_one("#main-tabs", TabbedContent).active = "tab-desk"
        self.set_class(self.colour_system in ("256", "standard"), "-cfb")
        self.set_class(self.colour_system == "standard", "-c16")
        self.set_class(self.graphics.mode == "text", "-ascii")
        tabs = self.query_one("#main-tabs", TabbedContent)
        for key, tab_id in enumerate(TABS):
            tabs.get_tab(tab_id).tooltip = f"{self._TAB_LABELS[tab_id][0]} ({key})"
        if self._migrated:
            self._note(MIGRATED_NOTE)
        if not self.is_headless:  # a real terminal: say how the map is drawn (not in snapshots)
            self._note(f"Desk map: {self.graphics.mode} ({self.graphics.reason}).")
        self._start_desk_timers()
        self.set_class(self.size.height < SHORT_H, SHORT_CLASS)
        self._apply_activity(self.size.height)
        self._apply_sidebar(self.size.width)
        self._tabs_ready = True
        style_buttons(self)
        self._fit_rows()
        self.call_after_refresh(self._fit_rows)
        self._render_all()
        self._sync_desk()
        self.run_worker(self.boot(), exclusive=True, group="boot")

    # ---- calls ----------------------------------------------------------------------------------
    async def _call(self, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kw)

    async def boot(self) -> None:
        try:
            self.access = await self._call(self.backend.access_status)
        except NuzeHubError as exc:
            self.conn = "offline"
            self._note(str(exc), "error")
            self._render_all()
            return
        if not self.access.get("open"):
            self.conn = "locked"
            self._render_all()
            self._overlay(GateScreen(self._unlock, self._where()), self._gate_done)
            return
        await self.load_everything()

    def _where(self) -> str:
        return "NuzeHub (demo)" if self.demo else f"NuzeHub at {getattr(self.backend, 'base_url', '')}"

    async def _unlock(self, key: str) -> str:
        view = await self._call(self.backend.unlock, key)
        if view.get("open"):
            self.access = view
            return ""
        return str(view.get("error") or "That key does not match.")

    def _gate_done(self, ok: Any) -> None:
        if ok:
            self._note("Unlocked with the host key (not saved).")
            self.run_worker(self.load_everything(), exclusive=True, group="boot")
        else:
            self.exit()

    def _conn_label(self) -> str:
        if self.demo:
            return "demo"
        if self.access.get("open"):
            if not self.access.get("remote"):
                return "host"
            return "trusted" if self.access.get("trusted") else "unlocked"
        return self.conn

    async def load_everything(self) -> None:
        self.conn = "connected"
        await self.load_instance()
        await asyncio.gather(self.load_news(), self.load_markets(), self.load_hazards(), self.load_wiki_status(),
                             self.load_models(), self.desk_load_tape())
        self._desk_mark("instance", bool(self.instance))
        self._note("Desk loaded.")
        self._render_all()

    async def _guarded(self, what: str, coro: Callable[[], Any]) -> bool:
        try:
            await coro()
            return True
        except AccessDenied as exc:
            self.conn = "locked"
            self._note(f"{what}: {exc}", "warning")
            if len(self.screen_stack) == 1:
                self._overlay(GateScreen(self._unlock, self._where()), self._gate_done)
        except NuzeHubError as exc:
            self._note(f"{what}: {exc}", "error")
        return False

    async def load_instance(self) -> None:
        async def run() -> None:
            self.instance = await self._call(self.backend.load_instance)
        await self._guarded("Desk", run)
        self._render_brain()

    async def load_news(self) -> None:
        async def run() -> None:
            urls = desk.feed_urls(self.instance)
            if not urls:
                self.stories, self.feed_errors = [], []
                return
            res = await self._call(self.backend.fetch_news, urls)
            stories = [s for s in res.get("stories") or [] if isinstance(s, dict)]
            stories.sort(key=lambda s: str(s.get("publishedAt") or ""), reverse=True)
            self.stories = stories
            self.feed_errors = list(res.get("errors") or [])
        self._desk_mark("news", await self._guarded("News", run))
        self._render_news()

    async def load_markets(self) -> None:
        async def run() -> None:
            symbols = desk.watchlist(self.instance)
            if not symbols:
                self.quotes = []
                return
            prefs = (self.instance.get("desk") or {}).get("prefs") or {}
            sources = [s.get("id") for s in prefs.get("marketSources") or [] if isinstance(s, dict) and s.get("enabled")]
            res = await self._call(self.backend.get_markets, symbols, self.market_range, sources or None)
            self.quotes = [q for q in res.get("quotes") or [] if isinstance(q, dict)]
        ok = await self._guarded("Markets", run)
        if self.market_range == "1mo":  # the Desk watchlist uses 1mo (brief §5)
            ok = ok and not (self.quotes and all(q.get("error") for q in self.quotes))  # all failed: keep old, mark
            if ok:
                self.desk_watch = list(self.quotes)
            self._desk_mark("markets", ok)
        self._render_markets()

    async def load_hazards(self) -> None:
        async def run() -> None:
            res = await self._call(self.backend.get_hazards, self.hazard_window, list(self.hazard_kinds))
            events: list[dict[str, Any]] = []
            for kind in res.get("results") or []:
                events.extend(e for e in kind.get("events") or [] if isinstance(e, dict))
                if kind.get("error"):
                    self._note(f"GEO {kind.get('kind')}: {kind.get('error')}", "warning")
            events.sort(key=lambda e: (-(e.get("severity") or 0), -(e.get("time") or 0)))
            self.hazards = events
            failed = [k for k in res.get("results") or [] if isinstance(k, dict) and k.get("error") and not k.get("events")]
            self._hazards_all_failed = bool(failed) and len(failed) == len(res.get("results") or [])
        self._hazards_all_failed = False
        ok = await self._guarded("GEO", run)
        if self.hazard_window == "24h" and list(self.hazard_kinds) == list(HAZARD_KINDS):
            ok = ok and not self._hazards_all_failed
            if ok:
                self.desk_hazards = list(self.hazards)
            self._desk_mark("hazards", ok)
        self._render_geo()

    async def load_models(self) -> None:
        async def run() -> None:
            self.engines = await self._call(self.backend.probe_engines)
            self.model_state = await self._call(self.backend.model_status)
        await self._guarded("Model status", run)
        self._update_status()
        self._render_status()

    async def load_wiki_status(self) -> None:
        async def run() -> None:
            self.wiki_named = await self._call(self.backend.wiki_status)
        await self._guarded("Wikipedia status", run)
        if not desk.library_on(self.wiki_named):
            self._clear_wiki("The library is not available, so no results are shown.")
        self._render_wiki()

    # ---- Wikipedia ------------------------------------------------------------------------------
    def _clear_wiki(self, why: str) -> None:
        had = bool(self.wiki_results or self.wiki_article)
        self.wiki_results, self.wiki_article, self.wiki_links, self.wiki_history = [], None, [], []
        if had:
            self._wiki_notice(why)

    def _wiki_notice(self, text: str) -> None:
        self._notice("#wiki-notice", text)

    def _accept(self, answer: dict[str, Any]) -> bool:
        if isinstance(answer.get("status"), dict) and answer["status"].get("state") != "on":
            self.wiki_named = answer["status"]
        ok, why = desk.pinned(answer, self.wiki_named)
        if not ok:
            if answer.get("reason") in ("bad-query", "not-found"):
                self._wiki_notice(why)
            else:
                self._clear_wiki(why)
                self._wiki_notice(why)
            self._render_wiki()
        return ok

    async def wiki_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            self._wiki_notice("Type something to search for, then press Enter.")
            return
        self.wiki_query = query

        async def run() -> None:
            self.wiki_named = await self._call(self.backend.wiki_status)
            if not desk.library_on(self.wiki_named):
                self._clear_wiki(desk.status_summary(self.wiki_named))
                self._wiki_notice(desk.status_summary(self.wiki_named) + " Your search is kept; press Enter to try again.")
                return
            res = await self._call(self.backend.wiki_search, query, 10)
            if not self._accept(res):
                return
            self.wiki_results = list(res.get("results") or [])
            self.wiki_heading = f"Results for “{query}”"
            self._wiki_notice(f"{len(self.wiki_results)} result{'s' if len(self.wiki_results) != 1 else ''} for “{query}”."
                              if self.wiki_results else f"No articles match “{query}”. Try fewer or other words.")
        await self._guarded("Wikipedia search", run)
        self._render_wiki()

    async def wiki_open(self, title: str, *, push: bool = True) -> None:
        async def run() -> None:
            res = await self._call(self.backend.wiki_read, title)
            if not self._accept(res):
                return
            if push and self.wiki_article and self.wiki_article.get("title") != title:
                self.wiki_history.append(str(self.wiki_article.get("title")))
            self.wiki_article = res.get("article") or {}
            self.wiki_links = list(res.get("links") or [])
            self._wiki_notice("")
        await self._guarded("Wikipedia read", run)
        self._render_wiki()

    async def wiki_related(self, title: str, text: str, origin: str) -> None:
        async def run() -> None:
            self.wiki_named = await self._call(self.backend.wiki_status)
            res = await self._call(self.backend.wiki_related, title, text)
            if not self._accept(res):
                return
            self.wiki_results = list(res.get("results") or [])
            self.wiki_heading = f"Related to “{title}” ({origin})"
            self._wiki_notice(f"{len(self.wiki_results)} related article(s) for “{title}”.")
        self.action_show_tab("tab-wiki", refresh=False)
        await self._guarded("Related in Wikipedia", run)
        self._render_wiki()

    async def _save_brain(self, brain: dict[str, Any], what: str) -> bool:
        before = copy.deepcopy(self.instance.get("brain") or {})
        base = int(self.instance.get("rev") or 0)
        res = await self._call(self.backend.save_instance, desk=None, brain=brain, base_rev=base)
        if not res.get("ok"):
            self._note(f"{what}: the desk changed elsewhere. Reloaded; try again.", "warning")
            await self.load_instance()
            return False
        self.instance["brain"] = brain
        self.instance["rev"] = int(res.get("rev") or base + 1)
        self.undo_brain = (before, self.instance["rev"], what)
        self._render_brain()
        return True

    def action_wiki_cite(self) -> None:
        if self._active() == "tab-desk":  # 0.2.0: on the Desk, c filters INTEL to the row's country
            if not self._desk_view().filter_country():
                self._note("Desk: highlight an Intel row or a map country first, then c.")
            return
        if not self.wiki_article:
            self._wiki_notice("Open an article first, then Cite.")
            return
        notes = desk.notes_of(self.instance)
        title = str(self.wiki_article.get("title", ""))
        self._overlay(CiteDialog(title, notes, self.cite_target), self._cite_chosen)

    def _cite_chosen(self, choice: Any) -> None:
        if choice:
            self.run_worker(self._cite(str(choice)), exclusive=True, group="write")

    async def _cite(self, choice: str) -> None:
        if not self.wiki_article:
            return
        c = desk.citation_of(self.wiki_article, via=str((self.wiki_named or {}).get("sourceLabel") or ""))

        async def run() -> None:
            if choice == NEW_NOTE:
                brain, nid = desk.brain_with_new_cited_note(self.instance, c)
                if await self._save_brain(brain, "Cite (new note)"):
                    self.cite_target = nid
                    self._wiki_notice(f"Cited in a new note “Notes on {c['title']}”. u undoes it.")
                return
            brain, added = desk.brain_with_cite(self.instance, choice, c)
            note = next((n for n in desk.notes_of(self.instance) if n.get("id") == choice), {})
            if not added:
                self._wiki_notice(f"“{note.get('title', 'That note')}” already cites this article.")
                return
            if await self._save_brain(brain, "Cite"):
                self.cite_target = choice
                self._wiki_notice(f"Cited in “{note.get('title', '')}”. u undoes it.")
        await self._guarded("Cite", run)
        self._render_wiki()

    def action_wiki_save(self) -> None:
        if not self.wiki_article:
            self._wiki_notice("Open an article first, then Save to Brain.")
            return
        c = desk.citation_of(self.wiki_article, via=str((self.wiki_named or {}).get("sourceLabel") or ""))
        _brain, _nid, existed = desk.brain_with_save(self.instance, c)
        self._overlay(SaveDialog(c["title"], c["excerpt"], existed), self._save_chosen)

    def _save_chosen(self, ok: Any) -> None:
        if ok:
            self.run_worker(self._save_article(), exclusive=True, group="write")

    async def _save_article(self) -> None:
        if not self.wiki_article:
            return
        c = desk.citation_of(self.wiki_article, via=str((self.wiki_named or {}).get("sourceLabel") or ""))

        async def run() -> None:
            brain, _nid, existed = desk.brain_with_save(self.instance, c)
            if existed:
                self._wiki_notice("Already in the Brain (Resources).")
                return
            if await self._save_brain(brain, "Save to Brain"):
                self._wiki_notice("Saved to the Brain in Resources. u undoes it.")
        await self._guarded("Save to Brain", run)
        self._render_wiki()

    def action_undo(self) -> None:
        if not self.undo_brain:
            self._notice_current("Nothing to undo.")
            return
        self.run_worker(self._undo(), exclusive=True, group="write")

    async def _undo(self) -> None:
        if not self.undo_brain:
            return
        before, rev, what = self.undo_brain

        async def run() -> None:
            res = await self._call(self.backend.save_instance, desk=None, brain=before, base_rev=rev)
            if not res.get("ok"):
                self.undo_brain = None
                self._wiki_notice(f"The Brain changed elsewhere after {what}, so Undo was not applied.")
                await self.load_instance()
                return
            self.instance["brain"] = before
            self.instance["rev"] = int(res.get("rev") or rev + 1)
            self.undo_brain = None
            self._wiki_notice(f"Undid {what}.")
            self._note(f"Undid {what}.")
        await self._guarded("Undo", run)
        self._render_brain()
        self._render_wiki()

    def action_wiki_focus(self) -> None:
        self.action_show_tab("tab-wiki", refresh=False)
        self.call_after_refresh(lambda: self.query_one("#wiki-query", Input).focus())

    def action_wiki_back(self) -> None:
        if self._active() == "tab-desk" and self._desk_view().clear_filter():
            return
        if self._active() == "tab-wiki" and self.wiki_history:
            title = self.wiki_history.pop()
            self.run_worker(self.wiki_open(title, push=False), exclusive=True, group="wiki")
            return
        if isinstance(self.focused, Input):
            self.set_focus(None)

    # ---- rendering --------------------------------------------------------------------------------
    def _active(self) -> str:
        try:
            return str(self.query_one("#main-tabs", TabbedContent).active or "tab-news")
        except NoMatches:
            return "tab-news"

    def _notice(self, selector: str, text: str) -> None:
        for w in self.query(selector):
            if isinstance(w, Static):
                w.update(Text(text))

    def _notice_current(self, text: str) -> None:
        sel = {"tab-news": "#news-notice", "tab-markets": "#market-notice", "tab-geo": "#geo-notice",
               "tab-brain": "#brain-notice", "tab-wiki": "#wiki-notice"}.get(self._active())
        if sel:
            self._notice(sel, text)
        self._note(text)

    def _set(self, selector: str, content: Any) -> None:
        for w in self.query(selector):
            if isinstance(w, Static):
                w.update(content if isinstance(content, Text) else Text(str(content)))

    def _list_items(self, tab: str) -> list[str]:
        if tab == "tab-desk":
            return []
        if tab == "tab-news":
            return [f"{desk.when(s.get('publishedAt'))}  {s.get('title', '')}".strip() for s in self.stories]
        if tab == "tab-markets":
            out = []
            for q in self.quotes:
                if q.get("error"):
                    out.append(f"{q.get('symbol')}  —  {q.get('error')}")
                else:
                    out.append(f"{q.get('symbol', ''):<8} {q.get('price', 0):>10.2f} {q.get('changePct', 0):+6.2f}%")
            return out
        if tab == "tab-geo":
            return [f"{e.get('kind', '')[:5]:<6}{e.get('title', '')}" for e in self.hazards]
        if tab == "tab-brain":
            return [f"{n.get('title', 'Untitled')}" for n in self._filtered_notes()]
        if tab == "tab-wiki":
            return [f"{r.get('rank', i + 1)}. {r.get('title', '')}" for i, r in enumerate(self.wiki_results)]
        return ["Connection", "Wikipedia library", "Local model", "This TUI"]

    def _render_list(self) -> None:
        tab = self._active()
        try:
            lst = self.query_one("#item-list", OptionList)
            side = self.query_one("#sidebar")
            label = self.query_one("#view-label", Label)
        except NoMatches:
            return
        items = self._list_items(tab)
        title, hint = LIST_TITLES.get(tab, ("Items", ""))
        # 0.2.2: no no-op rewrites on a tab switch (each title/label assignment repaints the pane)
        if side.border_title != title:
            side.border_title = title
        if side.border_subtitle != f"{len(items)}":
            side.border_subtitle = f"{len(items)}"
        if getattr(self, "_list_hint", None) != hint:
            self._list_hint = hint
            label.update(hint)
        key = (tab, tuple(items), self.theme if tab == "tab-markets" else "")
        if key == self._list_key:
            return
        self._list_key = key
        rows = self._market_rows() if tab == "tab-markets" else [Text(text, no_wrap=True, overflow="ellipsis") for text in items]
        with self.batch_update():
            lst.clear_options()
            lst.add_options([Option(row, id=f"i{i}") for i, row in enumerate(rows)])
        if items:
            lst.highlighted = min(self.selected.get(tab, 0), len(items) - 1)

    def _sel(self, tab: str, items: list[Any]) -> Any:
        if not items:
            return None
        return items[min(self.selected.get(tab, 0), len(items) - 1)]

    def _render_news(self) -> None:
        s = self._sel("tab-news", self.stories)
        if not desk.feed_urls(self.instance):
            body = "No feeds are switched on in the desk. Add them in the web desk (News, Sources)."
        elif not s:
            body = "No stories yet. Press r to refresh."
        else:
            body = (f"{s.get('title', '')}\n{s.get('feedUrl', '')}  ·  {desk.when(s.get('publishedAt'))}\n\n"
                    f"{s.get('summary', '')}\n\n{s.get('url', '')}")
        if self.feed_errors:
            body += f"\n\n{len(self.feed_errors)} feed(s) did not load."
        self._set("#news-detail", body)
        if self.opened.get("news") != (s or {}).get("url"):
            self._set("#news-article", "")
        self._after_render("tab-news")

    def _render_markets(self) -> None:
        q = self._sel("tab-markets", self.quotes)
        body: str | Text
        for rng in RANGES:
            for b in self.query(f"#rng-{rng}"):
                b.set_class(rng == self.market_range, "-current")
        if not q:
            body = "The watchlist is empty. Add symbols in the web desk (Markets)." if not desk.watchlist(self.instance) \
                else "No quotes yet. Press r to refresh."
        elif q.get("error"):
            body = f"{q.get('symbol')}: {q.get('error')}"
        else:
            closes = [p.get("close") for p in q.get("points") or [] if isinstance(p, dict)]
            glyph, colour = self._trend(q)
            change = f"{q.get('change', 0):+.2f} ({q.get('changePct', 0):+.2f}%)"
            # 0.2.2: the trend line and the change in the Desk Watchlist colours (up $success, down $error, flat muted)
            body = Text.assemble(
                (f"{q.get('symbol')}", "bold"), f"  {q.get('name') or ''}\n",
                f"{q.get('price', 0):.2f} {q.get('currency', '')}  ", (f"{glyph} {change}", colour),
                f"  range {self.market_range}\n",
                (desk.sparkline([c for c in closes if c is not None], 48), colour.split(" on ")[-1]), "\n",
                f"source {q.get('source') or '-'}{' (fallback)' if q.get('fallback') else ''}")
        if self.symbol_hits:
            body = Text.assemble(body, "\n\nSymbol search:\n" + "\n".join(
                f"  {h.get('symbol', ''):<8} {h.get('name', '')}  {h.get('exchange', '')}" for h in self.symbol_hits))
        self._set("#market-detail", body)
        self._after_render("tab-markets")

    def _trend(self, q: dict[str, Any]) -> tuple[str, str]:
        """0.2.2 Markets: (indicator, colour) for a quote, as on the Desk Watchlist: ▲ $success up, ▼ $error down,
        – $text-muted flat (ASCII + - =). The colours are the 256/16-colour mapped roles there (desk_palette)."""
        p = self.desk_palette()
        cp = float(q.get("changePct") or 0)
        ascii_only = self.desk_ascii()
        if cp > 0:
            return ("+" if ascii_only else "▲"), p.success
        if cp < 0:
            glyph = "-" if ascii_only else "▼"
            return glyph, (f"#000000 on {p.error}" if self.colour_system == "standard" else p.error)
        return ("=" if ascii_only else "–"), p.muted

    def _market_rows(self) -> list[Text]:
        """0.2.2 Markets list: symbol, price, ▲/▼ change and a coloured trend sparkline per row."""
        p = self.desk_palette()
        rows: list[Text] = []
        for q in self.quotes:
            t = Text(no_wrap=True, overflow="ellipsis")
            if q.get("error"):
                t.append(f"{q.get('symbol')}  —  {q.get('error')}", style=p.muted)
                rows.append(t)
                continue
            glyph, colour = self._trend(q)
            closes = [float(c["close"]) for c in q.get("points") or [] if isinstance(c, dict) and isinstance(c.get("close"), int | float)]
            t.append(f"{q.get('symbol', ''):<8}", style=f"bold {p.foreground}")
            t.append(f" {q.get('price', 0):>10.2f} ", style=p.foreground)
            t.append(f"{glyph}{abs(float(q.get('changePct') or 0)):5.2f}%", style=colour)
            line = spark(closes[-30:], 12, self.desk_ascii())
            if line:
                t.append(" " + line, style=colour.split(" on ")[-1])
            rows.append(t)
        return rows

    def _render_geo(self) -> None:
        e = self._sel("tab-geo", self.hazards)
        for win in HAZARD_WINDOWS:
            for b in self.query(f"#win-{win}"):
                b.set_class(win == self.hazard_window, "-current")
        if not e:
            body = f"No hazards in the last {self.hazard_window} for {', '.join(self.hazard_kinds) or 'no kinds'}."
        else:
            sev = ["info", "minor", "moderate", "major"][int(e.get("severity") or 0) % 4]
            mag = e.get("magnitude")
            magline = "" if mag is None else (f"magnitude {mag} {e.get('magType', '')}".strip() if e.get("kind") == "quake"
                                              else f"wind {mag} kt")
            body = (f"{e.get('title', '')}\n{e.get('place', '')}\nseverity {sev}  {e.get('level', '')}\n"
                    f"{magline}\n{desk.when(e.get('time'))}{'  (ongoing)' if e.get('ongoing') else ''}\n"
                    f"source {e.get('source', '')}\n{e.get('url', '')}")
        self._set("#geo-detail", body)
        self._after_render("tab-geo")

    def _filtered_notes(self) -> list[dict[str, Any]]:
        f = self.note_filter.strip().lower()
        notes = desk.notes_of(self.instance)
        if not f:
            return notes
        return [n for n in notes if f in f"{n.get('title', '')} {' '.join(n.get('tags') or [])} {n.get('body', '')}".lower()]

    def _render_brain(self) -> None:
        n = self._sel("tab-brain", self._filtered_notes())
        if not n:
            body = "No notes match." if self.note_filter else "No notes in the Brain yet."
        else:
            tags = " ".join(f"#{t}" for t in n.get("tags") or [])
            target = "  (Cite target)" if n.get("id") == self.cite_target else ""
            body = f"{n.get('title', '')}{target}\n{n.get('para', '')}  {tags}\n\n{n.get('body', '')}"
        self._set("#note-detail", body)
        self._after_render("tab-brain")

    def _render_wiki(self) -> None:
        self._set("#wiki-status", desk.status_summary(self.wiki_named))
        art = self.wiki_article
        if art:
            body = desk.article_body(str(art.get("title", "")), str(art.get("text") or ""))
            self._set("#wiki-reader", f"{art.get('title', '')}\n{art.get('url', '')}  ·  {desk.LICENSE}\n\n{body}")
        elif self.wiki_results:
            self._set("#wiki-reader", f"{self.wiki_heading}. Enter on a result reads it.")
        else:
            self._set("#wiki-reader", "")
        try:
            links = self.query_one("#wiki-links", OptionList)
            links.clear_options()
            links.add_options([Option(f"→ {link.get('title', '')}", id=f"l{i}") for i, link in enumerate(self.wiki_links)])
            links.display = bool(self.wiki_links)
            for b in self.query("#wiki-back"):
                b.disabled = not self.wiki_history
            for bid in ("#wiki-cite", "#wiki-save"):
                for b in self.query(bid):
                    b.disabled = art is None
            for b in self.query("#wiki-related"):
                b.disabled = art is None
            for b in self.query("#wiki-undo"):
                b.disabled = self.undo_brain is None
        except NoMatches:
            pass
        self._after_render("tab-wiki")

    def _render_status(self) -> None:
        chip, level = desk.model_chip(self.engines, self.model_state)
        url = getattr(self.backend, "base_url", "")
        access = self._conn_label()
        lines = [
            f"Connection   {access}  ·  {url}",
            f"Access       {'host computer (loopback)' if access == 'host' else access}",
            f"Library      {desk.status_summary(self.wiki_named)}",
            f"             {(self.wiki_named or {}).get('path', '')}",
            f"Model        {chip}",
            f"             {'from /api/model-status and probeEngines' if self.model_state else 'from probeEngines'}",
            f"Desk         rev {self.instance.get('rev', '-')}  ·  {len(desk.notes_of(self.instance))} notes  ·  "
            f"{len(self.stories)} stories  ·  {len(self.quotes)} quotes  ·  {len(self.hazards)} hazards",
            f"This TUI     {__version__}  ·  settings {self.settings.path}",
        ]
        if level == "fallback":
            lines.append("             LM Studio answers because Ollama does not. Start Ollama on the server to go back.")
        self._set("#status-body", "\n".join(lines))
        self._after_render("tab-status")

    def _render_all(self) -> None:
        self._render_news()
        self._render_markets()
        self._render_geo()
        self._render_brain()
        self._render_wiki()
        self._render_status()
        self._render_list()
        self._update_status()
        self._render_desk()

    def _after_render(self, tab: str) -> None:
        if self._tabs_ready and self._active() == tab:
            self._render_list()
            self._update_status()

    # ---- events -----------------------------------------------------------------------------------
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "item-list":
            return
        tab = self._active()
        if self.selected.get(tab) == int(event.option_index):
            return
        self.selected[tab] = int(event.option_index)
        {"tab-news": self._render_news, "tab-markets": self._render_markets, "tab-geo": self._render_geo,
         "tab-brain": self._render_brain, "tab-wiki": lambda: None, "tab-status": lambda: None}[tab]()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "wiki-links":
            idx = int(event.option_index)
            if 0 <= idx < len(self.wiki_links):
                self.run_worker(self.wiki_open(str(self.wiki_links[idx].get("title"))), exclusive=True, group="wiki")
            return
        if event.option_list.id != "item-list":
            return
        tab = self._active()
        self.selected[tab] = int(event.option_index)
        if tab == "tab-wiki" and 0 <= event.option_index < len(self.wiki_results):
            self.run_worker(self.wiki_open(str(self.wiki_results[event.option_index].get("title"))), exclusive=True, group="wiki")
        elif tab == "tab-news":
            self._open_story()

    def _open_story(self) -> None:
        s = self._sel("tab-news", self.stories)
        if not s:
            return

        async def run() -> None:
            res = await self._call(self.backend.fetch_article, str(s.get("url")))
            self.opened["news"] = str(s.get("url"))
            text = str(res.get("text") or "") or str(res.get("note") or "Full article not available.")
            self._set("#news-article", text)
        self.run_worker(self._guarded("Article", run), exclusive=True, group="news")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wiki-query":
            self.run_worker(self.wiki_search(event.value), exclusive=True, group="wiki")
        elif event.input.id == "symbol-query":
            await self._symbol_search(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "note-filter":
            self.note_filter = event.value
            self.selected["tab-brain"] = 0
            self._render_brain()
            if self._active() == "tab-brain":
                self._render_list()

    async def _symbol_search(self, query: str) -> None:
        async def run() -> None:
            res = await self._call(self.backend.search_symbols, query)
            self.symbol_hits = list(res.get("hits") or [])
            self._notice("#market-notice", f"{len(self.symbol_hits)} symbol(s) for “{query}”." if self.symbol_hits
                         else f"No symbols for “{query}”. Try a company name or ticker.")
        await self._guarded("Symbol search", run)
        self._render_markets()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cid = str(event.checkbox.id or "")
        if not cid.startswith("kind-") or not self._tabs_ready:
            return
        kind = cid[5:]
        kinds = [k for k in HAZARD_KINDS if (k != kind and k in self.hazard_kinds) or (k == kind and event.value)]
        if kinds == self.hazard_kinds:
            return
        self.hazard_kinds = kinds
        self.run_worker(self.load_hazards(), exclusive=True, group="geo")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = str(event.button.id or "")
        if bid.startswith("rng-"):
            self.market_range = bid[4:]
            self.run_worker(self.load_markets(), exclusive=True, group="markets")
        elif bid.startswith("win-"):
            self.hazard_window = bid[4:]
            self.run_worker(self.load_hazards(), exclusive=True, group="geo")
        elif bid == "news-open":
            self._open_story()
        elif bid == "news-related":
            s = self._sel("tab-news", self.stories)
            if s:
                self.cite_target = None
                self.run_worker(self.wiki_related(str(s.get("title", "")), str(s.get("summary", "")), "News"),
                                exclusive=True, group="wiki")
        elif bid == "note-related":
            n = self._sel("tab-brain", self._filtered_notes())
            if n:
                self.cite_target = str(n.get("id"))
                self.run_worker(self.wiki_related(str(n.get("title", "")), str(n.get("body", ""))[:2000], "Brain"),
                                exclusive=True, group="wiki")
        elif bid == "note-target":
            n = self._sel("tab-brain", self._filtered_notes())
            if n:
                self.cite_target = str(n.get("id"))
                self._notice("#brain-notice", f"Cite target: “{n.get('title', '')}”.")
                self._render_brain()
        elif bid == "symbol-search":
            self.run_worker(self._symbol_search(self.query_one("#symbol-query", Input).value), exclusive=True, group="markets")
        elif bid == "wiki-search":
            self.run_worker(self.wiki_search(self.query_one("#wiki-query", Input).value), exclusive=True, group="wiki")
        elif bid == "wiki-back":
            self.action_wiki_back()
        elif bid == "wiki-cite":
            self.action_wiki_cite()
        elif bid == "wiki-save":
            self.action_wiki_save()
        elif bid == "wiki-related" and self.wiki_article:
            art = self.wiki_article
            self.run_worker(self.wiki_related(str(art.get("title", "")), str(art.get("abstract", "")), "Wikipedia"),
                            exclusive=True, group="wiki")
        elif bid == "wiki-undo":
            self.action_undo()
        elif bid == "status-refresh":
            self.run_worker(self.action_refresh(), exclusive=True, group="boot")
        elif bid == "theme-open":
            self.action_theme_modal()

    # ---- layout (SSHush 0.7.0) --------------------------------------------------------------------
    def on_resize(self, event: Any) -> None:
        self.set_class(event.size.height < SHORT_H, SHORT_CLASS)
        self._apply_activity(event.size.height)
        self._apply_sidebar(event.size.width)
        for dv in self.query(DeskView):
            dv.apply_width(event.size.width)
        self._fit_rows()
        self.call_after_refresh(self._fit_rows)

    def _fit_rows(self) -> None:
        tabs = self.query("#main-tabs")
        if not tabs:
            return
        width = tabs.first().size.width
        if width <= 0:
            return
        self._fit_chrome(width)
        pane = max(width - 4, 1)
        fitted: dict[int, str] = self.__dict__.setdefault("_rows_fit", {})
        for row in self.query(".buttons"):
            if row.screen is not self.screen:
                continue
            buttons = [child for child in row.children if isinstance(child, Button)]
            needed = 0
            first = id(row) not in fitted
            for button in buttons:
                if first:  # 0.2.2: constant styles are set once, not on every tab switch (no no-op relayouts)
                    button.styles.width = "auto"
                    button.styles.max_width = "100%"
                needed += button_width(str(button.label))
            layout = "vertical" if needed > pane and len(buttons) > 1 else "horizontal"
            if fitted.get(id(row)) != layout:
                fitted[id(row)] = layout
                row.styles.layout = layout
                row.styles.height = "auto"

    def _fit_chrome(self, strip: int) -> None:
        level = 0
        for level in range(3):
            needed = sum(len(labels[level]) + 2 for labels in self._TAB_LABELS.values())
            if needed <= strip or level == 2:
                break
        tabs = self.query_one("#main-tabs", TabbedContent)
        for tab_id, labels in self._TAB_LABELS.items():
            tab = tabs.get_tab(tab_id)
            if str(tab.label) != labels[level]:
                tab.label = labels[level]
        bar = self.query_one(MenuBar)
        brand = f"NuzeHub TUI {__version__}" if self.size.width >= 100 else "NuzeHub"
        if bar.brand != brand:
            bar.brand = brand
            bar.refresh()
        select = self.query_one("#theme-select", Select)
        sw = 22 if self.size.width >= 80 else 20
        if getattr(self, "_select_w", None) != sw:
            self._select_w = sw
            select.styles.width = sw

    def _apply_sidebar(self, width: int) -> None:
        sidebar = self.query_one("#sidebar")
        choice = self._sidebar_choice
        shown = ((not choice) if choice is not None else width >= 88) and self._active() != "tab-desk"
        if sidebar.display != shown:  # 0.2.2: assign only on a change (each assignment relayouts the body)
            sidebar.display = shown
        margin = 1 if shown else 0
        if getattr(self, "_tabs_margin", None) != margin:
            self._tabs_margin = margin
            for tabs in self.query("#main-tabs"):
                tabs.styles.margin = (0, 0, 0, margin)
        note = self.query_one("#sidebar-note", Static)
        narrow_note = choice is False and width < 88
        if narrow_note and not note.display:
            note.update("Shown. Narrow. Press b.")
        if note.display != narrow_note:
            note.display = narrow_note

    def _sidebar_shown(self) -> bool:
        found = self.query("#sidebar")
        return bool(found and found.first().display)

    def _activity_shown(self) -> bool:
        found = self.query("#activity")
        return bool(found and not found.first().has_class("hidden"))

    def action_toggle_activity(self) -> None:
        self._activity_hidden = self._activity_shown()
        self._apply_activity(self.size.height)

    def _apply_activity(self, height: int) -> None:
        found = self.query("#activity")
        if found:
            choice = getattr(self, "_activity_hidden", None)
            found.first().set_class(choice if choice is not None else height < SHORT_H, "hidden")

    def action_toggle_sidebar(self) -> None:
        hidden = self._sidebar_shown()
        self._sidebar_choice = hidden
        self._apply_sidebar(self.size.width)
        self.settings.save({"sidebar_hidden": hidden})

    # ---- status pane (activity + 2-row HUD) -------------------------------------------------------
    def notify(self, message: str, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        super().notify(message, *args, **kwargs)
        self._note(str(message), str(kwargs.get("severity", "information")))

    def _note(self, text: str, severity: str = "information") -> None:
        level = {"information": "INFO", "warning": "WARN", "error": "ERROR"}.get(severity, "INFO")
        line = " ".join(str(text).split())
        if not line:
            return
        self._activity.append(f"{self._clock()} {level:<5} {line}")
        self._update_status()

    def _update_status(self) -> None:
        try:
            activity = self.query_one("#activity", Static)
            hud = self.query_one("#hud", Static)
        except NoMatches:
            return
        tab = self._TAB_LABELS.get(self._active(), ("",))[0]
        tabs = self.query("#main-tabs")
        if tabs:
            # only assign when changed: each assignment repaints the whole tab container (and the Desk map under it),
            # which the 1 s Desk clock did every second (the ~1.45 MB/min idle output)
            box, title, subtitle = tabs.first(), f"NuzeHub: {tab}" if tab else "NuzeHub", self._conn_label()
            if box.border_title != title:
                box.border_title = title
            if box.border_subtitle != subtitle:
                box.border_subtitle = subtitle
        chip, level = desk.model_chip(self.engines, self.model_state)
        conn = self._conn_label()
        on_desk = self._active() == "tab-desk"
        lines = [
            f"{conn.upper():<9} {getattr(self.backend, 'base_url', '')}  ·  {tab or '-'}  ·  "
            f"{'demo desk (fictional data)' if self.demo else 'live desk'}",
            f"  log: {len(self._activity)} recent messages · the host key is never shown or saved",
        ]
        lines += [f"  {item}" for item in self._activity]
        text = "\n".join(lines)
        if text != getattr(self, "_activity_text", None):  # the 1 s Desk clock calls this; skip unchanged relayouts
            self._activity_text = text
            activity.update(text)
        theme = self.current_theme
        label = f"bold {theme.background or '#000000'} on {theme.primary or '#4493f8'}"
        chip_style = label
        if level == "fallback":
            chip_style = f"bold {theme.background or '#000000'} on {theme.warning or '#d29922'}"
        elif level == "down":
            chip_style = f"bold {theme.background or '#000000'} on {theme.error or '#f85149'}"

        def pairs(items: list[tuple[str, str, str]]) -> list[Any]:
            out: list[Any] = []
            for key, value, style in items:
                out += [(f" {key} ", style), f" {value} "]
            return out

        lib = desk.status_summary(self.wiki_named).replace("Library ", "")
        row1 = [("CONN", conn, label), ("MODEL", chip, chip_style), ("LIB", lib, label)]
        row2 = [("TAB", tab or "-", label), ("THEME", get(self.theme).name, label),
                ("NOTES", str(len(desk.notes_of(self.instance))), label), ("HELP", "? keys  F10 menu", label)]
        if on_desk:  # 0.2.0 rows 3-5: FEEDS / STORIES chips and the clocks, on the Desk only
            ok, total = deskdata.feeds_chip(self.instance, self.feed_errors)
            feeds_style = label if ok == total else f"bold {theme.background or '#000000'} on {theme.warning or '#d29922'}"
            row1 += [("FEEDS", f"{ok}/{total}", feeds_style), ("STORIES", str(len(self.stories)), label)]
            row2 = [("TAB", tab or "-", label), ("THEME", get(self.theme).name, label), ("HELP", "? keys  F10 menu", label),
                    ("UTC", self._desk_clock(), label)]
        hud_key = (tuple(row1), tuple(row2))
        if hud_key != getattr(self, "_hud_key", None):  # unchanged second: nothing to repaint
            self._hud_key = hud_key
            hud.update(Text.assemble(*pairs(row1), "\n", *pairs(row2), no_wrap=True), layout=False)  # #hud is a fixed 2 rows: repaint only (§5 CPU)

    # ---- tabs / themes ----------------------------------------------------------------------------
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if not self._tabs_ready or event.tabbed_content.id != "main-tabs":
            return
        tab_id = str(event.pane.id or "")
        if tab_id not in TABS:
            return
        if self.settings.load()["active_tab"] != tab_id:
            self.settings.save({"active_tab": tab_id})
        # 0.2.2: one batched paint per switch; loaded tab data is reused (nothing is cleared or re-fetched), and the
        # Desk is re-rendered only when something changed while it was hidden
        with self.batch_update():
            self._apply_sidebar(self.size.width)
            self._render_list()
            self._update_status()
            self._sync_desk()
            if tab_id == "tab-desk" and self._desk_stale:
                self._render_desk()
        self.call_after_refresh(self._fit_rows)

    def action_show_tab(self, tab_id: str, refresh: bool = True) -> None:
        del refresh
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active == tab_id:  # 0.2.2: already there: no blur/refocus flash, no repaint
            return
        self.set_focus(None)
        with self.batch_update():
            tabs.active = tab_id
            self._render_list()
            self._update_status()
        self.call_after_refresh(self._focus_tab)

    def _focus_tab(self) -> None:
        strip = self.query("#main-tabs Tabs")
        if strip:
            strip.first().focus()

    def action_next_theme(self) -> None:
        current = self.theme if self.theme in NAMES else NAMES[0]
        self._apply_theme(NAMES[(NAMES.index(current) + 1) % len(NAMES)])

    def action_theme_modal(self) -> None:
        self._overlay(ThemeModal(), self._theme_chosen)

    def _theme_chosen(self, theme_id: Any) -> None:
        if theme_id:
            self._apply_theme(str(theme_id))

    def action_set_theme(self, theme_id: str) -> None:
        if theme_id in NAMES:
            self._apply_theme(theme_id)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "theme-select" or not isinstance(event.value, str):
            return
        if event.value != event.select.value:
            return  # a stale Changed from before a programmatic set; applying it made two themes ping-pong
        if event.value != self.theme:
            self._apply_theme(event.value)

    def _apply_theme(self, theme_id: str) -> None:
        self.settings.save({"theme": theme_id})
        self.theme = theme_id
        self._update_status()
        self._render_desk()
        for widget in self.query("#theme-select"):
            if isinstance(widget, Select) and widget.value != theme_id:
                widget.value = theme_id

    async def action_refresh(self) -> None:
        if not self.access.get("open"):
            await self.boot()
            return
        self._note("Refreshing…")
        await self.load_everything()

    def action_help(self) -> None:
        self._overlay(HelpModal())

    def action_about(self) -> None:
        self._overlay(AboutModal())

    # ---- overlays and menus (SSHush 0.7.0) --------------------------------------------------------
    def _overlay(self, screen: Any, callback: Any = None) -> None:
        if len(self.screen_stack) == 1 and not self._handoff:
            self._return_focus = self.focused
        self._handoff = False

        def done(result: Any) -> None:
            if callback is not None:
                callback(result)
            if len(self.screen_stack) == 1 and not self._handoff:
                self.call_after_refresh(self._restore_focus, self._return_focus)
            self.call_after_refresh(self._sync_desk)

        self.push_screen(screen, done)
        self._sync_desk()

    def _restore_focus(self, target: Any) -> None:
        if len(self.screen_stack) > 1:
            return
        if target is not None and target.is_attached and target.focusable and target.display:
            self.set_focus(target)
        else:
            self.set_focus(None)

    def _build_menus(self) -> list[Menu]:
        def file_items() -> list[Item]:
            return [Item("Refresh", "refresh", "r"), SEP, Item("Quit", "quit", "q")]

        def view_items() -> list[Item]:
            names = ("News", "Markets", "GEO", "Brain", "Wikipedia", "Status")
            return [
                Item("Desk", "show_tab('tab-desk')", "0"),
                *[Item(n, f"show_tab('{t}')", str(i)) for i, (n, t) in enumerate(zip(names, TABS[1:], strict=True), start=1)],
                SEP,
                Item("List pane", "toggle_sidebar", "b", checked=lambda: self._sidebar_shown()),
                Item("Activity panel", "toggle_activity", "A", checked=lambda: self._activity_shown()),
                Item("Live Mode (All)", "toggle_live", "L", checked=lambda: self.live_state() == "full"),
                Item("Live: Globe Spin", "toggle_live_globe", "G", checked=lambda: self.live["globe"]),
                Item("Live: Stock Ticker", "toggle_live_ticker", "K", checked=lambda: self.live["ticker"]),
                Item("Live: Auto-Updates", "toggle_live_updates", "U", checked=lambda: self.live["updates"]),
                Item(f"Live Speed: {SPEED_NAMES[self.live_speed]}", "cycle_live_speed", "S"),
                Item(f"Auto-Update: every {self.live_update_interval}s", "cycle_update_interval", "I"),
                SEP,
                Item("Next theme", "next_theme", "t"),
                Item("Themes…", "theme_modal", "T"),
            ]

        def wiki_items() -> list[Item]:
            has = lambda: self.wiki_article is not None  # noqa: E731
            return [
                Item("Search", "wiki_focus", "/"),
                Item("Back", "wiki_back", "Esc", enabled=lambda: bool(self.wiki_history)),
                Item("Cite…", "wiki_cite", "c", enabled=has),
                Item("Save to Brain", "wiki_save", "s", enabled=has),
                Item("Undo", "undo", "u", enabled=lambda: self.undo_brain is not None),
            ]

        def theme_items() -> list[Item]:
            def is_on(pid: str) -> Callable[[], bool]:
                return lambda: self.theme == pid
            return [Item(p.name, f"set_theme('{p.id}')", checked=is_on(p.id), radio=True) for p in PALETTES]

        def help_items() -> list[Item]:
            return [Item("Help", "help", "?"), Item("About NuzeHub TUI", "about")]

        return [
            Menu("File", file_items),
            Menu("View", view_items),
            Menu("Wikipedia", wiki_items, "w"),
            Menu("Themes", theme_items, "t"),
            Menu("Help", help_items),
        ]

    def action_open_menu(self, index: int = 0) -> None:
        if self._menu_open or len(self.screen_stack) > 1:
            return
        bar = self.query_one(MenuBar)
        self._menu_open = True

        def done(result: str | None) -> None:
            self._menu_open = False
            if result and result.startswith("__menu__"):
                self._handoff = True
                self.call_after_refresh(self.action_open_menu, int(result[8:]))
            elif result:
                self._handoff = True
                self.call_after_refresh(self._run_from_menu, result)

        self._overlay(MenuScreen(bar, index), done)

    def open_menu(self, index: int) -> None:
        self.action_open_menu(index)

    def _run_from_menu(self, action: str) -> None:
        depth = len(self.screen_stack)
        self.run_menu_action(action)
        if len(self.screen_stack) == depth:
            self._handoff = False
            if not action.startswith(("show_tab(", "set_theme(")):
                self._restore_focus(self._return_focus)

    def run_menu_action(self, action: str) -> None:
        if action.startswith("show_tab("):
            self.action_show_tab(action.split("'")[1])
            return
        if action.startswith("set_theme("):
            self.action_set_theme(action.split("'")[1])
            return
        method = getattr(self, f"action_{action}", None)
        if method is None:
            self._note(f"Menu action {action!r} is not available.", "warning")
            return
        result = method()
        if inspect.isawaitable(result):
            self.run_worker(result, exclusive=False)

    def on_key(self, event: Any) -> None:
        if len(self.screen_stack) > 1 or not str(event.key).startswith("alt+"):
            return
        letter = str(event.key)[-1]
        if self._active() == "tab-desk" and letter in "12345678" and len(str(event.key)) == 5:
            event.stop()  # 0.2.0 §9 Q5: Alt+1..Alt+8 toggle the map layers
            self._desk_view().set_layer(int(letter) - 1)
            return
        for index, menu in enumerate(self.menus):
            if menu.hotkey == letter:
                event.stop()
                self.action_open_menu(index)
                return


    # ---- 0.2.0 Desk ------------------------------------------------------------------------------
    def now_ms(self) -> float:
        return float(self._now())

    def _desk_view(self) -> DeskView:
        return self.query_one(DeskView)

    def desk_palette(self) -> Any:
        p = get(self.theme)
        return fallback_palette(p, self.colour_system) if self.colour_system in ("256", "standard") else p

    def desk_ascii(self) -> bool:
        return self.graphics.mode == "text"

    def desk_failed(self, source: str) -> bool:
        return source in self._desk_fail

    def _desk_mark(self, source: str, ok: bool) -> None:
        """Stale data is kept and marked ("stale 5m"), never blanked."""
        if ok:
            self.desk_at[source] = self.now_ms()
            self._desk_fail.discard(source)
        else:
            self._desk_fail.add(source)

    def _render_desk(self) -> None:
        if not self._tabs_ready:
            return
        if self._active() != "tab-desk":
            self._desk_stale = True  # 0.2.2: painted once on return to the Desk, not while it is hidden
            return
        self._desk_stale = False
        for dv in self.query(DeskView):
            dv.render_all()
        self._update_status()

    def _desk_clock(self) -> str:
        ms = self.now_ms()
        utc = time.strftime("%H:%M:%S", time.gmtime(ms / 1000))
        loc = time.localtime(ms / 1000)
        return f"{utc} · {time.strftime('%Z', loc)} {time.strftime('%H:%M', loc)}"

    # timers: created once, all paused unless the Desk is visible. 0.2.2 per-element Live Mode (all OFF by default): OFF
    # runs only the clock (the map and the tape move by hand, nothing polls; startup load and r still work). Each element
    # runs its own timers: globe -> spin, ticker -> tape (both only while the Desk is in front, with no modal or menu, and
    # the terminal has focus), updates -> the polls and the alert rotation (while the Desk is visible).
    # The defaults (live_speed "smooth", live_update_interval 30 s); the running values are in ``desk_every`` and
    # ``spin_step`` (0.2.2 addendum: View > Live Speed / Auto-Update, S / I on the Desk, settings.json).
    DESK_EVERY = {"alerts": 7.0, "clock": 1.0, "news": 30.0, "markets": 30.0, "hazards": 30.0,
                  "instance": 30.0, "spin": 0.125, "tape": 0.14}
    LIVE_POLLS = ("alerts", "news", "markets", "hazards", "instance")
    SOURCE_POLLS = ("news", "markets", "hazards", "instance")  # follow live_update_interval
    LIVE_MOTION = ("spin", "tape")
    TIMER_ELEMENT = {"spin": "globe", "tape": "ticker", **dict.fromkeys(LIVE_POLLS, "updates")}
    SPIN_STEP = 1.5  # degrees of longitude per step at "smooth" (8 fps, 12°/s)

    def _apply_cadence(self) -> None:
        spin_s, step, tape_s = SPEEDS[self.live_speed]
        every = dict(self.DESK_EVERY)
        every.update(spin=spin_s, tape=tape_s, **dict.fromkeys(self.SOURCE_POLLS, float(self.live_update_interval)))
        self.desk_every, self.spin_step = every, step

    def _desk_jobs(self) -> dict[str, Callable[[], Any]]:
        return {"alerts": self._desk_alert_tick, "clock": self._desk_clock_tick,
                "news": self._desk_refresh_news, "markets": self._desk_refresh_markets,
                "hazards": self._desk_refresh_hazards, "instance": self._desk_refresh_instance,
                "spin": self._desk_spin_step, "tape": self._desk_tape_step}

    def _start_desk_timers(self, names: tuple[str, ...] | None = None) -> None:
        """Create (or, for a new cadence, re-create) Desk timers, paused; ``_sync_desk`` resumes the ones that run."""
        for name, job in self._desk_jobs().items():
            if names is not None and name not in names:
                continue
            old = self._desk_timers.get(name)
            if old is not None:
                old.stop()
            self._desk_timers[name] = self.set_interval(self.desk_every[name], job, pause=True, name=f"desk-{name}")

    def set_live_speed(self, speed: str) -> None:
        if speed not in LIVE_SPEEDS:
            return
        self.live_speed = speed
        self.settings.save({"live_speed": speed})
        self._apply_cadence()
        if self._desk_timers:
            self._start_desk_timers(self.LIVE_MOTION)
            self._sync_desk()
        spin_s, step, tape_s = SPEEDS[speed]
        self._note(f"Live Speed: {SPEED_NAMES[speed]} (globe +{step:g}° at {1 / spin_s:.0f} fps, ticker 1 cell / {tape_s:g} s).")

    def set_update_interval(self, seconds: int) -> None:
        self.live_update_interval = max(UPDATE_MIN, min(UPDATE_MAX, int(seconds)))
        self.settings.save({"live_update_interval": self.live_update_interval})
        self._apply_cadence()
        if self._desk_timers:
            self._start_desk_timers(self.SOURCE_POLLS)
            self._sync_desk()
        self._note(f"Auto-Update: every {self.live_update_interval}s (when Live: Auto-Updates is on).")

    def action_cycle_live_speed(self, from_key: bool = False) -> None:
        if from_key and self._active() != "tab-desk":
            return
        self.set_live_speed(LIVE_SPEEDS[(LIVE_SPEEDS.index(self.live_speed) + 1) % len(LIVE_SPEEDS)])

    def action_cycle_update_interval(self, from_key: bool = False) -> None:
        if from_key and self._active() != "tab-desk":
            return
        nxt = next((c for c in UPDATE_CHOICES if c > self.live_update_interval), UPDATE_CHOICES[0])
        self.set_update_interval(nxt)

    def desk_visible(self) -> bool:
        return self._tabs_ready and self._active() == "tab-desk" and self.is_running

    def desk_live(self) -> bool:
        return self.desk_visible() and len(self.screen_stack) == 1 and self._app_focused

    @property
    def live_mode(self) -> bool:
        """True when any Live Mode element is on (the 0.2.1 single switch, kept for the chip and older callers)."""
        return any(self.live.values())

    def live_state(self) -> str:
        """``off``, ``partial`` or ``full`` (the LIVE chip and View > Live Mode (All))."""
        n = sum(self.live.values())
        return "off" if n == 0 else "full" if n == len(self.live) else "partial"

    def _sync_desk(self) -> None:
        if not self._desk_timers:
            return
        visible = self.desk_visible()
        front = self.desk_live()
        for name, timer in self._desk_timers.items():
            run = visible
            if name in self.LIVE_POLLS:
                run = visible and self.live["updates"]
            elif name in self.LIVE_MOTION:
                run = front and self.live[self.TIMER_ELEMENT[name]]
            if run and timer._active.is_set() is False:
                timer.resume()
            elif not run:
                timer.pause()
        if visible and self.live["updates"] and self.access.get("open"):
            now = self.now_ms()
            for source, job in (("news", self._desk_refresh_news), ("markets", self._desk_refresh_markets),
                                ("hazards", self._desk_refresh_hazards), ("instance", self._desk_refresh_instance)):
                at = self.desk_at.get(source)
                if at is not None and now - at > self.desk_every[source] * 1000:
                    job()

    def desk_timer_states(self) -> dict[str, bool]:
        """Which Desk timers are running (for the state-flow tests and the performance log)."""
        return {name: bool(timer._active.is_set()) for name, timer in self._desk_timers.items()}

    def action_toggle_live(self, from_key: bool = False) -> None:
        """Master switch: L on the Desk, the LIVE chip, or View > Live Mode (All). Any element on: all off (the
        combination is remembered). All off: the remembered combination comes back, or all three."""
        if from_key and self._active() != "tab-desk":
            return
        if self.live_mode:
            self._live_last = [k for k in LIVE_ELEMENTS if self.live[k]]
            self.set_live_elements(dict.fromkeys(LIVE_ELEMENTS, False))
        else:
            back = self._live_last or list(LIVE_ELEMENTS)
            self.set_live_elements({k: k in back for k in LIVE_ELEMENTS})

    def _toggle_element(self, element: str, from_key: bool) -> None:
        if from_key and self._active() != "tab-desk":
            return
        self.set_live_elements({**self.live, element: not self.live[element]}, element)

    def action_toggle_live_globe(self, from_key: bool = False) -> None:
        self._toggle_element("globe", from_key)

    def action_toggle_live_ticker(self, from_key: bool = False) -> None:
        self._toggle_element("ticker", from_key)

    def action_toggle_live_updates(self, from_key: bool = False) -> None:
        self._toggle_element("updates", from_key)

    def set_live(self, on: bool) -> None:
        """All three elements on or off (0.2.1 API; the master switch's memory is not changed)."""
        self.set_live_elements(dict.fromkeys(LIVE_ELEMENTS, bool(on)))

    def set_live_elements(self, wanted: dict[str, bool], changed: str | None = None) -> None:
        self.live = {k: bool(wanted.get(k)) for k in LIVE_ELEMENTS}
        if self.live_mode:
            self._live_last = [k for k in LIVE_ELEMENTS if self.live[k]]
        patch: dict[str, Any] = {f"live_{k}": v for k, v in self.live.items()}
        patch["live_last"] = [f"live_{k}" for k in self._live_last] if self._live_last else None
        self.settings.save(patch)
        self._sync_desk()
        for dv in self.query(DeskView):
            dv.paint_live()
        on = [LIVE_NAMES[k] for k in LIVE_ELEMENTS if self.live[k]]
        state = self.live_state()
        if changed is not None:
            head = f"Live: {LIVE_NAMES[changed]} {'ON' if self.live[changed] else 'OFF'}."
        else:
            head = {"off": "Live Mode OFF.", "partial": "Live Mode ON (partial).", "full": "Live Mode ON (all)."}[state]
        self._note(f"{head} Active: {', '.join(on) if on else 'none'}.")

    def _desk_spin_step(self) -> None:
        if self.live["globe"] and self.desk_live():
            self._desk_view().rotate(self.spin_step)

    def _desk_tape_step(self) -> None:
        if self.live["ticker"] and self.desk_live():
            self._desk_view().scroll_tape()

    def on_app_focus(self) -> None:
        self._app_focused = True
        self._sync_desk()

    def on_app_blur(self) -> None:
        self._app_focused = False
        self._sync_desk()

    def _desk_alert_tick(self) -> None:
        for dv in self.query(DeskView):
            dv.rotate_alerts()

    def _desk_clock_tick(self) -> None:
        self._ticks += 1
        self._update_status()
        for dv in self.query(DeskView):
            minute = int(self.now_ms() // 60000)
            if minute != dv.minute:
                dv.render_all()
            elif dv.focus_running() or self._ticks % 60 == 0:
                dv.now_ms = self.now_ms()
                dv.paint_focus()

    def _desk_refresh_news(self) -> None:
        self.run_worker(self._desk_news(), exclusive=True, group="desk-news")

    async def _desk_news(self) -> None:
        await self.load_news()
        self._render_desk()

    def _desk_refresh_markets(self) -> None:
        self.run_worker(self._desk_markets(), exclusive=True, group="desk-markets")

    async def _desk_markets(self) -> None:
        async def run() -> None:
            symbols = desk.watchlist(self.instance)
            if not symbols:
                self.desk_watch = []
                return
            res = await self._call(self.backend.get_markets, symbols, "1mo", None)
            quotes = [q for q in res.get("quotes") or [] if isinstance(q, dict)]
            if quotes and all(q.get("error") for q in quotes):  # every source failed: keep and mark the old values
                raise NuzeHubError("no quote source answered")
            self.desk_watch = quotes
        self._desk_mark("markets", await self._guarded("Desk markets", run))
        await self.desk_load_tape()
        self._render_desk()

    async def desk_load_tape(self) -> None:
        async def run() -> None:
            res = await self._call(self.backend.get_markets, list(deskdata.TAPE_SYMBOLS), "5d", None)
            quotes = [q for q in res.get("quotes") or [] if isinstance(q, dict)]
            if quotes and all(q.get("error") for q in quotes):
                raise NuzeHubError("no quote source answered")
            self.desk_tape = quotes
        self._desk_mark("tape", await self._guarded("Desk tape", run))

    def _desk_refresh_hazards(self) -> None:
        self.run_worker(self._desk_hazards(), exclusive=True, group="desk-hazards")

    async def _desk_hazards(self) -> None:
        async def run() -> None:
            res = await self._call(self.backend.get_hazards, "24h", list(HAZARD_KINDS))
            results = [k for k in res.get("results") or [] if isinstance(k, dict)]
            if results and all(k.get("error") and not k.get("events") for k in results):
                raise NuzeHubError("no hazard source answered")
            self.desk_hazards = deskdata.flat_hazards(results)
        self._desk_mark("hazards", await self._guarded("Desk hazards", run))
        self._render_desk()

    def _desk_refresh_instance(self) -> None:
        self.run_worker(self._desk_instance(), exclusive=True, group="desk-instance")

    async def _desk_instance(self) -> None:
        async def run() -> None:
            self.instance = await self._call(self.backend.load_instance)
        self._desk_mark("instance", await self._guarded("Desk", run))
        self._render_desk()

    def desk_start_focus(self, minutes: int) -> None:
        self.run_worker(self._desk_focus(minutes), exclusive=True, group="write")

    async def _desk_focus(self, minutes: int) -> None:
        """Focus 25m/50m: the Desk's only write. The latest desk is read first and only ``focus`` changes in it
        (a saveInstance merge); a conflict reloads and tries once more."""
        async def run() -> None:
            for _attempt in range(2):
                latest = await self._call(self.backend.load_instance)
                merged = copy.deepcopy(latest.get("desk") or {})
                merged["focus"] = deskdata.start_focus(minutes, self.now_ms())
                res = await self._call(self.backend.save_instance, desk=merged, brain=None, base_rev=int(latest.get("rev") or 0))
                if res.get("ok"):
                    latest["desk"] = merged
                    latest["rev"] = int(res.get("rev") or 0)
                    self.instance = latest
                    self._note(f"Focus {minutes}m started.")
                    return
            self._note("Focus: the desk changed elsewhere twice; not started.", "warning")
        await self._guarded("Focus", run)
        self._render_desk()

    def desk_open_story(self, url: str) -> None:
        idx = next((i for i, s in enumerate(self.stories) if str(s.get("url")) == url), None)
        if idx is None:
            return
        self.selected["tab-news"] = idx
        self.action_show_tab("tab-news")
        self._render_news()
        self._open_story()

    def desk_open_symbol(self, symbol: str) -> None:
        idx = next((i for i, q in enumerate(self.quotes) if str(q.get("symbol")) == symbol), 0)
        self.selected["tab-markets"] = idx
        self.action_show_tab("tab-markets")
        self._render_markets()

    def action_desk_map(self) -> None:
        if self._active() == "tab-desk":
            self._desk_view().toggle_map()


def run_tui(backend: Any, *, demo: bool, state: Path | None = None) -> None:
    force_truecolor()  # 0.1.1: before the App and its console exist (ssh does not forward COLORTERM)
    NuzeHubApp(backend, settings=Settings(state) if state else None, demo=demo).run()
