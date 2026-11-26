"""Command line, --check without secrets, and the path rules (no Desktop, no leading dates)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nuzehub_tui import __version__, cli
from nuzehub_tui.settings import Settings, state_dir
from standin import StandIn

SRC = Path(__file__).resolve().parents[1] / "src" / "nuzehub_tui"


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"nuzehub-tui {__version__}" == "nuzehub-tui 0.2.3"


def test_check_reports_without_the_key(capsys):
    with StandIn(key="test-key-placeholder") as s:
        assert cli.main(["--check", "--url", s.url]) == 0
    out = capsys.readouterr().out
    assert "OK   connect" in out and "library: Library on" in out and "model: Ollama" in out
    assert "/api/model-status: served" in out and "test-key-placeholder" not in out


def test_check_remote_needs_key(capsys):
    with StandIn(peer="remote", key="test-key-placeholder") as s:
        assert cli.main(["--check", "--url", s.url]) == 0
    assert "ask for the host key" in capsys.readouterr().out


def test_key_link_refused(capsys):
    assert cli.main(["--url", "http://127.0.0.1:8080/?key=SECRET999"]) == 2
    err = capsys.readouterr().err
    assert "SECRET999" not in err and "key" in err


def test_settings_never_on_desktop(tmp_path):
    with pytest.raises(ValueError):
        Settings(tmp_path / "Desktop" / "x")
    assert "Desktop" not in state_dir().parts


def test_no_dated_names_and_no_desktop_writes():
    for path in SRC.rglob("*"):
        assert not re.match(r"\d{4}-?\d{2}", path.name), path
    for path in SRC.rglob("*.py"):
        text = path.read_text("utf-8")
        assert "~/Desktop" not in text and "Path.home() / \"Desktop\"" not in text, path


def test_settings_round_trip(tmp_path):
    st = Settings(tmp_path / "s")
    st.save({"theme": "dracula", "active_tab": "tab-wiki", "bogus": 1})
    data = st.load()
    assert data["theme"] == "dracula" and data["active_tab"] == "tab-wiki" and "bogus" not in data
    st.path.write_text("{broken", "utf-8")
    assert st.load()["theme"] == "huddy"  # 0.2.0: the default is HUDdy
