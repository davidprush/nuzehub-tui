"""0.2.0 §9 Q1: the Python ports give the same answers as the web's TS functions on the same synthetic input.

The fixture was produced by running src/lib/desk/rank.ts, places.ts and map-data.tsx from the NuzeHub web tree with
``node --experimental-strip-types`` (see fixtures/desk-ts-source/). Synthetic data only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nuzehub_tui import rank

FX = json.loads((Path(__file__).parent / "fixtures" / "desk-ts-fixtures.json").read_text(encoding="utf-8"))


def _slim(rows):
    return [{"id": s["id"], "score": s["score"], "taste": s["taste"], "hits": s["hits"], "sourceName": s["sourceName"]} for s in rows]


@pytest.mark.parametrize("window", ["1", "3", "7", "all"])
def test_rank_stories_matches_ts(window):
    got = rank.rank_stories(FX["stories"], FX["prefs"], window, FX["now"], FX["votes"])
    assert _slim(got) == FX["ranked"][window]


def test_rank_without_topics_or_votes_matches_ts():
    prefs = {**FX["prefs"], "topics": [], "boostKeywords": []}
    assert _slim(rank.rank_stories(FX["stories"], prefs, "7", FX["now"], [])) == FX["noVotes"]


def test_geopolitical_matches_ts():
    ranked = rank.rank_stories(FX["stories"], FX["prefs"], "7", FX["now"], FX["votes"])
    assert [s["id"] for s in rank.geopolitical_stories(ranked)] == FX["geo"]


def test_detect_countries_matches_ts():
    got = [[c.iso2 for c in rank.detect_countries(s["title"], s["summary"])] for s in FX["stories"]]
    assert got == FX["detect"]


def test_norm_matches_ts():
    assert [[raw, rank.norm(raw)] for raw, _ in FX["norms"]] == FX["norms"]


@pytest.mark.parametrize("picture", [False, True])
def test_compute_map_data_matches_ts(picture):
    m = rank.compute_map_data(FX["stories"], FX["links"], FX["placements"], FX["archive"], picture, FX["now"])
    want = FX["mapPicture" if picture else "map"]
    assert m.displayed == want["displayed"]
    assert m.extras == want["extras"]
    assert [[k, v] for k, v in m.counts.items()] == want["counts"]
    assert [[c.id, n] for c, n in m.ranked] == want["ranked"]
    assert m.max_count == want["maxCount"]
    assert [{"key": loc["key"], "countryId": loc["countryId"], "urls": [a["url"] for a in loc["articles"]],
             "freshest": loc["freshest"]} for loc in m.locations] == want["locations"]
    assert [[a["key"], a["count"]] for a in m.arcs] == want["arcs"]
    assert [[k, v] for k, v in m.country_for_url.items()] == want["countryForUrl"]


def test_heat_level_matches_ts():
    assert [rank.heat_level(i) for i in range(11)] == FX["heat"]


def test_gazetteer_lookup_pads_ids():
    assert rank.country_by_id("76").name == "Brazil" and rank.country_by_id("076").iso2 == "BR"
    assert rank.country_by_id(None) is None and rank.country_by_id("999") is None
    assert len(rank.COUNTRIES) == 174
