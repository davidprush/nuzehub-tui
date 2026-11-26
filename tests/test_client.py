"""Client for every MVP handler over real HTTP (stand-in), including access denied, unlock and timeout."""

from __future__ import annotations

import socket

import pytest

from nuzehub_tui.client import (
    FUNCTIONS,
    AccessDenied,
    NuzeHubClient,
    NuzeHubError,
    ServerError,
    TimedOut,
    Unreachable,
    clean_base_url,
    function_id,
)
from standin import StandIn

KEY = "test-key-placeholder"


def test_function_ids_match_nuzehub_dev_ids():
    # Ids NuzeHub's dev server (npm run dev, the LaunchAgent) put in its client modules, captured Nov 21, 2026.
    assert function_id("accessStatus") == "eyJmaWxlIjoiL3NyYy9saWIvaG9zdC9hcGkudHM_dHNzLXNlcnZlcmZuLXNwbGl0IiwiZXhwb3J0IjoiYWNjZXNzU3RhdHVzX2NyZWF0ZVNlcnZlckZuX2hhbmRsZXIifQ"
    assert function_id("wikiPanelSearch") == "eyJmaWxlIjoiL3NyYy9saWIvaG9zdC93aWtpLWFwaS50cz90c3Mtc2VydmVyZm4tc3BsaXQiLCJleHBvcnQiOiJ3aWtpUGFuZWxTZWFyY2hfY3JlYXRlU2VydmVyRm5faGFuZGxlciJ9"


def test_every_mvp_handler_as_host():
    with StandIn() as s:
        c = NuzeHubClient(s.url)
        view = c.access_status()
        assert view["open"] and "key" not in view  # the host's own key is dropped
        inst = c.load_instance()
        assert inst["rev"] == 7 and len(inst["brain"]["notes"]) == 3
        assert c.save_instance(desk=None, brain=inst["brain"], base_rev=7)["ok"]
        assert c.fetch_news(["https://demo.invalid/world.xml"])["stories"]
        assert c.fetch_article("https://demo.invalid/world/1")["text"]
        assert len(c.get_markets(["NVDA", "AAPL"], "5d")["quotes"]) == 2
        assert c.search_symbols("nv")["hits"][0]["symbol"] == "NVDA"
        assert c.get_hazards("24h", ["quake"])["results"][0]["kind"] == "quake"
        assert c.wiki_status()["state"] == "on"
        assert c.wiki_search("saturn")["ok"]
        assert c.wiki_read("Saturn")["article"]["title"] == "Saturn"
        assert c.wiki_related("Saturn rings", "Cassini")["ok"]
        assert c.probe_engines()["ollama"]["ok"]
        assert c.model_status()["ollama"]["count"] == 2
        called = {name for verb, name in s.requests if verb == "POST"}
        assert called == set(FUNCTIONS) - {"unlockHost"}  # unlock: see the remote test


def test_remote_session_access_denied_then_unlock_keeps_cookie_in_memory():
    with StandIn(peer="remote", key=KEY) as s:
        c = NuzeHubClient(s.url)
        assert c.access_status()["open"] is False
        with pytest.raises(AccessDenied) as denied:
            c.load_instance()
        assert "host key" in str(denied.value) and KEY not in str(denied.value)
        bad = c.unlock("wrong")
        assert bad["open"] is False and bad["error"] == "That key does not match."
        good = c.unlock(KEY)
        assert good["open"] is True
        assert c.load_instance()["rev"] == 7
        assert KEY not in repr(c)


def test_trusted_device_is_open_without_key():
    with StandIn(peer="trusted") as s:
        c = NuzeHubClient(s.url)
        assert c.access_status() == {"open": True, "remote": True, "busy": False, "trusted": True}
        assert c.load_instance()["rev"] == 7


def test_timeout_is_a_sentence():
    with StandIn() as s:
        s.delay = 1.0
        c = NuzeHubClient(s.url, timeout=0.2)
        with pytest.raises(TimedOut) as err:
            c.load_instance()
        assert "did not answer within" in str(err.value)


def test_unreachable_server_says_what_to_do():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    c = NuzeHubClient(f"http://127.0.0.1:{port}", timeout=1)
    with pytest.raises(Unreachable) as err:
        c.access_status()
    assert "net.secondbrain.nuzehub" in str(err.value)


def test_ids_are_discovered_when_the_scheme_changes():
    with StandIn(id_scheme="hashed") as s:
        c = NuzeHubClient(s.url)
        assert c.access_status()["open"]
        assert ("GET", "/src/lib/host/api.ts") in s.requests
        assert c.wiki_status()["state"] == "on"


def test_server_error_message_is_passed_on():
    with StandIn() as s:
        c = NuzeHubClient(s.url)
        with pytest.raises(ServerError, match="Missing desk"):
            c.call("saveInstance", {})


def test_key_links_are_refused_without_echo():
    with pytest.raises(NuzeHubError) as err:
        clean_base_url("http://nuzehub.example:8080/?key=SECRET123")
    assert "SECRET123" not in str(err.value)
    assert clean_base_url("127.0.0.1:8080") == "http://127.0.0.1:8080"


def test_model_status_only_on_loopback():
    c = NuzeHubClient("http://nuzehub.example:8080")
    assert c.loopback is False and c.model_status() is None
