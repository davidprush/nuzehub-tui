"""Dialogs: Gate (host key), Cite (note picker + New note), Save to Brain, Themes, Help, About.

Same frame as SSHush 0.7.0 dialogs (round $primary border on $surface, compact role-coloured buttons).
Inside a dialog letters and digits are typed text; Esc or the dismiss button closes it.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from nuzehub_tui import __version__
from nuzehub_tui.themes import PALETTES
from nuzehub_tui.ui.dlayout import style_buttons

DIALOG_CSS = """
NzModal { align: center middle; background: transparent; }
.dialog { width: 80; max-width: 94%; height: auto; max-height: 88%; padding: 0 1;
          border: round $primary; background: $surface; }
.dialog.tall { height: auto; max-height: 88%; }
#theme-options, #cite-notes { height: auto; max-height: 14; border: none; padding: 0; }
.dialog VerticalScroll { height: auto; max-height: 14; }
.dlg-title { text-style: bold; color: $accent; height: 1; padding: 0; }
.hint { color: $text-muted; height: auto; width: 100%; padding: 0; }
.dlg-error { color: $error; height: auto; width: 100%; }
.buttons { height: auto; width: 100%; padding: 0; }
.buttons Button { width: auto; max-width: 100%; margin: 0 1 0 0; min-width: 0; }
"""


class NzModal(ModalScreen[Any]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def on_mount(self) -> None:
        style_buttons(self)

    def action_cancel(self) -> None:
        self.dismiss(None)


class GateScreen(NzModal):
    """Unlock with the host key. A wrong key keeps what was typed and says exactly what to do."""

    def __init__(self, unlock: Any, where: str) -> None:
        super().__init__()
        self._unlock = unlock
        self._where = where

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="gate-dialog"):
            yield Label("Unlock NuzeHub", classes="dlg-title")
            yield Label(
                f"{self._where} asks this session for the host key. Type the Remote API key from the web desk "
                "(Settings, Remote) on the server, then press Enter or Unlock. It is not saved.",
                classes="hint",
            )
            yield Input(placeholder="Host key", password=True, id="gate-key")
            yield Static("", id="gate-error", classes="dlg-error")
            with Horizontal(classes="buttons"):
                yield Button("Unlock", id="gate-unlock", variant="primary")
                yield Button("Quit", id="gate-quit")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#gate-key", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    async def _try(self) -> None:
        field = self.query_one("#gate-key", Input)
        key = field.value
        err = self.query_one("#gate-error", Static)
        if not key.strip():
            err.update("Type the host key first, then press Unlock.")
            return
        try:
            message = await self._unlock(key)
        except Exception as exc:  # noqa: BLE001 - shown as a sentence; the key is never part of it
            message = str(exc)
        if message:
            err.update(f"{message} Check the key and press Unlock again.")
            field.focus()
            return
        self.dismiss(True)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        await self._try()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "gate-quit":
            self.dismiss(False)
        else:
            await self._try()


NEW_NOTE = "__new__"


class CiteDialog(NzModal):
    """Cite in: pick a note (the default target first) or New note."""

    def __init__(self, title: str, notes: list[dict[str, Any]], default_id: str | None) -> None:
        super().__init__()
        self._title = title
        self._notes = notes
        self._default = default_id

    def compose(self) -> ComposeResult:
        options = [Option("+ New note", id=NEW_NOTE)]
        ordered = sorted(self._notes, key=lambda n: 0 if n.get("id") == self._default else 1)
        for note in ordered:
            label = str(note.get("title") or "Untitled")
            if note.get("id") == self._default:
                label += "  (from Related)"
            options.append(Option(label, id=str(note.get("id"))))
        with Vertical(classes="dialog tall", id="cite-dialog"):
            yield Label(f"Cite “{self._title}” in", classes="dlg-title")
            yield Label("Pick a note and press Enter, or New note. A note cites an article once. Esc cancels.",
                        classes="hint")
            yield OptionList(*options, id="cite-notes")
            with Horizontal(classes="buttons"):
                yield Button("Cite", id="cite-ok", variant="primary")
                yield Button("Cancel", id="cite-cancel")

    def on_mount(self) -> None:
        super().on_mount()
        lst = self.query_one("#cite-notes", OptionList)
        lst.highlighted = 1 if self._default and len(self._notes) else 0
        lst.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "cite-cancel":
            self.dismiss(None)
            return
        lst = self.query_one("#cite-notes", OptionList)
        idx = lst.highlighted
        self.dismiss(lst.get_option_at_index(idx).id if idx is not None else None)


class SaveDialog(NzModal):
    def __init__(self, title: str, excerpt: str, existed: bool) -> None:
        super().__init__()
        self._title = title
        self._excerpt = excerpt
        self._existed = existed

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="save-dialog"):
            yield Label("Save to Brain", classes="dlg-title")
            if self._existed:
                yield Label(f"“{self._title}” is already in the Brain (Resources). Nothing new is written.",
                            classes="hint")
            else:
                yield Label(f"New Markdown note “{self._title}” in Resources, tag wikipedia, with the link, "
                            "the licence line and this excerpt. Undo (u) removes it again.", classes="hint")
            yield Static(f"> {self._excerpt}" if self._excerpt else "(no excerpt)", id="save-excerpt")
            with Horizontal(classes="buttons"):
                yield Button("Save note", id="save-ok", variant="primary", disabled=self._existed)
                yield Button("Cancel", id="save-cancel")

    def on_mount(self) -> None:
        super().on_mount()
        target = "#save-cancel" if self._existed else "#save-ok"
        self.query_one(target, Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "save-ok")


class ThemeModal(NzModal):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall", id="theme-dialog"):
            yield Label("Themes", classes="dlg-title")
            yield Label("Enter applies the highlighted theme and saves it. Esc cancels.", classes="hint")
            yield OptionList(*[Option(f"{p.name}  {p.id}", id=p.id) for p in PALETTES], id="theme-options")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


HELP_LINES = [
    f"NuzeHub TUI {__version__}. Esc or Close returns.",
    "F10 or alt+letter opens the menu (Ghostty: macos-option-as-alt = true). Arrows move, Enter runs, Esc closes.",
    "0 Desk  1 News  2 Markets  3 GEO  4 Brain  5 Wikipedia  6 Status (the TUI always opens on the Desk)",
    "Desk: Alt+1..Alt+8 map layers, Left/Right step countries on the map, Enter opens the Inspector, m shows the map"
    " on a small window, c filters Intel to the row's country, Esc clears it; Enter on Intel or Watchlist opens News/Markets.",
    "Live Mode has three parts you can switch on one by one (on the Desk or in the View menu): G Live: Globe Spin,"
    " K Live: Stock Ticker (scrolls the MKT tape), U Live: Auto-Updates (the Desk polls its sources).",
    "L, the LIVE chip or View > Live Mode (All) is the master switch: with anything on it turns all off and remembers"
    " the mix; with all off it brings that mix back (or all three). Chip: ◇ off, ◈ some on, ◆ all on.",
    "S (Desk) or View > Live Speed cycles Eco (globe +3° at 3 fps, ticker 1 cell / 0.28 s), Smooth (default; +1.5° at"
    " 8 fps, 1 cell / 0.14 s) and Ultra (+1° at 12 fps, 1 cell / 0.08 s). I (Desk) or View > Auto-Update cycles how"
    " often Auto-Updates polls: 15s, 30s (default), 60s, 120s (settings.json: live_update_interval, 5..600).",
    "All off (the default) is calm: nothing moves or polls on its own, r still refreshes. Live parts pause behind"
    " a dialog or menu, off the Desk and when the terminal loses focus.",
    "When they are not live the map and MKT tape move only when you move them: on the map Shift+Left/Right or the wheel rotate, Shift+Up/Down tilt,"
    " Home resets; on the tape Left/Right or the wheel step one item, Home goes back to the biggest movers.",
    "r refresh   b list pane   A activity panel   t next theme   T themes (default HUDdy)   ? help   q quit",
    "Wikipedia: / search, Enter opens a result, links follow inside the library, Esc or Back goes back.",
    "c cites the open article in a note (or a new note), s saves it to the Brain, u undoes that.",
    "Related in Wikipedia works from a News story (1) or a Brain note (4).",
    "Inside a dialog letters and digits are typed text; q does not quit there.",
    "Results only come from the library the status line names. When it is unavailable nothing is shown.",
    "The model chip is Ollama first. LM Studio is only a fallback; there is no warning while Ollama answers.",
    "The host key is never shown, logged or saved.",
]


class HelpModal(NzModal):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall", id="help-dialog"):
            yield Label("Help", classes="dlg-title")
            with VerticalScroll():
                yield Static("\n".join(HELP_LINES), id="help-body")
            with Horizontal(classes="buttons"):
                yield Button("Close", id="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)


class AboutModal(NzModal):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="about-dialog"):
            yield Label("About", classes="dlg-title")
            yield Static(
                "\n".join([
                    f"NuzeHub TUI {__version__}",
                    "A keyboard-first terminal client of the NuzeHub desk running on your server.",
                    "The OPS Desk, News, Markets, GEO list, Brain notes, the Wikipedia Library and status.",
                    "Look: SSHush 0.7.0 / 1.0.0 chrome (Dirlume 1.7.x buttons, MIT). Default theme: HUDdy.",
                ]),
                id="about-body",
            )
            with Horizontal(classes="buttons"):
                yield Button("Close", id="about-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)
