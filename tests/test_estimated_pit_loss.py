"""Ticket 07: estimated Pit Loss for first-time circuits.

Fast tests cover the pit lane table, the estimation formula, the flag
propagation through the Backtest Result, and the single-race report line.
Loader-level slow tests (Miami 2022 and Las Vegas 2023) live alongside the
other `tests/test_fastf1_weekend_loader.py` cases.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    PreRaceInfo,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    Stint,
    predict,
    run_backtest,
)
from f1_strategy.backtest import format_backtest
from f1_strategy.pit_lane_table import (
    PIT_LANES,
    PitLane,
    estimated_pit_loss,
    pit_lane_entry,
)
from f1_strategy.report import format_header
from f1_strategy.settings import Settings


S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


# ---------------------------------------------------------------------------
# Pit lane table + formula
# ---------------------------------------------------------------------------


def test_table_includes_the_known_first_time_circuits():
    circuits = {entry.circuit for entry in PIT_LANES}
    # Ticket 07 survey: the only 2022–2025 circuits whose FastF1 Location
    # has no earlier race at all are Miami (first run 2022) and Las Vegas
    # (first run 2023). Both must be in the table.
    assert "Miami" in circuits
    assert "Las Vegas" in circuits


def test_pit_lane_entry_lookup_matches_table_circuit_names():
    for entry in PIT_LANES:
        assert pit_lane_entry(entry.circuit) is entry


def test_pit_lane_entry_returns_none_for_an_unknown_circuit():
    assert pit_lane_entry("Nowhere International") is None


def test_estimated_pit_loss_rises_with_longer_pit_lane():
    short = PitLane("A", length_m=300.0, speed_limit_kmh=80.0, source="")
    longer = PitLane("B", length_m=500.0, speed_limit_kmh=80.0, source="")
    assert estimated_pit_loss(longer) > estimated_pit_loss(short)


def test_estimated_pit_loss_rises_with_a_lower_speed_limit():
    low = PitLane("A", length_m=400.0, speed_limit_kmh=60.0, source="")
    high = PitLane("B", length_m=400.0, speed_limit_kmh=80.0, source="")
    assert estimated_pit_loss(low) > estimated_pit_loss(high)


def test_estimated_pit_loss_lies_in_the_calibration_band():
    # The published Pit Loss figures the formula is calibrated against
    # cluster between about 18 and 28 seconds across every F1 circuit in
    # recent seasons. The two table entries land inside that band —
    # Miami close to its ~21 s observed figure and Las Vegas close to
    # its ~22 s observed figure (ticket 07 "Checking the formula").
    for entry in PIT_LANES:
        value = estimated_pit_loss(entry)
        assert 18.0 <= value <= 28.0, (entry.circuit, value)


# ---------------------------------------------------------------------------
# Flag propagation through the Backtest Result
# ---------------------------------------------------------------------------


def _estimated_weekend(circuit: str = "Miami") -> RaceWeekend:
    """A hand-built weekend whose pit loss is flagged as estimated.

    The pre_race is replaced on a standard-practice green weekend with the
    estimated flag set, so the Backtest Result's per-race fields can be
    exercised without any FastF1 data.
    """
    base = weekend(standard_practice(), TEAMS)
    pre_race = replace(
        base.pre_race,
        circuit=circuit,
        pit_loss=20.5,
        pit_loss_seasons=(),
        estimated_pit_loss=True,
    )
    top = predict(RaceWeekend(pre_race=pre_race, race=base.race))["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    stints = (
        Stint("VER", top.strategy.compounds[0], 1, stop_lap),
        Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
    )
    return RaceWeekend(
        pre_race=pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=(),
            finishing_status={"VER": True},
        ),
    )


def _measured_weekend() -> RaceWeekend:
    """Companion weekend with measured Pit Loss (seasons listed, flag off)."""
    base = weekend(standard_practice(), TEAMS)
    pre_race = replace(
        base.pre_race,
        circuit="Monza",
        pit_loss=22.0,
        pit_loss_seasons=(2022, 2023),
        estimated_pit_loss=False,
    )
    top = predict(RaceWeekend(pre_race=pre_race, race=base.race))["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    stints = (
        Stint("VER", top.strategy.compounds[0], 1, stop_lap),
        Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
    )
    return RaceWeekend(
        pre_race=pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=(),
            finishing_status={"VER": True},
        ),
    )


def test_race_result_carries_pit_loss_seasons_and_estimated_flag():
    races = [RaceSpec(2022, "Miami"), RaceSpec(2024, "Monza")]
    weekends = {
        (2022, "Miami"): _estimated_weekend(),
        (2024, "Monza"): _measured_weekend(),
    }

    result = run_backtest(races, load=lambda s, e: weekends[(s, e)])

    miami, monza = result.races
    assert miami.estimated_pit_loss is True
    assert miami.pit_loss_seasons == ()
    assert miami.pit_loss == pytest.approx(20.5)
    assert monza.estimated_pit_loss is False
    assert monza.pit_loss_seasons == (2022, 2023)
    assert monza.pit_loss == pytest.approx(22.0)


def test_backtest_result_lists_estimated_pit_loss_races():
    races = [RaceSpec(2022, "Miami"), RaceSpec(2024, "Monza")]
    weekends = {
        (2022, "Miami"): _estimated_weekend(),
        (2024, "Monza"): _measured_weekend(),
    }

    text = format_backtest(run_backtest(races, load=lambda s, e: weekends[(s, e)]))

    assert "Pit Loss estimated" in text
    assert "2022 Miami" in text
    # Measured races are not listed in the estimated section.
    assert "2024 Monza" not in text.split("Pit Loss estimated")[1]


def test_report_header_flags_estimated_pit_loss():
    weekend_ = _estimated_weekend()
    header = format_header(weekend_.pre_race, Settings(), predictions=None)
    assert "estimated from pit lane length and speed limit" in header


def test_report_header_does_not_flag_measured_pit_loss():
    weekend_ = _measured_weekend()
    header = format_header(weekend_.pre_race, Settings(), predictions=None)
    assert "estimated from pit lane length" not in header


# ---------------------------------------------------------------------------
# Excluded Race path for an unknown first-time circuit
# ---------------------------------------------------------------------------


def test_a_circuit_with_no_history_and_no_table_entry_is_excluded():
    # Mimic the loader's refusal when a race has no history and no table
    # entry: the loader raises ValueError, which the Backtest translates
    # into an Excluded Race with reason DATA_UNAVAILABLE (ticket 02).
    def load(season, event):
        raise ValueError(
            f"no previous seasons' races at 'Nowhere' were available to "
            f"measure Pit Loss from, and 'Nowhere' has no entry in the pit "
            f"lane table (ticket 07)"
        )

    result = run_backtest([RaceSpec(2026, "Nowhere Grand Prix")], load=load)
    assert len(result.races) == 0
    assert len(result.excluded) == 1
    excluded = result.excluded[0]
    assert "pit lane table" in excluded.detail
