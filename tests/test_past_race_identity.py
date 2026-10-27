"""Fast tests for ticket 38: each past race counts once, however many aliases reach it.

The past-race scan asks each source for the circuit's race once per alias
name (ticket 16). The OpenF1 meeting lookup used to be a substring test
across ``meeting_name``, ``location`` and ``country_name``, so for
Singapore both "Marina Bay" (the location) and "Singapore" (inside the
meeting name and equal to the country) found the same meeting, and its
Pit Loss and Historical Degradation samples were counted twice for the
2024 and 2025 races.

Two fixes, both pinned here:

- The OpenF1 lookup matches ``location`` or ``meeting_name`` exactly
  (ignoring case), so a short name can't reach a meeting through a longer
  one ("Miami" inside "Miami Gardens", "Singapore" inside "Singapore
  Grand Prix").
- Every :class:`PastRaceSamples` names the source's own race (OpenF1 race
  session key, FastF1 season and round), and the scan counts each race
  once per season by that identity, not by the name it was asked for.

Meeting rows are real (trimmed) OpenF1 rows in
``fixtures/openf1/aliases_2023_2025.json``. No network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from f1_strategy import Compound
from f1_strategy.data import measure_pit_loss_and_history
from f1_strategy.openf1_loader import (
    PastRaceSamples,
    _find_meeting,
    _past_races_at_circuit,
    load_past_race_samples,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


class _RecordingClient:
    """URL-keyed OpenF1 stand-in that fails on any unrecorded request."""

    def __init__(self) -> None:
        with (FIXTURES / "aliases_2023_2025.json").open(encoding="utf-8") as f:
            raw = json.load(f)
        self._fixture = {k: v for k, v in raw.items() if not k.startswith("_")}
        self.requests: list[str] = []

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        key = endpoint
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key = f"{endpoint}?{query}"
        self.requests.append(key)
        if key not in self._fixture:
            raise AssertionError(f"no OpenF1 fixture row for {key!r}")
        return self._fixture[key]


@pytest.fixture
def client() -> _RecordingClient:
    return _RecordingClient()


def _meeting_key(client: _RecordingClient, season: int, event: str) -> int:
    return int(_find_meeting(client.get("meetings", year=season), event)["meeting_key"])


# ---------------------------------------------------------------------------
# The OpenF1 meeting lookup is exact.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("season", "event", "meeting_key"),
    [
        (2023, "Marina Bay", 1219),
        (2023, "marina bay", 1219),
        (2023, "Singapore Grand Prix", 1219),
        (2023, "Miami", 1208),
        (2023, "Monaco", 1210),
        (2023, "Austin", 1222),
        (2023, "Las Vegas Grand Prix", 1225),
        (2025, "Miami Gardens", 1259),
        (2025, "Miami Grand Prix", 1259),
    ],
)
def test_a_location_or_meeting_name_finds_its_meeting(
    client: _RecordingClient, season: int, event: str, meeting_key: int,
) -> None:
    assert _meeting_key(client, season, event) == meeting_key


@pytest.mark.parametrize(
    ("season", "event"),
    [
        # Singapore/Marina Bay: "Singapore" is the country and part of the
        # meeting name, not the location. The old substring test matched it.
        (2023, "Singapore"),
        (2024, "Singapore"),
        # Miami/Miami Gardens: "Miami" is only a prefix of 2025's location.
        (2025, "Miami"),
        # Monaco/Monte Carlo: "Monte Carlo" is OpenF1's circuit_short_name,
        # which the lookup has never read.
        (2023, "Monte Carlo"),
        # A country shared by three meetings must not pick the first one.
        (2023, "United States"),
        # Part of a name is not a name.
        (2023, "Vegas"),
    ],
)
def test_a_name_that_is_not_a_location_or_meeting_name_finds_nothing(
    client: _RecordingClient, season: int, event: str,
) -> None:
    with pytest.raises(ValueError, match="no OpenF1 meeting matched"):
        _find_meeting(client.get("meetings", year=season), event)


def test_pre_season_testing_is_never_matched(client: _RecordingClient) -> None:
    """2023 testing shares Bahrain's location (Sakhir); only the Grand Prix
    is a race meeting, and it isn't in this fixture."""
    with pytest.raises(ValueError):
        _find_meeting(client.get("meetings", year=2023), "Sakhir")


