"""0.1.1 change 3: on a client Mac (``~/.local/bin/nuzehub-remote`` exists) a silent 127.0.0.1 says to use
``nuzehub-remote``; without the launcher (on the server Mac) the 0.1.0 text is unchanged. HOME is the test's temp home
(conftest). NUZEHUB_TUI_HINT_LOG keeps the evidence."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from conftest import settle
from nuzehub_tui import cli
from nuzehub_tui.client import NuzeHubClient, Unreachable
from nuzehub_tui.settings import Settings
from nuzehub_tui.ui.app import NuzeHubApp

HINT = "Open NuzeHub with nuzehub-remote (quit with q): it runs on the NuzeHub server, not on this Mac"


def _closed_port() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def _launcher(present: bool) -> None:
    path = Path(os.environ["HOME"]) / ".local" / "bin" / "nuzehub-remote"
    if present:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/zsh\n", "utf-8")
        path.chmod(0o755)


def _keep(text: str) -> None:
    log = os.environ.get("NUZEHUB_TUI_HINT_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(text.rstrip("\n") + "\n")


def _old_text(url: str) -> str:
    return (f"NuzeHub is not answering at {url}. On the server check it is running "
            "(launchctl print gui/$(id -u)/net.secondbrain.nuzehub), then press r.")


@pytest.mark.parametrize("present", [True, False])
def test_unreachable_text_and_check(capsys, present):
    _launcher(present)
    url = _closed_port()
    with pytest.raises(Unreachable) as err:
        NuzeHubClient(url, timeout=3).access_status()
    assert cli.main(["--check", "--url", url]) == 1
    out = capsys.readouterr().out
    _keep(f"launcher {'present' if present else 'absent'} | Unreachable: {err.value}\n  --check: {out.strip()}")
    if present:
        assert HINT in str(err.value) and HINT in out and out.startswith("FAIL connect:")
    else:
        assert str(err.value) == _old_text(url)  # byte-identical to 0.1.0
        assert out == f"FAIL connect: {_old_text(url)}\n"


def test_non_loopback_url_keeps_old_text():
    _launcher(True)
    client = NuzeHubClient("http://nuzehub.example:8080")
    hint = getattr(client, "_client_hint", lambda: "")()
    _keep(f"non-loopback http://nuzehub.example:8080 with launcher | hint: {hint!r}")
    assert hint == ""


@pytest.mark.parametrize("size", [(120, 40), (80, 24)])
async def test_hint_in_the_log_line(tmp_path, size):
    _launcher(True)
    app = NuzeHubApp(NuzeHubClient(_closed_port(), timeout=3), settings=Settings(tmp_path / "s"), clock=lambda: "09:30:00")
    async with app.run_test(size=size) as pilot:
        await settle(pilot, 4)
        if not app.query_one("#activity").display:
            await pilot.press("A")
            await settle(pilot)
        lines = [line for line in app._activity if "ERROR" in line]
        screen = "\n".join("".join(s.text for s in strip) for strip in app.screen._compositor.render_strips())
        shown = [row.strip() for row in screen.splitlines() if "ERROR" in row]
        _keep(f"app {size[0]}x{size[1]} log: {lines}\n  on screen: {shown}")
        assert lines and HINT in lines[-1]
        assert "nuzehub-remote" in screen  # shown whole, never cut mid-command
