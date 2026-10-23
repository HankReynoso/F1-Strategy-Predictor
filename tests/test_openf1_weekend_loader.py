"""Fast tests for the OpenF1 pre-race weekend loader (ticket 21).

The loader turns OpenF1's JSON responses into a ``RaceWeekend`` whose
shape matches ``fastf1_loader.load_weekend``. These tests exercise it
against recorded responses saved under ``tests/fixtures/openf1/``: a
conventional 2024 weekend (Monza) and a sprint 2024 weekend (Austria),
each trimmed to the two drivers and few lap/stint rows the assertions
need, so the whole file runs without network and in well under a
second. One slow test that goes through a real
:class:`.openf1_client.OpenF1Client` lives in
``test_openf1_weekend_loader_real_data.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from f1_strategy import Compound, PreRaceInfo, RaceWeekend, Session
from f1_strategy.openf1_loader import (
    _find_meeting,
    _is_sprint_weekend,
    _round_number,
    load_weekend,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


class _FixtureClient:
    """Stand-in for :class:`.openf1_client.OpenF1Client` that serves rows
    from a recorded-response dict.

    The dict is keyed by ``"<endpoint>?<sorted query string>"`` — exactly
    the suffix the real client would ``_build_url`` after ``BASE_URL`` —
    so a fixture written against one URL stays stable as the loader
    changes.
    """

    def __init__(self, fixture: dict[str, list[dict]]):
        # Strip the ``_about`` metadata key, if present, before using
        # the dict as a response table.
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
def monza_fixture() -> dict[str, list[dict]]:
    return _load_fixture("monza_2024.json")


@pytest.fixture(scope="module")
def austria_fixture() -> dict[str, list[dict]]:
    return _load_fixture("austria_2024.json")


@pytest.fixture
def monza_weekend(monza_fixture) -> RaceWeekend:
    return load_weekend(2024, "Italian Grand Prix", client=_FixtureClient(monza_fixture))


@pytest.fixture
def austria_weekend(austria_fixture) -> RaceWeekend:
    return load_weekend(2024, "Austrian Grand Prix", client=_FixtureClient(austria_fixture))


# ---------------------------------------------------------------------------
# Shape: matches the FastF1 loader's return type field for field.
# ---------------------------------------------------------------------------


def test_load_weekend_returns_a_race_weekend(monza_weekend):
    assert isinstance(monza_weekend, RaceWeekend)
    assert isinstance(monza_weekend.pre_race, PreRaceInfo)
    assert monza_weekend.pre_race.season == 2024


def test_circuit_is_the_meetings_location(monza_weekend):
    assert monza_weekend.pre_race.circuit == "Monza"


def test_event_can_be_matched_by_location(monza_fixture):
    """Matching on ``event`` is case-insensitive and tries meeting_name,
    location and country_name; "Monza" (location) alone resolves."""
    weekend = load_weekend(
        2024, "monza", client=_FixtureClient(monza_fixture)
    )
    assert weekend.pre_race.circuit == "Monza"


def test_event_can_be_matched_by_country(monza_fixture):
    weekend = load_weekend(
        2024, "Italy", client=_FixtureClient(monza_fixture)
    )
    assert weekend.pre_race.circuit == "Monza"


def test_unknown_event_raises_value_error(monza_fixture):
    with pytest.raises(ValueError):
        load_weekend(2024, "no such grand prix", client=_FixtureClient(monza_fixture))


def test_pre_season_testing_is_not_matched_as_an_event(monza_fixture):
    """The 2024 meetings list includes a "Pre-Season Testing" row at
    Sakhir (same location as the Bahrain GP). Matching on "Sakhir" must
    land on the real Grand Prix, never the testing row — ``_find_meeting``
    filters testing out before matching on either name or location."""
    meetings = monza_fixture["meetings?year=2024"]
    matched = _find_meeting(meetings, "Sakhir")
    assert "Grand Prix" in matched["meeting_name"]


# ---------------------------------------------------------------------------
# Weekend format detection: sprint vs conventional from the session set.
# ---------------------------------------------------------------------------


def test_monza_is_a_conventional_weekend(monza_weekend):
    assert monza_weekend.pre_race.is_sprint_weekend is False


def test_austria_is_a_sprint_weekend(austria_weekend):
    assert austria_weekend.pre_race.is_sprint_weekend is True


def test_is_sprint_weekend_detects_a_sprint_from_session_names():
    assert _is_sprint_weekend(
        {"Practice 1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"}
    )
    assert not _is_sprint_weekend(
        {"Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"}
    )


# ---------------------------------------------------------------------------
# Session set: every pre-race session is present, in canonical order.
# ---------------------------------------------------------------------------


def test_conventional_weekend_has_fp1_fp2_fp3_q(monza_weekend):
    names = tuple(s.name for s in monza_weekend.pre_race.sessions)
    assert names == ("FP1", "FP2", "FP3", "Q")


def test_sprint_weekend_has_fp1_sq_s_q(austria_weekend):
    names = tuple(s.name for s in austria_weekend.pre_race.sessions)
    # FP1 → Sprint Qualifying → Sprint → Qualifying — the predictor
    # reads this order (chronological on a sprint weekend).
    assert names == ("FP1", "SQ", "S", "Q")


def test_race_session_is_never_in_pre_race(monza_weekend):
    for session in monza_weekend.pre_race.sessions:
        assert session.name != "R"
        assert session.name != "Race"


def test_race_outcome_is_empty_in_ticket_21_scope(monza_weekend):
    """Ticket 22 fills the race side; ticket 21 leaves it empty."""
    assert monza_weekend.race.stints == ()
    assert monza_weekend.race.neutralisations == ()
    assert monza_weekend.race.finishing_status == {}


def test_pit_loss_is_a_placeholder_in_ticket_21_scope(monza_weekend):
    """Pit Loss is ticket 22; keep the field typed but at a zero
    placeholder so the shape mirrors FastF1 loader exactly."""
    assert monza_weekend.pre_race.pit_loss == 0.0
    assert monza_weekend.pre_race.pit_loss_seasons == ()
    assert monza_weekend.pre_race.estimated_pit_loss is False


# ---------------------------------------------------------------------------
# Teams: from the race's drivers + the quali session's starting grid.
# ---------------------------------------------------------------------------


def test_teams_come_from_starting_grid_x_drivers(monza_weekend):
    teams = monza_weekend.pre_race.teams
    assert teams == {"VER": "Red Bull Racing", "LEC": "Ferrari"}


def test_sprint_weekend_teams_use_the_main_qualifying_starting_grid(austria_weekend):
    # Austria 2024: VER and NOR on the main race's starting grid, which
    # is attached to session Qualifying (session_key=9551), not Sprint
    # Qualifying.
    teams = austria_weekend.pre_race.teams
    assert teams == {"VER": "Red Bull Racing", "NOR": "McLaren"}


# ---------------------------------------------------------------------------
# Per-lap derivations: ticket 21's main responsibility.
# ---------------------------------------------------------------------------


def _session(weekend: RaceWeekend, name: str) -> Session:
    for s in weekend.pre_race.sessions:
        if s.name == name:
            return s
    raise AssertionError(f"no session {name!r} in weekend")


def _laps(weekend: RaceWeekend, name: str, driver: str) -> list:
    return [lap for lap in _session(weekend, name).laps if lap.driver == driver]


def test_every_lap_carries_the_required_fields(monza_weekend):
    laps = _laps(monza_weekend, "FP1", "VER")
    assert laps, "fixture must produce at least one lap for VER"
    for lap in laps:
        # The weekend description's contract on `Lap`.
        assert isinstance(lap.lap_number, int)
        assert isinstance(lap.lap_time, float)
        assert isinstance(lap.compound, Compound)
        assert isinstance(lap.tyre_age, int)
        assert isinstance(lap.new_when_fitted, bool)
        assert isinstance(lap.pit_in, bool)
        assert isinstance(lap.pit_out, bool)
        assert lap.tyre_set  # non-empty id


def test_lap_time_is_lap_duration_in_seconds(monza_weekend):
    # Monza FP1 VER lap 2 has lap_duration=85.5 in the fixture.
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    assert laps[2].lap_time == pytest.approx(85.5)


def test_compound_comes_from_the_stint_whose_range_covers_the_lap(monza_weekend):
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    # VER stint 1 is SOFT laps 1-4; stint 2 is SOFT laps 5-6.
    assert laps[2].compound is Compound.SOFT
    assert laps[6].compound is Compound.SOFT


def test_laps_with_missing_lap_duration_are_skipped(monza_weekend):
    """The fixture gives VER FP1 lap 1 and lap 4 lap_duration=null."""
    numbers = {lap.lap_number for lap in _laps(monza_weekend, "FP1", "VER")}
    assert 1 not in numbers
    assert 4 not in numbers
    # And the surrounding laps are kept.
    assert 2 in numbers
    assert 3 in numbers


def test_laps_outside_every_stint_range_are_skipped(monza_weekend):
    """Fixture LEC FP1 lap 99 is deliberately outside the stint range
    (stint 1 covers laps 1-2). Ticket 21 ambiguity decision: a lap with
    no matching stint is skipped, not inserted with an unknown compound.
    """
    numbers = {lap.lap_number for lap in _laps(monza_weekend, "FP1", "LEC")}
    assert 99 not in numbers
    assert 2 in numbers


# -- tyre_age and new_when_fitted ------------------------------------------


def test_tyre_age_starts_at_one_for_a_new_sets_first_lap(monza_weekend):
    """VER FP1 stint 1 is SOFT laps 1-4 with tyre_age_at_start=0; lap 2
    (the first lap of this stint that has a time) must be age 2 by the
    recipe (lap - lap_start + 1 + 0 = 2 - 1 + 1 + 0)."""
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    assert laps[2].tyre_age == 2
    assert laps[3].tyre_age == 3


def test_tyre_age_includes_tyre_age_at_start_for_a_used_set(austria_weekend):
    """Austria Sprint VER stint 1 is MEDIUM laps 1-24 with
    tyre_age_at_start=5 (used set from Sprint Qualifying). Lap 1 must
    be age 1 + 5 = 6."""
    laps = {lap.lap_number: lap for lap in _laps(austria_weekend, "S", "VER")}
    assert laps[1].tyre_age == 6
    assert laps[2].tyre_age == 7


def test_new_when_fitted_is_true_when_tyre_age_at_start_is_zero(monza_weekend):
    laps = _laps(monza_weekend, "FP1", "VER")
    stint_one = [lap for lap in laps if 1 <= lap.lap_number <= 4]
    assert stint_one, "fixture should produce at least one stint-1 lap"
    for lap in stint_one:
        assert lap.new_when_fitted is True


def test_new_when_fitted_is_false_when_tyre_age_at_start_is_positive(austria_weekend):
    """Used-set stint (Austria Sprint VER MEDIUM, tyre_age_at_start=5)."""
    laps = _laps(austria_weekend, "S", "VER")
    assert laps, "fixture must have Sprint laps for VER"
    for lap in laps:
        assert lap.new_when_fitted is False


# -- pit_in and pit_out -----------------------------------------------------


def test_pit_in_is_flagged_from_pit_endpoint_lap_numbers(monza_weekend):
    """Fixture has a /v1/pit row for VER FP1 lap 4 (and lap 4's
    lap_duration is null in the fixture, so this test can't look at
    the pit-in lap itself — instead check that no non-pit lap gets
    the flag)."""
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    assert laps[2].pit_in is False
    assert laps[3].pit_in is False
    assert laps[6].pit_in is False


def test_pit_out_comes_from_is_pit_out_lap_field(monza_weekend):
    """VER FP1 lap 5 has is_pit_out_lap=True; lap 6 is False."""
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    assert laps[5].pit_out is True
    assert laps[6].pit_out is False


# -- tyre_set id matches the FastF1 loader's recipe -------------------------


def test_tyre_set_id_follows_the_fastf1_loaders_pattern(monza_weekend):
    """fastf1_loader builds "{driver}-{session}-stint{N}-{compound}";
    openf1_loader must match so a cross-source history uses the same
    uniqueness key per stint."""
    laps = {lap.lap_number: lap for lap in _laps(monza_weekend, "FP1", "VER")}
    assert laps[2].tyre_set == "VER-FP1-stint1-S"
    # Stint 2 (laps 5-6) must get its own id so a session-level
    # dedupe counts two stints, not one.
    assert laps[5].tyre_set == "VER-FP1-stint2-S"


# -- neutralised flag (pre-race scope) --------------------------------------


def test_neutralised_is_false_for_pre_race_sessions(monza_weekend):
    """OpenF1 has no per-lap TrackStatus for pre-race sessions. Ticket
    21 ambiguity decision: ``neutralised`` stays False on every pre-race
    lap. The (rare) red-flag practice case diverges from the FastF1
    loader and is listed in the ticket's limitations."""
    for session in monza_weekend.pre_race.sessions:
        for lap in session.laps:
            assert lap.neutralised is False


