"""Keep tests off the real home folder, off David's libraries and off the network (loopback stand-ins only)."""

from __future__ import annotations

import os
import socket
import time

import pytest

os.environ["TZ"] = "UTC"
time.tzset()

_real_getaddrinfo = socket.getaddrinfo
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("NUZEHUB_TUI_STATE_DIR", str(tmp_path / "tui-state"))
    for name in list(os.environ):
        if name.startswith("SB_") or name in ("NUZEHUB_TUI_URL", "NUZEHUB_BRAIN_BIN", "NO_COLOR"):
            monkeypatch.delenv(name, raising=False)
    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")

    def guarded(host, *args, **kwargs):
        if str(host) not in LOOPBACK:
            raise AssertionError(f"unexpected network lookup {host!r}")
        return _real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
    return tmp_path


async def settle(pilot, n: int = 3) -> None:
    for _ in range(n):
        await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    for _ in range(n):
        await pilot.pause()
