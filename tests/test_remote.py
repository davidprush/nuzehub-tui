"""0.1.1 change 1: truecolor detection and force, ported from Dirlume 1.7.3 tests/test_v173.py."""

from __future__ import annotations

import pytest

from nuzehub_tui import remote


@pytest.mark.parametrize("env,kitty,truecolor", [
    ({}, False, False),
    ({"TERM": "xterm-256color"}, False, False),
    ({"TERM": "xterm-ghostty"}, True, True),
    ({"TERM": "xterm-kitty"}, True, True),
    ({"TERM": "xterm-256color", "TERM_PROGRAM": "ghostty"}, True, True),
    ({"TERM": "xterm-256color", "TERM_PROGRAM": "Ghostty"}, True, True),
    ({"TERM": "xterm-256color", "KITTY_WINDOW_ID": "1"}, True, True),
    ({"TERM": "xterm-256color", "KITTY_WINDOW_ID": " "}, False, False),
    ({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, False, True),
    ({"TERM": "xterm-256color", "COLORTERM": "24bit"}, False, True),
    ({"TERM": "xterm-256color", "COLORTERM": "yes"}, False, False),
    ({"TERM": "xterm-direct"}, False, True),
    ({"TERM": "foot-direct"}, False, True),
    ({"TERM": "xterm-truecolor"}, False, True),
    ({"TERM": "xterm-256color", "TERM_PROGRAM": "iTerm.app"}, False, False),
    ({"TERM": "xterm-256color", "TERM_PROGRAM": "Apple_Terminal"}, False, False),
])
def test_env_signals(env, kitty, truecolor):
    assert remote.kitty_env(env) is kitty
    assert remote.truecolor(env) is truecolor


def test_force_truecolor():
    env: dict = {"TERM": "xterm-256color"}
    assert remote.force_truecolor(env) is False and "COLORTERM" not in env
    env = {"TERM": "xterm-ghostty"}
    assert remote.force_truecolor(env) is True and env["COLORTERM"] == "truecolor"
    env = {"TERM": "xterm-direct"}
    assert remote.force_truecolor(env) is True and env["COLORTERM"] == "truecolor"
    env = {"COLORTERM": "24bit"}
    assert remote.force_truecolor(env) is True and env["COLORTERM"] == "24bit"  # kept as is
    env = {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty", "NO_COLOR": "1"}
    assert remote.force_truecolor(env) is False and "COLORTERM" not in env  # NO_COLOR is never overridden
    for quiet in ({}, {"TERM": "xterm-256color", "TERM_PROGRAM": "Apple_Terminal"},
                  {"TERM": "xterm-256color", "TERM_PROGRAM": "iTerm.app"}, {"TERM": "xterm-256color", "COLORTERM": "yes"}):
        before = dict(quiet)
        assert remote.force_truecolor(quiet) is False and quiet == before  # no signal: a no-op


@pytest.mark.parametrize("term,program", [("xterm-256color", "ghostty"), ("xterm-ghostty", None)])
def test_forced_truecolor_reaches_rich(monkeypatch, term, program):
    from rich.console import ColorSystem, Console
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", term)
    if program:
        monkeypatch.setenv("TERM_PROGRAM", program)
    else:
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
    before = Console(force_terminal=True)._detect_color_system()
    assert before != ColorSystem.TRUECOLOR
    if term == "xterm-ghostty":
        assert before == ColorSystem.STANDARD  # Rich alone treats xterm-ghostty as 16 colours
    assert remote.force_truecolor()
    assert Console(force_terminal=True)._detect_color_system() == ColorSystem.TRUECOLOR