# ---------------------------------------------------------------------------
# race_laps: from the winner's /v1/session_result row.
# ---------------------------------------------------------------------------


def test_race_laps_comes_from_session_result_winners_lap_count(monza_weekend):
    # Monza 2024 winner (LEC) completed 53 laps in the fixture.
    assert monza_weekend.pre_race.race_laps == 53


def test_race_laps_uses_the_maximum_lap_count_across_the_result(austria_weekend):
    """Austria fixture has NOR as a DNF with number_of_laps=64; the
    winner's row has number_of_laps=71. race_laps must be 71."""
    assert austria_weekend.pre_race.race_laps == 71


# ---------------------------------------------------------------------------
# Round number helper (ticket 23 will call it; here we pin the derivation).
# ---------------------------------------------------------------------------


def test_round_number_is_the_target_meetings_index_in_date_order(monza_fixture):
    meetings = monza_fixture["meetings?year=2024"]
    monza = next(m for m in meetings if m["location"] == "Monza")
    bahrain = next(m for m in meetings if m["location"] == "Sakhir" and "Grand Prix" in m["meeting_name"])
    austria = next(m for m in meetings if m["location"] == "Spielberg")

    # Fixture ordering: Bahrain (R1) → Austria (R2) → Monza (R3); the
    # "Pre-Season Testing" row is dropped by _is_race_meeting.
    assert _round_number(meetings, bahrain) == 1
    assert _round_number(meetings, austria) == 2
    assert _round_number(meetings, monza) == 3
