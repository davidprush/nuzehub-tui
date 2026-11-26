"""TUI settings (theme, list pane, last tab). Never under a Desktop folder; file names never start with a date.

0.2.0: the Desk tab (key 0) is the start tab; ``active_tab`` is still saved but no longer restored at launch. A settings
file from before 0.2.0 is switched to God's Eye HUD once (``migrate_theme``, flag ``theme_migrated_020``); a theme chosen
after that is never overridden. The 0.2.0 pre-release ``static_tape`` key is retired (the tape only moves when stepped); an older file that still
has it loads fine because unknown keys are ignored.

0.2.1: ``live_mode`` (default false) is the one Live Mode switch: globe spin, ticker scroll and background updates.
A value that is not a boolean loads as false.

0.2.2: God's Eye HUD is called HUDdy (id ``huddy``); a saved legacy ``gods-eye-hud`` loads as ``huddy``. Live Mode is
three independent switches, ``live_globe``, ``live_ticker`` and ``live_updates`` (each default false; a value that is
not a boolean loads as false). A file that has the 0.2.1 ``live_mode: true`` and none of the three keys loads with all
three on; ``live_mode`` itself is no longer written. ``live_last`` is the last active combination, which L restores.
0.2.2 addendum: ``live_speed`` ("eco", "smooth" or "ultra"; default "smooth"; anything else loads as "smooth") sets the
globe and ticker cadence, and ``live_update_interval`` (whole seconds, default 30, clamped to 5..600; anything that is
not a whole number loads as 30) is how often Live: Auto-Updates polls the Desk sources.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from nuzehub_tui.themes import DEFAULT, NAMES, canonical

LIVE_KEYS = ("live_globe", "live_ticker", "live_updates")  # 0.2.2 per-element Live Mode
LIVE_SPEEDS = ("eco", "smooth", "ultra")  # 0.2.2 addendum
UPDATE_MIN, UPDATE_MAX, UPDATE_DEFAULT = 5, 600, 30
DEFAULTS: dict[str, Any] = {"theme": DEFAULT, "sidebar_hidden": None, "active_tab": "tab-desk",
                            "theme_migrated_020": False, "live_globe": False, "live_ticker": False,
                            "live_updates": False, "live_last": None, "live_speed": "smooth",
                            "live_update_interval": UPDATE_DEFAULT}
TABS = ("tab-desk", "tab-news", "tab-markets", "tab-geo", "tab-brain", "tab-wiki", "tab-status")
MIGRATED_NOTE = "Theme: switched to HUDdy once; press T or use the Themes menu to change."


def state_dir() -> Path:
    raw = os.environ.get("NUZEHUB_TUI_STATE_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "nuzehub-tui"
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "nuzehub-tui"
    if "Desktop" in path.parts:
        raise ValueError(f"Refusing to keep NuzeHub TUI settings under a Desktop folder ({path}).")
    return path


class Settings:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or state_dir()
        if "Desktop" in self.root.parts:
            raise ValueError("Refusing to keep NuzeHub TUI settings under a Desktop folder.")
        self.path = self.root / "settings.json"

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        data = dict(DEFAULTS)
        saved: Any = None
        try:
            saved = json.loads(self.path.read_text("utf-8"))
            if isinstance(saved, dict):
                data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        if isinstance(data["theme"], str):
            data["theme"] = canonical(data["theme"])  # 0.2.2: legacy gods-eye-hud -> huddy
        if data["theme"] not in NAMES:
            data["theme"] = DEFAULT
        if data["active_tab"] not in TABS:
            data["active_tab"] = "tab-desk"
        if isinstance(saved, dict) and saved.get("live_mode") is True and not any(k in saved for k in LIVE_KEYS):
            data.update(dict.fromkeys(LIVE_KEYS, True))  # 0.2.1 file with Live Mode on: all three on
        for key in LIVE_KEYS:
            if not isinstance(data[key], bool):
                data[key] = False
        last = data["live_last"]
        if not (isinstance(last, list) and last and all(k in LIVE_KEYS for k in last)):
            data["live_last"] = None
        if data["live_speed"] not in LIVE_SPEEDS:
            data["live_speed"] = "smooth"
        every = data["live_update_interval"]
        if isinstance(every, float) and every.is_integer():
            every = int(every)
        if isinstance(every, bool) or not isinstance(every, int):
            every = UPDATE_DEFAULT
        data["live_update_interval"] = max(UPDATE_MIN, min(UPDATE_MAX, every))
        return data

    def save(self, patch: dict[str, Any]) -> None:
        data = self.load()
        data.update({k: v for k, v in patch.items() if k in DEFAULTS})
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name("settings.json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        tmp.replace(self.path)

    def migrate_theme(self) -> bool:
        """0.2.0 one-time switch (brief §0.1): when ``theme_migrated_020`` is absent or false, set the theme to HUDdy
        (God's Eye HUD before 0.2.2) and the flag to true in one save. Returns True when it switched (the caller logs ``MIGRATED_NOTE``)."""
        if self.load().get("theme_migrated_020") is True:
            return False
        self.save({"theme": DEFAULT, "theme_migrated_020": True})
        return True