# ---------------------------------------------------------------------------
# Each source names its own race.
# ---------------------------------------------------------------------------


def test_openf1_samples_name_the_race_session(client: _RecordingClient) -> None:
    samples = load_past_race_samples(client, 2023, "Marina Bay")
    assert samples.pit_losses
    assert samples.race_id == "openf1 session 9165"


def test_openf1_samples_with_no_meeting_name_no_race(client: _RecordingClient) -> None:
    assert load_past_race_samples(client, 2023, "Singapore").race_id is None


# ---------------------------------------------------------------------------
# Singapore / Marina Bay through the real OpenF1 loader.
# ---------------------------------------------------------------------------


def _fastf1_2022_marina_bay(season, event, **kwargs) -> PastRaceSamples:
    if (season, event) != (2022, "Marina Bay"):
        return PastRaceSamples(pit_losses=(), stint_rates=())
    return PastRaceSamples(
        pit_losses=(30.0,),
        stint_rates=((Compound.MEDIUM, 0.10, 20),),
        race_id="fastf1 2022 round 17",
    )


def test_marina_bay_2024_counts_2023_singapore_once(client: _RecordingClient) -> None:
    """The bug as it ran: 2024 Marina Bay reads 2023 Singapore under both
    alias names. Counted once, the 2023 race adds exactly the samples one
    direct load of it gives."""
    one_race = load_past_race_samples(_RecordingClient(), 2023, "Marina Bay")
    pit_loss, seasons, estimated, hist = measure_pit_loss_and_history(
        circuit="Marina Bay",
        race_season=2024,
        openf1_client=client,
        fastf1_load_past_race_samples=_fastf1_2022_marina_bay,
    )
    assert seasons == (2022, 2023)
    assert estimated is False
    median_2023 = sorted(one_race.pit_losses)[len(one_race.pit_losses) // 2]
    # 2023 weight 1.0, 2022 weight 0.5, one median each.
    assert pit_loss == pytest.approx((median_2023 * 1.0 + 30.0 * 0.5) / 1.5)
    stints_2023 = {c: 0 for c in Compound}
    for compound, _, _ in one_race.stint_rates:
        stints_2023[compound] += 1
    for compound, degradation in hist.items():
        expected = stints_2023[compound] + (compound is Compound.MEDIUM)
        assert degradation.stint_count == expected, compound
    # The race session's rows were fetched once: "Singapore" no longer
    # reaches the meeting at all.
    assert client.requests.count("laps?session_key=9165") == 1


def test_openf1_only_scan_counts_2023_singapore_once(client: _RecordingClient) -> None:
    """The direct OpenF1 loader's own scan (no router) has the same rule."""
    one_race = load_past_race_samples(client, 2023, "Marina Bay")
    _, seasons, hist = _past_races_at_circuit(
        circuit="Marina Bay",
        race_season=2024,
        client=client,
        fuel_effect_s_per_lap=0.03,
        history_min_stint_length=4,
    )
    assert seasons == (2023,)
    assert sum(h.stint_count for h in hist.values()) == len(one_race.stint_rates)


# ---------------------------------------------------------------------------
# The scan de-duplicates by race identity, whatever the lookup returns.
# ---------------------------------------------------------------------------


def _same_race_for_every_alias(race_ids: dict[int, str]):
    """A fake source that, like the old substring lookup, answers every
    alias name with the same race."""
    calls: list[tuple[int, str]] = []

    def fake(*args, **kwargs) -> PastRaceSamples:
        season, event = args[-2], args[-1]
        calls.append((season, event))
        if season not in race_ids:
            return PastRaceSamples(pit_losses=(), stint_rates=())
        return PastRaceSamples(
            pit_losses=(20.0 + season - 2022,),
            stint_rates=((Compound.HARD, 0.05, 30),),
            race_id=race_ids[season],
        )

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


@pytest.mark.parametrize(
    ("circuit", "race_season", "openf1_races"),
    [
        # Singapore/Marina Bay: 2023 and 2024 race sessions.
        ("Marina Bay", 2025, {2023: "openf1 session 9165", 2024: "openf1 session 9606"}),
        # Miami/Miami Gardens: 2023 and 2024 race sessions.
        ("Miami Gardens", 2025, {2023: "openf1 session 9078", 2024: "openf1 session 9507"}),
    ],
)
def test_each_past_race_contributes_once_per_season(
    circuit: str, race_season: int, openf1_races: dict[int, str],
) -> None:
    fastf1 = _same_race_for_every_alias({2022: "fastf1 2022 round 5"})
    openf1 = _same_race_for_every_alias(openf1_races)
    pit_loss, seasons, _, hist = measure_pit_loss_and_history(
        circuit=circuit,
        race_season=race_season,
        openf1_client=None,
        fastf1_load_past_race_samples=fastf1,
        openf1_load_past_race_samples=openf1,
    )
    # Both alias names were asked for in every season...
    assert len(fastf1.calls) == 2 and len(openf1.calls) == 4
    # ...but each season's race counted once: one Stint per season.
    assert seasons == (2022, 2023, 2024)
    assert hist[Compound.HARD].stint_count == 3
    # Medians 20, 21, 22 with weights 0.25, 0.5, 1.0.
    assert pit_loss == pytest.approx((20 * 0.25 + 21 * 0.5 + 22 * 1.0) / 1.75)


def test_pre_era_pit_loss_counts_each_race_once() -> None:
    """The ADR-0004 pre-era pass for a 2022 first-of-era circuit reads
    FastF1 per alias too; a race reached under both names counts once.
    2021 is reached under both names and 2019 under one, so counting 2021
    twice would pull the weighted mean towards it."""
    both_names = _same_race_for_every_alias({2021: "fastf1 2021 round 5"})

    def fastf1(season, event, **kwargs) -> PastRaceSamples:
        if (season, event) == (2019, "Monte Carlo"):
            return PastRaceSamples(
                pit_losses=(17.0,), stint_rates=(), race_id="fastf1 2019 round 6"
            )
        return both_names(season, event, **kwargs)

    pit_loss, seasons, _, _ = measure_pit_loss_and_history(
        circuit="Monaco",
        race_season=2022,
        openf1_client=None,
        fastf1_load_past_race_samples=fastf1,
        openf1_load_past_race_samples=_same_race_for_every_alias({}),
    )
    assert seasons == (2019, 2021)
    # Medians 17 (2019) and 19 (2021), weights 0.25 and 1.0, once each.
    assert pit_loss == pytest.approx((17 * 0.25 + 19 * 1.0) / 1.25)


def test_two_different_races_in_one_season_both_count() -> None:
    """De-duplication is by race, not by season: two distinct races found
    in one season (not seen at any 2022–2025 circuit) are both kept."""
    def fake(client, season, event, **kwargs) -> PastRaceSamples:
        return PastRaceSamples(
            pit_losses=(20.0,) if event == "Miami" else (30.0,),
            stint_rates=((Compound.HARD, 0.05, 30),),
            race_id=f"openf1 session {event}",
        )

    _, _, _, hist = measure_pit_loss_and_history(
        circuit="Miami Gardens",
        race_season=2024,
        openf1_client=None,
        fastf1_load_past_race_samples=_same_race_for_every_alias({}),
        openf1_load_past_race_samples=fake,
    )
    assert hist[Compound.HARD].stint_count == 2
