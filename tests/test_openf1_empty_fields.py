"""Fast tests for ticket 30: OpenF1 rows with empty fields.

The 2026-10-26 baseline excluded five races (2023 Hungary, Belgium,
Qatar; 2024 Miami, Emilia Romagna) with ``int() argument must be ...
not 'NoneType'``. Every one crashed in the pre-race session loader on a
``/v1/stints`` row whose ``lap_start`` and ``lap_end`` are both null.
The fixture ``empty_fields_2023_2024.json`` holds the real rows from
those sessions (trimmed to a few drivers), plus the race-control
sequences behind São Paulo 2023's empty past-race samples, so this file
runs without the network.

Rules pinned here:

- A stint row with empty ``lap_start``/``lap_end`` is dropped and
  counted. It covers no lap, so dropping it must give exactly the
  laps the session would have had without the row.
- A stint row with empty ``compound`` is dropped and counted. It can't
  give a lap a Compound; a lap it covered falls to another stint that
  covers it, or is skipped like any lap outside every stint.
- The counts reach ``PreRaceInfo.data_quality_warnings`` (ticket 28's
  record), and from there the Backtest report.
- An SC or VSC still open when a red flag is followed by a standing
  restart ends on the red-flag lap, instead of running to the end of
  the race.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from weekend_builder import TEAMS, standard_practice, weekend as hand_weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    Stint,
    format_backtest,
    predict,
    run_backtest,
)
from f1_strategy.openf1_loader import (
    _drop_stint_rows_with_empty_fields,
    _load_pre_race_session,
    _neutralisation_periods,
    load_weekend,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


class _FixtureClient:
    """URL-keyed recorded responses; fails loudly on an unrecorded request."""

    def __init__(self, fixture: dict[str, list[dict]]):
        self._fixture = {k: v for k, v in fixture.items() if not k.startswith("_")}

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        key = endpoint
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key = f"{endpoint}?{query}"
        if key not in self._fixture:
            raise AssertionError(f"no OpenF1 fixture row for {key!r}")
        return self._fixture[key]


def _load_fixture(name: str) -> dict[str, list[dict]]:
    with (FIXTURES / name).open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def rows() -> dict[str, list[dict]]:
    return _load_fixture("empty_fields_2023_2024.json")


# The driver numbers kept in the fixture. #7 at Hungary FP1 is not in
# any 2023 drivers list: OpenF1 carries placeholder stint rows for it.
_TLA = {
    1: "VER", 2: "SAR", 4: "NOR", 11: "PER", 40: "LAW", 44: "HAM", 63: "RUS", 81: "PIA",
}


def _without_empty_rows(fixture: dict, session_key: int) -> dict:
    """The fixture with the session's empty-field stint rows removed."""
    trimmed = copy.deepcopy(fixture)
    key = f"stints?session_key={session_key}"
    trimmed[key] = [
        s
        for s in trimmed[key]
        if s["lap_start"] is not None
        and s["lap_end"] is not None
        and s["compound"] is not None
    ]
    return trimmed


# -- The five baseline crashes ------------------------------------------------

# (race, session name, session_key, empty-range rows, empty-compound rows)
_CRASHES = [
    ("2023 Hungary", "Practice 1", 9223, 3, 0),
    ("2023 Belgium", "Sprint", 9140, 1, 0),
    ("2023 Qatar", "Sprint", 9220, 1, 0),
    ("2024 Miami", "Sprint", 9506, 1, 0),
    ("2024 Emilia Romagna", "Practice 1", 9508, 1, 1),
]


