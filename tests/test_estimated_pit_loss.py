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


def test_table_includes_the_2022_pre_era_only_circuits():
    # Ticket 25: the five 2022 circuits whose only pre-era Pit Loss
    # history is 2018–2019 (which FastF1 can no longer download) also
    # need table entries, so their 2022 races get an estimated Pit Loss
    # instead of becoming Excluded Races. The list was confirmed against
    # the 2026-10-23 baseline attempt's Excluded Races (commit e5e9699).
    circuits = {entry.circuit for entry in PIT_LANES}
    for required in {
        "Melbourne",
        "Montréal",
        "Spa-Francorchamps",
        "Marina Bay",
        "Suzuka",
    }:
        assert required in circuits, required


def test_table_includes_shanghai():
    # Ticket 31: Shanghai wasn't raced 2020–2023 and its 2018–2019 races
    # can no longer be downloaded, so 2024 China needs an entry.
    assert "Shanghai" in {entry.circuit for entry in PIT_LANES}


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
    # Published Pit Loss figures cluster roughly 17–30 seconds across
    # recent F1 circuits: short pit lanes like Melbourne's 281 m touch
    # the low end and long ones like Spa's 653 m touch the high end
    # (ticket 25 widened the ticket-07 band of 18–28 s after Melbourne
    # and Spa entries landed just outside it). Every table entry must
    # fall inside the widened band.
    for entry in PIT_LANES:
        value = estimated_pit_loss(entry)
        assert 17.0 <= value <= 30.0, (entry.circuit, value)


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
