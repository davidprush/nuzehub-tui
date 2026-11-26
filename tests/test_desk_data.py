"""0.2.0 §7.1 unit tests of the Desk's pure functions (deskdata.py), the price-move alerts (§9 Q6), the 256/16 maps
(§0.4) and the graphics ladder (mapgfx.detect). Synthetic data only; TZ is UTC (conftest)."""

from __future__ import annotations

import pytest
from rich._palettes import EIGHT_BIT_PALETTE, STANDARD_PALETTE

from nuzehub_tui import deskdata as D
from nuzehub_tui import mapgfx, themes

NOW = 1795264200000  # 2026-11-21 12:30 UTC
MIN = 60_000


def test_age_label():
    assert D.age_label(NOW - 20_000, NOW) == "now"
    assert D.age_label(NOW - 12 * MIN, NOW) == "12m"
    assert D.age_label(NOW - 5 * 60 * MIN, NOW) == "5h"
    assert D.age_label(NOW - 47 * 60 * MIN, NOW) == "47h"
    assert D.age_label(NOW - 3 * 1440 * MIN, NOW) == "3d"
    assert D.age_label("2026-11-21T12:00:00Z", NOW) == "30m"
    assert D.age_label(None, NOW) == D.age_label("not a date", NOW) == ""
    assert D.age_label(NOW + 5 * MIN, NOW) == "now"  # future clamps to 0


def test_price_text_digits_rule_and_pct():
    assert D.price_text(97250) == "97,250" and D.price_text(1234.4) == "1,234"
    assert D.price_text(182.4) == "182.40" and D.price_text(10) == "10.00"
    assert D.price_text(3.14159) == "3.142" and D.price_text(None) == D.price_text("x") == "—"
    assert D.pct(1.2) == "+1.20%" and D.pct(-0.4) == "-0.40%" and D.pct(0) == "0.00%"


def test_tape_order_biggest_movers_first_errors_skipped():
    first, second = D.TAPE_SYMBOLS[0], D.TAPE_SYMBOLS[1]
    tape = [{"symbol": second, "price": 2, "change": -1, "changePct": -0.5},
            {"symbol": D.TAPE_SYMBOLS[2], "error": "no data"},
            {"symbol": first, "price": 5000, "change": 1, "changePct": 0.35}]
    watch = [{"symbol": "NVDA", "price": 182.4, "change": 2, "changePct": 1.2}, {"symbol": first, "price": 1},
             {"symbol": "BAD", "error": "x"}]
    items = D.tape_items(tape, watch)
    labels = dict(D.MARKET_TAPE)
    assert [i["label"] for i in items] == ["NVDA", labels[second], labels[first]]  # |1.2| > |-0.5| > |0.35|
    assert items[1] == {"label": labels[second], "price": "2.000", "pct": "0.50%", "up": False}


def test_tape_ties_break_by_symbol():
    watch = [{"symbol": s, "price": 1, "change": c, "changePct": p} for s, c, p in
             (("ZZZ", 1, 2.0), ("AAA", -1, -2.0), ("MMM", 0, 0.0), ("BBB", 1, 2.0))]
    assert [i["label"] for i in D.tape_items([], watch)] == ["AAA", "BBB", "ZZZ", "MMM"]


def test_watch_rows_and_spark_input():
    q = {"symbol": "NVDA", "price": 182.4, "changePct": 0, "points": [{"close": i} for i in range(40)]}
    rows = D.watch_rows([q, {"symbol": "X", "error": "e"}])
    assert len(rows) == 1 and rows[0]["up"] is True and rows[0]["closes"] == list(range(10, 40))


def test_sparkline():
    from nuzehub_tui.ui.deskview import spark
    up = spark([1, 2, 3, 4, 5, 6, 7, 8], 8, False)
    assert len(up) == 8 and up[0] == "▁" and up[-1] == "█"
    assert set(spark([1, 2, 3], 3, True)) <= set("_.-'^") or spark([1, 2, 3], 3, True).isascii()
    assert spark([], 6, False) == ""  # no closes, no spark


def test_alert_fallback_is_stories_under_two_hours():
    stories = [{"id": "a", "url": "u1", "title": "Fresh", "publishedAt": "2026-11-21T11:00:00Z"},
               {"id": "b", "url": "u2", "title": "Old", "publishedAt": "2026-11-21T09:00:00Z"}]
    m = D.map_data({}, stories, NOW)
    items = D.alert_items({}, stories, m, NOW)
    assert [i["text"] for i in items] == ["Fresh"] and items[0]["tag"] == "Breaking"
    inst = {"desk": {"automationNotices": [{"id": "n1", "at": NOW - MIN, "title": "Rule", "body": "Fired"}]}}
    assert [i["text"] for i in D.alert_items(inst, stories, m, NOW)] == ["Fired"]
    inst["desk"]["automationNoticesClearedAt"] = NOW
    assert [i["text"] for i in D.alert_items(inst, stories, m, NOW)] == ["Fresh"]


# ---- §9 Q6 price-move alerts ----

Q = [{"symbol": "NVDA", "changePct": 2.0}, {"symbol": "AAPL", "changePct": -2.0}, {"symbol": "MSFT", "changePct": 1.99},
     {"symbol": "BAD", "changePct": 9.0, "error": "no data"}]


