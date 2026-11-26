"""0.1.1: full colour over ssh. ``kitty_env``, ``truecolor`` and ``force_truecolor`` from Dirlume 1.7.3 ``remote.py``
(MIT, Copyright (c) 2026 Dirlume contributors). ssh does not forward ``COLORTERM``, so without this the TUI on the server
falls back to 256 colours and GitHub Dark's ``#0d1117`` turns ``#000000``. Reads only the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping

TRUECOLOR = ("truecolor", "24bit")
KITTY_TERMS = ("xterm-ghostty", "xterm-kitty")


def kitty_env(env: Mapping[str, str] | None = None) -> bool:
    """The environment names a Kitty-graphics (and 24-bit colour) terminal: TERM xterm-ghostty / xterm-kitty,
    TERM_PROGRAM ghostty, or KITTY_WINDOW_ID set. Nothing is asked of the terminal."""
    e = os.environ if env is None else env
    return ((e.get("TERM") or "").strip().lower() in KITTY_TERMS
            or (e.get("TERM_PROGRAM") or "").strip().lower() == "ghostty"
            or bool((e.get("KITTY_WINDOW_ID") or "").strip()))


def truecolor(env: Mapping[str, str] | None = None) -> bool:
    """24-bit colour from the environment: COLORTERM truecolor / 24bit, a TERM naming ``direct`` or ``truecolor``, or a
    Kitty-graphics terminal (``kitty_env``)."""
    e = os.environ if env is None else env
    term = (e.get("TERM") or "").strip().lower()
    return ((e.get("COLORTERM") or "").strip().lower() in TRUECOLOR or "direct" in term or "truecolor" in term
            or kitty_env(e))


def force_truecolor(env: dict | None = None) -> bool:
    """When the environment says 24-bit colour (``truecolor``) but ``COLORTERM`` does not, set ``COLORTERM=truecolor``
    in this process before the App (and its console) is created, so Textual renders true colour. Returns whether
    truecolor is in force; nothing changes otherwise. NuzeHub TUI addition: never when ``NO_COLOR`` is set."""
    e = os.environ if env is None else env
    if (e.get("NO_COLOR") or "") != "" or not truecolor(e):
        return False
    if (e.get("COLORTERM") or "").strip().lower() not in TRUECOLOR:
        e["COLORTERM"] = "truecolor"
    return True
