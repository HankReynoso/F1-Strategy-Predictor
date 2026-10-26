"""Ticket 31: estimated Pit Loss for Shanghai (2024 China).

Shanghai wasn't raced 2020–2023 and its 2018–2019 races can no longer be
downloaded (ADR-0006), so 2024 China has no measurable Pit Loss history
and takes the pit lane table estimate. 2025 China measures from 2024.

Fast tests go through the data facade's ``measure_pit_loss_and_history``
and ``run_backtest``; the slow test loads real 2024 China through
``load_weekend`` (OpenF1) and scores it in a Backtest.
"""

from __future__ import annotations

import pytest

from f1_strategy import Compound, RaceSpec, run_backtest
from f1_strategy.backtest import format_backtest
from f1_strategy.data import load_weekend, measure_pit_loss_and_history
from f1_strategy.openf1_loader import PastRaceSamples
from f1_strategy.pit_lane_table import estimated_pit_loss, pit_lane_entry
from test_estimated_pit_loss import _estimated_weekend


def _no_samples(*args, **kwargs):
    return PastRaceSamples(pit_losses=(), stint_rates=())


def test_shanghai_has_a_cited_pit_lane_entry() -> None:
    entry = pit_lane_entry("Shanghai")
    assert entry is not None
    assert entry.length_m == 351.0
    assert entry.speed_limit_kmh == 80.0
    assert "McLaren" in entry.source and "FIA 2019" in entry.source
    # Single-source, off-year figures are recorded, not hidden.
    assert "unconfirmed" in entry.note


def test_2024_china_pit_loss_is_estimated_from_the_table() -> None:
    pit_loss, seasons, estimated, _ = measure_pit_loss_and_history(
        circuit="Shanghai",
        race_season=2024,
        openf1_client=None,
        fastf1_load_past_race_samples=_no_samples,
        openf1_load_past_race_samples=_no_samples,
    )
    assert estimated is True
    assert seasons == ()
    assert pit_loss == pytest.approx(estimated_pit_loss(pit_lane_entry("Shanghai")))


def test_2025_china_pit_loss_comes_from_2024_not_the_estimate() -> None:
    seen: list[tuple[str, int]] = []

    def openf1(client, season, event, **kwargs):
        seen.append(("openf1", season))
        if season == 2024:
            return PastRaceSamples(
                pit_losses=(21.0, 22.0, 23.0),
                stint_rates=((Compound.MEDIUM, 0.1, 20),),
            )
        return _no_samples()

    def fastf1(season, event, **kwargs):
        seen.append(("fastf1", season))
        return _no_samples()

    pit_loss, seasons, estimated, _ = measure_pit_loss_and_history(
        circuit="Shanghai",
        race_season=2025,
        openf1_client=None,
        fastf1_load_past_race_samples=fastf1,
        openf1_load_past_race_samples=openf1,
    )
    assert estimated is False
    assert seasons == (2024,)
    assert pit_loss == pytest.approx(22.0)
    assert ("openf1", 2024) in seen


def test_backtest_scores_2024_china_and_lists_it_as_estimated() -> None:
    weekend = _estimated_weekend("Shanghai")
    result = run_backtest(
        [RaceSpec(2024, "Chinese Grand Prix")], load=lambda s, e: weekend
    )
    assert result.excluded == ()
    (china,) = result.races
    assert china.circuit == "Shanghai"
    assert china.estimated_pit_loss is True
    assert "2024 Chinese Grand Prix (Shanghai)" in format_backtest(result)


@pytest.mark.slow
def test_real_2024_china_loads_with_an_estimated_pit_loss_and_is_scored() -> None:
    weekend = load_weekend(2024, "Chinese Grand Prix")
    assert weekend.pre_race.circuit == "Shanghai"
    assert weekend.pre_race.estimated_pit_loss is True
    assert weekend.pre_race.pit_loss_seasons == ()
    assert weekend.pre_race.pit_loss == pytest.approx(
        estimated_pit_loss(pit_lane_entry("Shanghai"))
    )
    result = run_backtest([RaceSpec(2024, "Chinese Grand Prix")], load=load_weekend)
    assert result.excluded == ()
    assert len(result.races) == 1
