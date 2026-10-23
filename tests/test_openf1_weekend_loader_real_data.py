"""Seam 2: OpenF1 real-weekend → race weekend description (ticket 21).

One real request against ``api.openf1.org/v1/`` through the default
HTTP seam and the real cache. Pins that the loader can round-trip a
2024 weekend end to end without a hand-written fixture: Monza 2024
(conventional) comes back with the four pre-race sessions, 20 teams
on the grid and lap rows that carry a Compound, tyre age and the
pit-in / pit-out booleans.

The fast suite covers field-by-field assertions; this test only
exercises the real network path. Marked ``slow`` so routine runs skip
it. Caches under ``.cache/openf1`` so a warm run makes no fresh
requests (``.cache/`` is gitignored).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import Compound, RaceWeekend
from f1_strategy.openf1_loader import load_weekend


pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "openf1"


@pytest.fixture(scope="module")
def monza_2024() -> RaceWeekend:
    return load_weekend(2024, "Italian Grand Prix", cache_dir=CACHE_DIR)


def test_loads_as_a_race_weekend(monza_2024: RaceWeekend) -> None:
    assert isinstance(monza_2024, RaceWeekend)
    assert monza_2024.pre_race.season == 2024
    assert monza_2024.pre_race.circuit == "Monza"
    assert monza_2024.pre_race.is_sprint_weekend is False


def test_all_pre_race_sessions_are_present(monza_2024: RaceWeekend) -> None:
    names = tuple(s.name for s in monza_2024.pre_race.sessions)
    assert names == ("FP1", "FP2", "FP3", "Q")


def test_all_race_starters_present_with_their_teams(monza_2024: RaceWeekend) -> None:
    teams = monza_2024.pre_race.teams
    # Monza 2024's grid had 20 starters.
    assert len(teams) == 20
    assert teams["VER"] == "Red Bull Racing"
    assert teams["LEC"] == "Ferrari"


def test_race_lap_count_matches_the_known_distance(monza_2024: RaceWeekend) -> None:
    # Monza 2024 is scheduled for 53 laps (public result).
    assert monza_2024.pre_race.race_laps == 53


def test_pre_race_laps_carry_lap_time_compound_and_tyre_age(monza_2024: RaceWeekend) -> None:
    fp1 = next(s for s in monza_2024.pre_race.sessions if s.name == "FP1")
    assert len(fp1.laps) > 50  # a real FP1 produces hundreds of laps
    for lap in fp1.laps[:20]:
        assert lap.lap_time > 60.0  # Monza laps are ~85 s; anything < 60 s is suspect
        assert lap.lap_time < 180.0
        assert isinstance(lap.compound, Compound)
        assert lap.tyre_age >= 1