def test_price_alerts_threshold_edges():
    out = D.price_alerts({}, Q, NOW, stale=False)  # no rule: the web's default "Price moves" at 2 %
    assert out == [{"id": "tui-price-move", "at": NOW, "tag": "Price moves", "text": "NVDA +2.00%, AAPL -2.00%"}]
    rule = {"desk": {"automations": [{"name": "Big moves", "enabled": True,
                                       "actions": [{"kind": "price-move", "thresholdPct": 1.99}]}]}}
    assert D.price_alerts(rule, Q, NOW, False)[0]["text"] == "NVDA +2.00%, AAPL -2.00%, MSFT +1.99%"
    rule["desk"]["automations"][0]["actions"][0]["thresholdPct"] = 2.01
    assert D.price_alerts(rule, Q, NOW, False) == []
    rule["desk"]["automations"][0]["actions"][0]["thresholdPct"] = 0  # invalid: the web's default 2
    assert D.price_rule(rule) == ("Big moves", 2.0)
    rule["desk"]["automations"][0]["enabled"] = False
    assert D.price_rule(rule) == D.PRICE_RULE


def test_price_alerts_empty_stale_and_cleared():
    assert D.price_alerts({}, [], NOW, False) == []
    assert D.price_alerts({}, Q, None, False) == []
    assert D.price_alerts({}, Q, NOW, stale=True) == []
    cleared_after = {"desk": {"automationNoticesClearedAt": NOW + 1}}
    assert D.price_alerts(cleared_after, Q, NOW, False) == []
    cleared_before = {"desk": {"automationNoticesClearedAt": "2026-11-21T12:00:00Z"}}
    assert D.price_alerts(cleared_before, Q, NOW, False) != []


# ---- day dock ----


def test_tasks_next_event_and_focus():
    inst = {"desk": {"tasks": [
        {"id": 1, "title": "Done once", "recurrence": "once", "doneOn": "2026-11-01"},
        {"id": 2, "title": "Daily, done yesterday", "recurrence": "daily", "doneOn": "2026-11-20T10:00:00Z"},
        {"id": 3, "title": "Weekly, done this week", "recurrence": "weekly", "doneOn": "2026-11-17T10:00:00Z"}],
        "events": [{"title": "Ended long ago", "start": "2026-11-20T08:00:00Z", "end": "2026-11-20T09:00:00Z"},
                   {"title": "Standup", "start": "2026-11-21T15:00:00Z"},
                   {"title": "Later", "start": "2026-11-24T15:00:00Z"}],
        "focus": {"endsAt": NOW + 61_000}}}
    assert D.tasks_summary(inst, NOW) == {"done": 2, "total": 3, "first": "Daily, done yesterday"}
    assert D.next_event(inst, NOW) == {"when": "3:00 PM", "title": "Standup"}
    inst["desk"]["events"] = inst["desk"]["events"][2:]
    assert D.next_event(inst, NOW) == {"when": "Nov 24", "title": "Later"}
    left = D.focus_left(inst, NOW)
    assert left == 61_000 and D.focus_text(left) == "1:01"
    assert D.focus_left(inst, NOW + 61_000) is None
    assert D.start_focus(25, NOW) == {"taskId": None, "label": "Focus", "endsAt": NOW + 25 * MIN}
    assert D.bar(0.5, 4) == ("━━", "──") and D.bar(1, 3, True) == ("###", "")


# ---- §0.4 fallback maps ----


@pytest.mark.parametrize("system,table", [("256", EIGHT_BIT_PALETTE), ("standard", STANDARD_PALETTE)])
@pytest.mark.parametrize("theme", ["huddy", "github-dark"])
def test_fallback_maps_keep_background_and_panel_distinct(theme, system, table):
    p = {x.id: x for x in themes.PALETTES}[theme]
    f = themes.fallback_palette(p, system)
    palette = ["#{:02x}{:02x}{:02x}".format(*table[i]) for i in range(16 if system == "standard" else 256)]
    assert f.background in palette and f.panel in palette and f.primary in palette
    assert f.background != f.panel


# ---- graphics ladder ----

UTF = {"LANG": "en_US.UTF-8"}


@pytest.mark.parametrize("env,tty,mode", [
    ({**UTF, "TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty"}, True, "kitty"),
    ({**UTF, "TERM": "xterm-kitty", "SSH_CONNECTION": "1 2 3 4"}, True, "kitty"),
    ({**UTF, "TERM": "xterm-ghostty", "TMUX": "/tmp/t,1,0"}, True, "braille"),
    ({**UTF, "TERM": "xterm-256color", "TERM_PROGRAM": "Apple_Terminal"}, True, "braille"),
    ({**UTF, "TERM": "xterm-ghostty"}, False, "braille"),
    ({**UTF, "TERM": "xterm-ghostty", "NUZEHUB_TUI_GRAPHICS": "braille"}, True, "braille"),
    ({**UTF, "TERM": "xterm-256color", "NUZEHUB_TUI_GRAPHICS": "text"}, True, "text"),
    ({"LANG": "C", "TERM": "xterm-ghostty"}, True, "text"),
])
def test_graphics_ladder(env, tty, mode):
    g = mapgfx.detect(env, tty)
    assert g.mode == mode, g
    if "SSH_CONNECTION" in env and mode != "kitty":
        assert g.reason.startswith("over SSH")
    mapgfx.detect({**UTF, "TERM": "dumb"}, False)  # leave textual-image preset to "no graphics"


def test_map_renderers_fit_their_box():
    m = D.map_data({}, [], NOW)
    p = {x.id: x for x in themes.PALETTES}["huddy"]
    scene = mapgfx.scene_from(m, NOW)
    for kind in ("tactical", "flat"):
        text = mapgfx.render_braille(scene, mapgfx.View(kind), dict(D.LAYER_DEFAULTS), 60, 20, p)
        lines = text.plain.split("\n")
        assert len(lines) == 20 and all(len(line) == 60 for line in lines)
    assert mapgfx.render_image(scene, mapgfx.View("flat"), dict(D.LAYER_DEFAULTS), 300, 150, p).size == (300, 150)
    table = mapgfx.render_table(m, 5, 40, p).plain
    assert table.isascii() or "No" in table
