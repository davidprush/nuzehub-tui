"""Dirlume 1.7.x look for NuzeHub TUI (SSHush 0.7.0 chrome): role-coloured rounded buttons and pane chrome.

Copyright (c) 2026 Dirlume contributors, MIT (layout.button_role / button_tcss). Adapted for SSHush, reused by NuzeHub TUI.

A button is the most compact bordered form: a thin rounded border round one label row, one cell of
padding each side of the label, no bold, no blank rows (Dirlume 1.7.2 compact buttons). Colours are the
theme's ``$btn-*`` variables (see ``nuzehub_tui.themes.button_tokens``).
"""

from __future__ import annotations

import re
from typing import Any

from textual.widgets import Button

from nuzehub_tui.themes import BUTTON_ROLES

BTN_H = 3  # border + one label row + border
BTN_PAD = 1  # one cell each side of the label
BTN_MIN_W = 6
BTN_GAP = 1
ACTIVITY_H = 8  # Dirlume activity panel rows (incl. its top rule)
HUD_H = 2  # Dirlume status bar rows
SHORT_H = 30  # below this many rows the screen is "short": one-row frameless buttons (Dirlume 1.6.9 -compact)
SHORT_CLASS = "-short-screen"

_DANGER_WORDS = ("remove", "delete", "revoke", "undo all", "reject", "erase", "discard")
_DISMISS_WORDS = ("close", "cancel", "back", "no")
_PRIMARY_WORDS = ("approve", "save", "commit", "apply", "ok", "yes", "generate", "start", "run", "use ")
END_IDS = frozenset({"cancel", "close"})


def button_role(label: str, button_id: str | None = None, variant: str = "default") -> str:
    """Dirlume's role rule: danger words, then dismiss (Cancel/Back/Close), then affirmative, else neutral."""
    text = " ".join(str(label).lower().split())
    bid = (button_id or "").lower()

    def has(words: tuple[str, ...]) -> bool:
        return any(re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", text) for w in words)

    def starts(words: tuple[str, ...]) -> bool:
        return any(re.match(rf"{re.escape(w.strip())}(?![a-z])", text) for w in words)

    if has(_DANGER_WORDS) or variant == "error":
        return "danger"
    if bid in END_IDS or bid.endswith("-cancel") or bid.endswith("-back") or starts(_DISMISS_WORDS):
        return "dismiss"
    if starts(_PRIMARY_WORDS) or variant in ("primary", "success", "warning"):
        return "primary"
    return "neutral"


def style_buttons(root: Any) -> None:
    """Give every Button under ``root`` its Dirlume role class and the compact rounded form."""
    for button in root.query(Button):
        if any(button.has_class(f"btn-{role}") for role in BUTTON_ROLES):
            continue
        button.compact = False
        button.add_class(f"btn-{button_role(str(button.label), button.id, str(button.variant))}")


def button_width(label: str) -> int:
    """Cells a button takes in a row: label + padding + border, plus the gap after it."""
    return len(label) + 2 * BTN_PAD + 2 + BTN_GAP


def button_tcss() -> str:
    """Dirlume 1.7.x button rules. Every colour is a ``$btn-*`` theme variable; the face is transparent.
    0.7.0 brief: no bold, also on focus (focus shows as the primary-coloured border)."""
    css = [
        f"Button {{ width: auto; min-width: {BTN_MIN_W}; height: {BTN_H}; line-pad: {BTN_PAD}; padding: 0; "
        "margin: 0 1 0 0; border: round $btn-neutral-border; background: transparent; color: $btn-neutral-text; "
        "text-style: none; }\n"
    ]
    for r in BUTTON_ROLES:
        css.append(
            f"Button.btn-{r} {{ color: $btn-{r}-text; background: transparent; border: round $btn-{r}-border; "
            f"text-style: none; tint: transparent; background-tint: transparent; }}\n"
            f"Button.btn-{r}:hover {{ color: $btn-{r}-text-hover; background: transparent; border: round $btn-{r}-hover; }}\n"
            f"Button.btn-{r}.-active {{ color: $btn-{r}-text-hover; background: $btn-{r}-pressed-bg; "
            f"border: round $btn-{r}-pressed; tint: transparent; }}\n"
            f"Button.btn-{r}:focus {{ color: $btn-{r}-text; background: transparent; border: round $btn-{r}-focus; "
            f"text-style: none; background-tint: transparent; }}\n"
            f"Button.btn-{r}:focus:hover {{ color: $btn-{r}-text-hover; background: transparent; "
            f"border: round $btn-{r}-focus; text-style: none; }}\n"
            f"Button.btn-{r}:focus.-active {{ background: $btn-{r}-pressed-bg; border: round $btn-{r}-focus; }}\n"
            f"Button.btn-{r}:disabled {{ color: $btn-disabled-text; background: transparent; "
            f"border: round $btn-disabled-border; text-style: none; }}\n"
        )
    css.append(".ascii-mode Button { border: ascii $btn-neutral-border; }\n")
    # Dirlume 1.6.9: on a short screen (80x24) buttons are one-row, frameless, role colours kept.
    short = ", ".join(
        f".{SHORT_CLASS} Button.btn-{r}{state}" for r in BUTTON_ROLES for state in ("", ":hover", ":focus", ":disabled", ".-active")
    )
    css.append(f".{SHORT_CLASS} Button, {short} {{ height: 1; border: none; }}\n")
    focus = ", ".join(f".{SHORT_CLASS} Button.btn-{r}:focus" for r in BUTTON_ROLES)
    css.append(f"{focus} {{ text-style: reverse; }}\n")
    return "".join(css)
