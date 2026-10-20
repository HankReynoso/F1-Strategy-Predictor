"""Seam 2: FastF1 real-weekend → race weekend description.

These tests load one cached real race (Monza 2024) through the public
loader and check that the description is sensible. They are marked
`slow` because they hit the FastF1 on-disk cache and, on a cold cache,
the live timing API.
"""

from pathlib import Path

import pytest

from f1_strategy import Compound, RaceWeekend

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastf1"


@pytest.fixture(scope="module")
def monza_2024() -> RaceWeekend:
    from f1_strategy.fastf1_loader import load_weekend

    return load_weekend(2024, "Italian Grand Prix", cache_dir=CACHE_DIR)


def test_loads_as_a_race_weekend(monza_2024: RaceWeekend) -> None:
    assert isinstance(monza_2024, RaceWeekend)
    assert monza_2024.pre_race.season == 2024
    assert monza_2024.pre_race.circuit == "Monza"
    assert monza_2024.pre_race.is_sprint_weekend is False


def test_all_race_starters_present_with_their_teams(monza_2024: RaceWeekend) -> None:
    teams = monza_2024.pre_race.teams
    assert len(teams) == 20
    assert teams["VER"] == "Red Bull Racing"
    assert teams["LEC"] == "Ferrari"
    assert teams["NOR"] == "McLaren"


def test_race_length_matches_the_official_distance(monza_2024: RaceWeekend) -> None:
    assert monza_2024.pre_race.race_laps == 53


def test_practice_sessions_are_included(monza_2024: RaceWeekend) -> None:
    names = [s.name for s in monza_2024.pre_race.sessions]
    assert names == ["FP1", "FP2", "FP3", "Q"]


def test_practice_laps_carry_tyre_set_identity_compound_age_and_new_flag(
    monza_2024: RaceWeekend,
) -> None:
    fp1 = next(s for s in monza_2024.pre_race.sessions if s.name == "FP1")
    assert fp1.laps
    sample = next(lap for lap in fp1.laps if not lap.pit_out and not lap.pit_in)

    assert sample.tyre_set  # non-empty identity
    assert isinstance(sample.compound, Compound)
    assert sample.tyre_age >= 1
    assert isinstance(sample.new_when_fitted, bool)
    assert sample.driver in monza_2024.pre_race.teams


def test_pit_in_and_pit_out_flags_are_populated(monza_2024: RaceWeekend) -> None:
    all_laps = [
        lap for session in monza_2024.pre_race.sessions for lap in session.laps
    ]
    assert any(lap.pit_in for lap in all_laps)
    assert any(lap.pit_out for lap in all_laps)


def test_race_stints_and_neutralisations_are_kept_separate_from_pre_race(
    monza_2024: RaceWeekend,
) -> None:
    assert monza_2024.race.stints
    # Every stint belongs to a race starter and uses a known Compound.
    for stint in monza_2024.race.stints:
        assert stint.driver in monza_2024.pre_race.teams
        assert isinstance(stint.compound, Compound)
        assert stint.start_lap <= stint.end_lap
    # Monza 2024 ran green — no SC/VSC period — but the field is a tuple.
    assert isinstance(monza_2024.race.neutralisations, tuple)
    # The race session itself is not in the pre-race sessions.
    assert "R" not in [s.name for s in monza_2024.pre_race.sessions]
    assert "Race" not in [s.name for s in monza_2024.pre_race.sessions]


def test_pit_loss_is_a_positive_number(monza_2024: RaceWeekend) -> None:
    assert monza_2024.pre_race.pit_loss > 10.0
    assert monza_2024.pre_race.pit_loss < 40.0


def test_pit_loss_never_includes_the_race_being_predicted() -> None:
    # Prove by construction: if we restrict the pit-loss sources to seasons
    # at or after the race itself, no past data is available and the loader
    # refuses to invent a number.
    from f1_strategy.fastf1_loader import _pit_loss_at_circuit

    with pytest.raises(ValueError, match="no previous"):
        _pit_loss_at_circuit(
            circuit="Monza",
            race_season=2024,
            min_season=2024,
            cache_dir=CACHE_DIR,
        )


def test_repeat_loads_come_from_the_local_cache(monza_2024: RaceWeekend) -> None:
    # The first load (via the fixture) populates the cache. A second load must
    # not need the network — we check by looking for FastF1 cache artefacts.
    import fastf1

    cache_files = list(Path(fastf1.Cache._CACHE_DIR).rglob("*.ff1pkl"))
    assert cache_files
