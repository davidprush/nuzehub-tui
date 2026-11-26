"""0.2.0 §0.6/§7.2: every snapshot of test_snapshots.py again in GitHub Dark, the required second theme."""

from __future__ import annotations

import pytest

import uihelp
from test_snapshots import (  # noqa: F401 - collected again here, in GitHub Dark
    test_snapshot_cite_save,
    test_snapshot_gate,
    test_snapshot_main_small,
    test_snapshot_menus,
    test_snapshot_tabs,
    test_snapshot_theme_dropdown,
)


@pytest.fixture(autouse=True)
def github_dark(monkeypatch):
    monkeypatch.setattr(uihelp, "SNAP_THEME", "github-dark")
