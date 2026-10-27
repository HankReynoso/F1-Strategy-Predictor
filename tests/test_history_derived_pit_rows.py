"""Fast tests for ticket 37: Historical Degradation uses derived pit rows.

OpenF1's ``/v1/pit`` is empty for the first seven 2023 races (ADR-0006).
Ticket 28 rebuilt pit-in laps from Stint boundaries for Pit Loss, but
the Historical Degradation fit still read the empty ``/v1/pit``, so
each Stint's slow in-lap stayed in the fit. These tests pin that both
samples now read the same pit rows.

Hand-built rows through a URL-keyed fixture client; no network.
"""

from __future__ import annotations

from typing import Any

import pytest

from f1_strategy import Compound
from f1_strategy.openf1_loader import load_past_race_samples

FUEL = 0.03


class _FixtureClient:
    """URL-keyed OpenF1 client stand-in; same shape as the ticket 22/28 tests."""

    def __init__(self, fixture: dict[str, list[dict]]):
        self._fixture = fixture

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        key = f"{endpoint}?{query}" if params else endpoint
        if key not in self._fixture:
            raise AssertionError(f"no OpenF1 fixture row for {key!r}")
        return self._fixture[key]


def _client(pit_rows: list[dict]) -> _FixtureClient:
    """One driver, MEDIUM laps 1–10 then HARD laps 11–20.

    Every green lap is 90 s + 0.1 s per lap of tyre age, so a clean
    fit gives exactly 0.1 s/lap. Lap 10 is the in-lap (110 s) and lap
    11 the out-lap (115 s, ``is_pit_out_lap``).
    """
    laps = []
    for lap in range(1, 21):
        age = lap if lap <= 10 else lap - 10
        duration = 90.0 + 0.1 * age
        if lap == 10:
            duration = 110.0
        if lap == 11:
            duration = 115.0
        laps.append({
            "driver_number": 1, "lap_number": lap,
            "lap_duration": duration, "is_pit_out_lap": lap == 11,
        })
    stints = [
        {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 10,
         "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 2, "lap_start": 11, "lap_end": 20,
         "compound": "HARD", "tyre_age_at_start": 0},
    ]
    return _FixtureClient({
        "meetings?year=2023": [
            {"meeting_key": 1, "meeting_name": "Fake Grand Prix",
             "location": "Fakeville", "country_name": "Fake",
             "date_start": "2023-01-01T00:00:00+00:00", "year": 2023}
        ],
        "sessions?meeting_key=1": [{"session_name": "Race", "session_key": 1}],
        "laps?session_key=1": laps,
        "stints?session_key=1": stints,
        "pit?session_key=1": pit_rows,
        "race_control?session_key=1": [],
        "session_result?session_key=1": [
            {"driver_number": 1, "number_of_laps": 20,
             "dnf": False, "dns": False, "dsq": False}
        ],
    })


def _medium(samples) -> tuple[float, int]:
    (match,) = [(r, n) for c, r, n in samples.stint_rates if c is Compound.MEDIUM]
    return match


def test_in_lap_is_excluded_from_the_fit_when_pit_rows_are_derived():
    """With ``/v1/pit`` empty, the lap-10 in-lap is dropped from the
    MEDIUM fit: 9 laps, rate exactly 0.1 s/lap plus the fuel effect.
    Before the fix the 110 s in-lap stayed in and the rate was ~1.1."""
    samples = load_past_race_samples(
        _client(pit_rows=[]), 2023, "Fakeville",
        fuel_effect_s_per_lap=FUEL, history_min_stint_length=4,
    )
    rate, laps = _medium(samples)
    assert laps == 9
    assert rate == pytest.approx(0.1 + FUEL)


def test_degradation_fit_matches_a_race_with_real_pit_rows():
    """Derived rows give the same fit as the equivalent real ``/v1/pit``
    row, which is what "exactly as Pit Loss does" means for the fit."""
    derived = load_past_race_samples(
        _client(pit_rows=[]), 2023, "Fakeville",
        fuel_effect_s_per_lap=FUEL, history_min_stint_length=4,
    )
    real = load_past_race_samples(
        _client(pit_rows=[{"driver_number": 1, "lap_number": 10,
                           "pit_duration": 22.0}]),
        2023, "Fakeville",
        fuel_effect_s_per_lap=FUEL, history_min_stint_length=4,
    )
    assert derived == real
