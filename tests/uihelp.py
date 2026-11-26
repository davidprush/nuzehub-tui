from __future__ import annotations

from pathlib import Path

from conftest import settle
from nuzehub_tui.demo import DemoBackend
from nuzehub_tui.settings import TABS, Settings
from nuzehub_tui.ui.app import NuzeHubApp

STABLE_STATE = Path("/tmp/nuzehub-tui-snapshots/state")  # the Status tab shows this path, so it is fixed
DIALOG_ACTIONS = ("help", "about", "theme_modal", "wiki_cite", "wiki_save")
SNAP_THEME: str | None = None  # 0.2.0: test_snapshots_github.py sets "github-dark" to rerun every snapshot in it


def demo_app(state: Path = STABLE_STATE, theme: str | None = None, now=None, **kw) -> NuzeHubApp:
    state.mkdir(parents=True, exist_ok=True)
    (state / "settings.json").unlink(missing_ok=True)
    theme = theme or SNAP_THEME
    if theme:  # an install past the one-time switch, showing this theme
        Settings(state).save({"theme": theme, "theme_migrated_020": True})
    return NuzeHubApp(DemoBackend(**kw), settings=Settings(state), demo=True, clock=lambda: "09:30:00", now=now)


async def open_article(app, pilot, title: str = "Saturn") -> None:
    app.action_show_tab("tab-wiki")
    await settle(pilot)
    await app.wiki_search("saturn")
    await settle(pilot)
    await app.wiki_open(title)
    await settle(pilot)


def screen_lines(app) -> list[str]:
    return ["".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips()]


__all__ = ["TABS", "DIALOG_ACTIONS", "demo_app", "open_article", "screen_lines", "settle"]
