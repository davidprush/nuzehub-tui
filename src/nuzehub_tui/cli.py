"""``nuzehub-tui``: open the TUI, or check the connection without one (``--check``)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nuzehub_tui import __version__, desk
from nuzehub_tui.client import DEFAULT_URL, NuzeHubClient, NuzeHubError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nuzehub-tui", description="Keyboard-first terminal client of NuzeHub.")
    p.add_argument("--version", action="version", version=f"nuzehub-tui {__version__}")
    p.add_argument("--url", default=os.environ.get("NUZEHUB_TUI_URL", DEFAULT_URL),
                   help=f"NuzeHub address (default {DEFAULT_URL}; NUZEHUB_TUI_URL). Never a ?key= link.")
    p.add_argument("--demo", action="store_true", help="fictional demo desk, no network")
    p.add_argument("--state", type=Path, default=None, help="settings folder (default: per-user app folder)")
    p.add_argument("--check", action="store_true",
                   help="print connection, access, library and model status, then exit (no TUI, no secrets)")
    return p


def check(url: str) -> int:
    try:
        client = NuzeHubClient(url, timeout=15)
        access = client.access_status()
    except NuzeHubError as exc:
        print(f"FAIL connect: {exc}")
        return 1
    kind = "host" if access.get("open") and not access.get("remote") else (
        "trusted" if access.get("trusted") else ("open" if access.get("open") else "needs key"))
    print(f"OK   connect: {client.base_url} ({kind})")
    if not access.get("open"):
        print("INFO the TUI will ask for the host key; nothing else was checked")
        return 0
    code = 0
    try:
        st = client.wiki_status()
        print(f"{'OK  ' if desk.library_on(st) else 'INFO'} library: {desk.status_summary(st)}")
    except NuzeHubError as exc:
        print(f"FAIL library: {exc}")
        code = 1
    try:
        chip, level = desk.model_chip(client.probe_engines(), client.model_status())
        print(f"{'OK  ' if level == 'ok' else 'INFO'} model: {chip}")
    except NuzeHubError as exc:
        print(f"FAIL model: {exc}")
        code = 1
    ms = client.model_status()
    print(f"INFO /api/model-status: {'served' if ms is not None else ('not served' if client.loopback else 'skipped (not loopback)')}")
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.check:
        return check(args.url)
    from nuzehub_tui.demo import DemoBackend
    from nuzehub_tui.ui.app import run_tui

    if args.demo:
        run_tui(DemoBackend(), demo=True, state=args.state)
        return 0
    try:
        backend = NuzeHubClient(args.url)
    except NuzeHubError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    run_tui(backend, demo=False, state=args.state)
    return 0