@pytest.mark.parametrize(
    "race,session_name,session_key,empty_range,empty_compound",
    _CRASHES,
    ids=[c[0] for c in _CRASHES],
)
def test_pre_race_session_with_empty_stint_fields_loads(
    rows, race, session_name, session_key, empty_range, empty_compound
) -> None:
    """Each baseline crash: the session now loads, and its laps are exactly
    the laps it would have had if OpenF1 had never sent the empty rows."""
    meta = {"session_name": session_name, "session_key": session_key}

    session, warnings = _load_pre_race_session(
        _FixtureClient(rows), meta, tla_by_num=_TLA
    )
    expected, expected_warnings = _load_pre_race_session(
        _FixtureClient(_without_empty_rows(rows, session_key)), meta, tla_by_num=_TLA
    )

    assert session == expected
    assert expected_warnings == ()
    total = len(rows[f"stints?session_key={session_key}"])
    expected_lines = []
    if empty_range:
        expected_lines.append(
            f"{session.name} /v1/stints: dropped {empty_range} of {total} rows "
            "with empty lap_start/lap_end"
        )
    if empty_compound:
        expected_lines.append(
            f"{session.name} /v1/stints: dropped {empty_compound} of {total} rows "
            "with empty compound"
        )
    assert warnings == tuple(expected_lines)


def test_hungary_fp1_keeps_its_timed_laps(rows) -> None:
    """Dropping the placeholder rows doesn't empty the session: RUS's
    timed laps on known Compounds survive."""
    session, _ = _load_pre_race_session(
        _FixtureClient(rows),
        {"session_name": "Practice 1", "session_key": 9223},
        tla_by_num=_TLA,
    )
    assert session.laps
    assert {lap.driver for lap in session.laps} == {"RUS"}


def test_a_lap_under_an_empty_compound_stint_takes_the_covering_stints_compound(
    rows,
) -> None:
    """Imola 2024 FP1, SAR: stint 2 (lap 2 only) has no compound, but
    stint 3 (laps 1-14, Soft) also covers lap 2."""
    session, _ = _load_pre_race_session(
        _FixtureClient(rows),
        {"session_name": "Practice 1", "session_key": 9508},
        tla_by_num=_TLA,
    )
    lap_2 = [lap for lap in session.laps if lap.lap_number == 2]
    assert [lap.compound for lap in lap_2] == [Compound.SOFT]


# -- Race-session stints -------------------------------------------------------


@pytest.mark.parametrize(
    "race,session_key", [("2023 Belgium", 9141), ("2023 Qatar", 9221)]
)
def test_race_stint_rows_with_empty_range_are_dropped_and_counted(
    rows, race, session_key
) -> None:
    """PIA (Belgium) and HAM (Qatar) retired on lap 1: OpenF1 gives each
    one stint row with no range. Ticket 22 already skipped it; now the
    drop is counted."""
    stints = rows[f"stints?session_key={session_key}"]

    kept, warnings = _drop_stint_rows_with_empty_fields(stints, session="Race")

    assert kept == [s for s in stints if s["lap_start"] is not None]
    assert warnings == (
        f"Race /v1/stints: dropped 1 of {len(stints)} rows with empty lap_start/lap_end",
    )


def test_clean_stint_rows_give_no_warning() -> None:
    clean = [
        {"driver_number": 1, "lap_start": 1, "lap_end": 20, "compound": "SOFT"},
    ]
    assert _drop_stint_rows_with_empty_fields(clean, session="FP2") == (clean, ())


# -- Warnings reach the weekend and the report ---------------------------------


def test_load_weekend_records_empty_field_drops_in_data_quality_warnings() -> None:
    """End to end on the Monza 2024 fixture with one empty-range stint row
    added to FP1 and one to the race: the weekend loads, the race
    Stints are unchanged, and both drops are recorded."""
    monza = _load_fixture("monza_2024.json")
    clean = load_weekend(2024, "Italian Grand Prix", client=_FixtureClient(monza))

    dirty = copy.deepcopy(monza)
    empty = {
        "driver_number": 16,
        "stint_number": 9,
        "lap_start": None,
        "lap_end": None,
        "compound": "MEDIUM",
        "tyre_age_at_start": 0,
    }
    dirty["stints?session_key=9581"].append(dict(empty, session_key=9581))
    dirty["stints?session_key=9590"].append(dict(empty, session_key=9590))
    weekend = load_weekend(2024, "Italian Grand Prix", client=_FixtureClient(dirty))

    assert weekend.race == clean.race
    assert weekend.pre_race.sessions == clean.pre_race.sessions
    fp1_total = len(dirty["stints?session_key=9581"])
    race_total = len(dirty["stints?session_key=9590"])
    assert weekend.pre_race.data_quality_warnings == (
        f"FP1 /v1/stints: dropped 1 of {fp1_total} rows with empty lap_start/lap_end",
        f"Race /v1/stints: dropped 1 of {race_total} rows with empty lap_start/lap_end",
    )


