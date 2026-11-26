"""0.2.0 §7.5: the Desk once against a real booted NuzeHub tree (a scratch dev server, never the live server). Skipped unless
NUZEHUB_TUI_LIVE_URL is set. Synthetic data only: the test writes a synthetic desk (tasks, events, a notice, a
price rule, no feeds) into the scratch server, and that server runs with NUZEHUB_MARKET_FAIL / NUZEHUB_HAZARD_FAIL
naming every source, so no third-party quote or hazard is fetched; those panels must show "offline", never blank.
"""

from __future__ import annotations

import json
import os
import socket

import pytest

from conftest import _real_getaddrinfo, settle
from nuzehub_tui.client import NuzeHubClient
from nuzehub_tui.settings import TABS, Settings
from nuzehub_tui.ui.app import NuzeHubApp
from nuzehub_tui.ui.deskview import DeskView
from uihelp import screen_lines

URL = os.environ.get("NUZEHUB_TUI_LIVE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="set NUZEHUB_TUI_LIVE_URL to a scratch NuzeHub dev server")


@pytest.fixture(autouse=True)
def allow_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _real_getaddrinfo)
    assert NuzeHubClient(URL).loopback, "live tests only run against a loopback scratch server"


def _synthetic(desk: dict, now_ms: int) -> dict:
    d = dict(desk)
    d["tasks"] = [{"id": "t1", "title": "Synthetic task A", "recurrence": "once"},
                  {"id": "t2", "title": "Synthetic task B", "recurrence": "once", "doneOn": "2026-11-01"}]
    d["events"] = [{"id": "e1", "title": "Synthetic standup", "start": "2099-01-01T15:00:00Z"}]
    d["automationNotices"] = [{"id": "n1", "at": now_ms, "title": "Synthetic rule", "body": "Synthetic notice"}]
    d.pop("automationNoticesClearedAt", None)
    d.pop("focus", None)
    d["watchlist"] = ["SYNA", "SYNB"]  # synthetic tickers; every quote source is forced to fail anyway
    return d


async def test_live_desk(tmp_path):
    import time
    c = NuzeHubClient(URL, timeout=60)
    inst = c.load_instance()
    now = int(time.time() * 1000)
    desk = _synthetic(inst.get("desk") or {}, now)
    prefs = dict(desk.get("prefs") or {})
    prefs["sources"] = []  # no feeds: nothing is fetched from the internet
    desk["prefs"] = prefs
    res = c.save_instance(desk=desk, brain=None, base_rev=int(inst.get("rev") or 0))
    assert res.get("ok"), res
    before = c.load_instance()
    brain_before = json.dumps(before.get("brain"), sort_keys=True)

    st = Settings(tmp_path / "s")
    app = NuzeHubApp(NuzeHubClient(URL, timeout=60), settings=st, clock=lambda: "09:30:00")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, 10)
        assert app._active() == "tab-desk" and app.theme == "huddy"
        dv = app.query_one(DeskView)
        text = "\n".join(screen_lines(app))
        assert "Synthetic notice" in text  # ALERTS from the instance's automation notices
        assert "TASKS 1/2" in text.replace("  ", " ") or "1/2" in text
        assert "Synthetic standup" in text or "Jan 1" in text
        assert "offline" in str(app.query_one("#desk-watch").border_subtitle)  # markets forced to fail: marked
        assert dv.intel_rows == []  # no feeds, no stories
        assert app.desk_failed("hazards") and "offline" in text  # hazard sources forced to fail: marked
        # Focus 25m: the Desk's only write, merged into the latest desk
        app.query_one("#chip-25").focus()
        await pilot.press("enter")
        await settle(pilot, 10)
        after = c.load_instance()
        assert after["desk"]["focus"]["label"] == "Focus" and after["desk"]["focus"]["endsAt"] > now
        rest_a = {k: v for k, v in after["desk"].items() if k != "focus"}
        rest_b = {k: v for k, v in before["desk"].items() if k != "focus"}
        assert json.dumps(rest_a, sort_keys=True) == json.dumps(rest_b, sort_keys=True)
        assert json.dumps(after.get("brain"), sort_keys=True) == brain_before
        # every tab still answers, then r on the Desk
        for tab in TABS:
            app.action_show_tab(tab)
            await settle(pilot, 3)
        await pilot.press("0")
        await pilot.press("r")
        await settle(pilot, 10)
        assert app._active() == "tab-desk" and app.desk_timer_states()["clock"]
