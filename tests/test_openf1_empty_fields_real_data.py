"""Slow tests for ticket 30 on the real OpenF1 cache.

The five races the 2026-10-26 baseline excluded with ``int() argument
must be ... not 'NoneType'`` load through the router and are scored,
with the dropped empty-field stint rows recorded as Data Quality
Warnings. São Paulo 2023, whose lap-1 SC used to run to the flag, now
gives past-race samples to the 2025 race.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import NeutralisationPeriod, RaceSpec, run_backtest
from f1_strategy.data import load_weekend
from f1_strategy.openf1_client import OpenF1Client
from f1_strategy.openf1_loader import load_past_race_samples

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
FASTF1_CACHE_DIR = ROOT / ".cache" / "fastf1"
OPENF1_CACHE_DIR = ROOT / ".cache" / "openf1"


def _loader(season: int, event: str):
    return load_weekend(
        season,
        event,
        fastf1_cache_dir=FASTF1_CACHE_DIR,
        openf1_cache_dir=OPENF1_CACHE_DIR,
    )


# Each race's target-weekend Data Quality Warnings, from the warm cache
# on 2026-10-26. History warnings, if any, follow these.
_FIVE = {
    RaceSpec(2023, "Hungarian Grand Prix"): (
        "FP1 /v1/stints: dropped 45 of 114 rows with empty lap_start/lap_end",
    ),
    RaceSpec(2023, "Belgian Grand Prix", True): (
        "S /v1/stints: dropped 10 of 42 rows with empty lap_start/lap_end",
        "Race /v1/stints: dropped 1 of 57 rows with empty lap_start/lap_end",
    ),
    RaceSpec(2023, "Qatar Grand Prix", True): (
        "S /v1/stints: dropped 1 of 23 rows with empty lap_start/lap_end",
        "Race /v1/stints: dropped 1 of 73 rows with empty lap_start/lap_end",
    ),
    RaceSpec(2024, "Miami Grand Prix", True): (
        "S /v1/stints: dropped 1 of 57 rows with empty lap_start/lap_end",
    ),
    RaceSpec(2024, "Emilia Romagna Grand Prix"): (
        "FP1 /v1/stints: dropped 16 of 85 rows with empty lap_start/lap_end",
        "FP1 /v1/stints: dropped 3 of 85 rows with empty compound",
    ),
}


@pytest.mark.parametrize("spec", list(_FIVE), ids=lambda s: f"{s.season} {s.event}")
def test_baseline_crash_race_is_scored(spec: RaceSpec) -> None:
    result = run_backtest([spec], load=_loader)

    assert result.excluded == ()
    (race,) = result.races
    assert race.summary.scoreable_drivers > 0
    expected = _FIVE[spec]
    assert race.history_warnings[: len(expected)] == expected


def test_sao_paulo_2023_gives_past_race_samples() -> None:
    samples = load_past_race_samples(
        OpenF1Client(cache_dir=OPENF1_CACHE_DIR), 2023, "São Paulo"
    )
    assert samples.pit_losses
    assert samples.stint_rates


def test_2025_sao_paulo_measures_pit_loss_from_2023_too() -> None:
    """The baseline warned "2023 São Paulo: no usable past-race samples"."""
    result = run_backtest([RaceSpec(2025, "São Paulo Grand Prix", True)], load=_loader)

    (race,) = result.races
    assert race.pit_loss_seasons == (2022, 2023, 2024)
    assert race.history_warnings == ()


def test_sao_paulo_2023_race_reads_one_short_safety_car() -> None:
    weekend = _loader(2023, "São Paulo Grand Prix")
    assert weekend.race.neutralisations == (NeutralisationPeriod("SC", 1, 2),)