def test_load_weekend_keeps_history_warnings_after_its_own() -> None:
    monza = copy.deepcopy(_load_fixture("monza_2024.json"))
    monza["stints?session_key=9590"].append(
        {"driver_number": 16, "lap_start": None, "lap_end": None, "compound": "SOFT"}
    )
    history_warning = "2023 Monza: no usable past-race samples"

    weekend = load_weekend(
        2024,
        "Italian Grand Prix",
        client=_FixtureClient(monza),
        measure_history=lambda circuit, season: (25.0, (2023,), False, {}, (history_warning,)),
    )

    assert weekend.pre_race.data_quality_warnings[-1] == history_warning
    assert weekend.pre_race.data_quality_warnings[0].startswith("Race /v1/stints")


def test_backtest_report_lists_data_quality_warnings() -> None:
    """The warnings are no longer only about history, so the report's
    section is named for both tickets that write to it."""
    base = hand_weekend(standard_practice(), TEAMS)
    top = predict(base)["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    warning = "Race /v1/stints: dropped 1 of 57 rows with empty lap_start/lap_end"
    weekend = RaceWeekend(
        pre_race=replace(base.pre_race, data_quality_warnings=(warning,)),
        race=RaceOutcome(
            stints=(
                Stint("VER", top.strategy.compounds[0], 1, stop_lap),
                Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
            ),
            neutralisations=(),
            finishing_status={"VER": True},
        ),
    )

    result = run_backtest(
        [RaceSpec(2023, "GP")], load=lambda s, e: weekend, wait=lambda s, r: None
    )
    text = format_backtest(result)

    assert "Data quality warnings (tickets 28, 30):" in text
    assert f"    {warning}" in text


# -- São Paulo 2023: an SC ended by a red flag ---------------------------------


def test_sao_paulo_2023_lap_1_safety_car_ends_at_the_red_flag(rows) -> None:
    """SC on lap 1, red flag on lap 2, standing restart on lap 3. The SC
    has no "IN THIS LAP" message; it used to run to lap 71 and leave
    the race with no clean lap to measure from."""
    periods, warnings = _neutralisation_periods(
        rows["race_control?session_key=9205"], race_laps=71
    )
    assert periods == (NeutralisationPeriod("SC", 1, 2),)
    assert warnings == ()


def test_mexico_city_2023_safety_car_ends_at_the_red_flag(rows) -> None:
    periods, warnings = _neutralisation_periods(
        rows["race_control?session_key=9181"], race_laps=71
    )
    assert periods == (
        NeutralisationPeriod("VSC", 5, 5),
        NeutralisationPeriod("SC", 33, 34),
    )
    assert warnings == ()


def test_melbourne_2023_red_flagged_safety_cars_are_both_kept(rows) -> None:
    """Two SCs ended by red flags (laps 7-8 and 54-55). The lap-7 SC used
    to be overwritten by the lap-54 deployment and lost."""
    periods, warnings = _neutralisation_periods(
        rows["race_control?session_key=7787"], race_laps=58
    )
    assert periods == (
        NeutralisationPeriod("SC", 1, 3),
        NeutralisationPeriod("SC", 7, 8),
        NeutralisationPeriod("VSC", 18, 19),
        NeutralisationPeriod("SC", 54, 55),
    )
    assert warnings == ()


def test_a_rolling_restart_after_a_red_flag_keeps_the_period_open(rows) -> None:
    """Zandvoort 2023: VSC on lap 64, red flag, rolling restart behind the
    SC. The SC laps after the restart have no "DEPLOYED" message of
    their own, so ending the VSC at the red flag would count them as
    green. The period stays open and is capped, with its warning."""
    periods, warnings = _neutralisation_periods(
        rows["race_control?session_key=9149"], race_laps=72
    )
    assert periods == (
        NeutralisationPeriod("SC", 16, 21),
        NeutralisationPeriod("VSC", 64, 72),
    )
    assert len(warnings) == 1
