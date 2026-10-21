"""Seam 2: FastF1 real-weekend → race weekend description.

These tests load cached real 2024 weekends through the public loader and
check that the description is sensible: Monza (conventional, green race),
Jeddah (Safety Car after Stroll's lap-7 crash) and Austin (sprint weekend).
They are marked `slow` because they hit the FastF1 on-disk cache and, on a
cold cache, the live timing API.
"""

from pathlib import Path

import pytest
import requests

from f1_strategy import Compound, NeutralisationPeriod, RaceWeekend
from f1_strategy.fastf1_loader import list_season, load_weekend
from f1_strategy.regulation_era import era_start

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastf1"


@pytest.fixture(scope="module")
def monza_2024() -> RaceWeekend:
    return load_weekend(2024, "Italian Grand Prix", cache_dir=CACHE_DIR)


@pytest.fixture(scope="module")
def jeddah_2024() -> RaceWeekend:
    return load_weekend(2024, "Saudi Arabian Grand Prix", cache_dir=CACHE_DIR)


@pytest.fixture(scope="module")
def austin_2024() -> RaceWeekend:
    return load_weekend(2024, "United States Grand Prix", cache_dir=CACHE_DIR)


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


def test_practice_laps_under_only_yellow_or_red_flags_are_not_neutralised(
    monza_2024: RaceWeekend,
) -> None:
    # Monza 2024's practice and qualifying had yellow (2) and red (5) flags
    # but no Safety Car (4) or VSC (6/7) codes, so no lap is neutralised.
    all_laps = [lap for s in monza_2024.pre_race.sessions for lap in s.laps]
    assert not [lap for lap in all_laps if lap.neutralised]


def test_safety_car_period_matches_race_control(jeddah_2024: RaceWeekend) -> None:
    # Race control: "SAFETY CAR DEPLOYED" on lap 7 after Stroll's crash,
    # "SAFETY CAR IN THIS LAP" on lap 9. No other SC or VSC in the race.
    assert jeddah_2024.race.neutralisations == (
        NeutralisationPeriod(kind="SC", start_lap=7, end_lap=9),
    )


def test_sprint_weekend_includes_sprint_qualifying_and_the_sprint(
    austin_2024: RaceWeekend,
) -> None:
    pre_race = austin_2024.pre_race
    assert pre_race.is_sprint_weekend is True
    assert [s.name for s in pre_race.sessions] == ["FP1", "SQ", "S", "Q"]
    assert pre_race.race_laps == 56

    sprint = next(s for s in pre_race.sessions if s.name == "S")
    assert max(lap.lap_number for lap in sprint.laps) == 19  # 100 km at COTA
    assert len({lap.driver for lap in sprint.laps}) >= 18


def test_a_2022_race_gets_no_historical_degradation() -> None:
    # ADR-0004 / ticket 01: Historical Degradation draws only on earlier
    # seasons in the same Regulation Era. 2022 is the first season of the
    # 2022–2025 era, so no past-era season exists and the dict is empty.
    # Pit Loss uses pre-era seasons via its exception (ADR-0004, ticket 03)
    # under default settings, so the load succeeds with no override.
    weekend = load_weekend(2022, "Italian Grand Prix", cache_dir=CACHE_DIR)
    assert weekend.pre_race.historical_degradation == {}


def test_a_2022_races_pit_loss_falls_back_to_pre_era_seasons() -> None:
    # ADR-0004's Pit Loss exception / ticket 03: a 2022 race has no same-era
    # race before it, so Pit Loss falls back to pre-era seasons (2018–2021).
    # Monza was raced every year in that window.
    weekend = load_weekend(2022, "Italian Grand Prix", cache_dir=CACHE_DIR)
    seasons = weekend.pre_race.pit_loss_seasons
    assert seasons, "pre-era fallback should contribute at least one season"
    assert all(2018 <= s <= 2021 for s in seasons), seasons
    assert weekend.pre_race.pit_loss > 10.0
    assert weekend.pre_race.pit_loss < 40.0


def test_a_2024_races_pit_loss_uses_only_same_era_seasons(
    monza_2024: RaceWeekend,
) -> None:
    # A race that has same-era history (Monza 2022 and 2023 under the current
    # Regulation Era) uses only those seasons for Pit Loss — the pre-era
    # fallback is reserved for circuits with no same-era race before them.
    era = era_start(2024)
    seasons = monza_2024.pre_race.pit_loss_seasons
    assert seasons, "same-era Monza history should supply Pit Loss"
    assert all(era <= s < 2024 for s in seasons), seasons


def test_a_2023_races_historical_degradation_uses_2022_only() -> None:
    # ADR-0004 / ticket 01: a 2023 race, in the 2022–2025 era, has 2022 as
    # the only earlier season in the era, so every Compound's historical
    # fit lists 2022 and only 2022.
    weekend = load_weekend(2023, "Italian Grand Prix", cache_dir=CACHE_DIR)
    assert weekend.pre_race.historical_degradation  # at least one Compound
    for compound, hist in weekend.pre_race.historical_degradation.items():
        assert hist.seasons == (2022,), (compound, hist.seasons)


def test_list_season_2024_marks_sprint_weekends() -> None:
    # Ticket 02 acceptance: the loader lists a season's race weekends with
    # sprints marked. 2024 ran 24 championship rounds, of which six were
    # sprint weekends (China, Miami, Austria, Austin, São Paulo, Qatar).
    specs = list_season(2024, cache_dir=CACHE_DIR)
    assert len(specs) == 24
    sprints = {s.event for s in specs if s.is_sprint_weekend}
    assert sprints == {
        "Chinese Grand Prix",
        "Miami Grand Prix",
        "Austrian Grand Prix",
        "United States Grand Prix",
        "São Paulo Grand Prix",
        "Qatar Grand Prix",
    }
    # The remaining 18 weekends are conventional.
    assert len([s for s in specs if not s.is_sprint_weekend]) == 18


def test_repeat_loads_come_from_the_local_cache(
    monza_2024: RaceWeekend, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fixture's load filled the cache; a repeat load with every HTTP
    # request refused must still produce the same weekend.
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("network disabled for this test")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", refuse)

    assert load_weekend(2024, "Italian Grand Prix", cache_dir=CACHE_DIR) == monza_2024
