"""Fast tests for ticket 50: OpenF1 weekends start every driver on the full
Tyre Allocation.

OpenF1's ``tyre_age_at_start`` is often 0 on a stint that continues or
re-fits a set already used in practice or qualifying, so counting those as
new sets runs drivers out of Compounds they still had (ADR-0002 amendment,
2026-10-27). OpenF1 doesn't carry F1's "new" flag, so a weekend loaded from
it says set usage is unknown and Remaining Sets is the full allocation.
FastF1 weekends (2022) keep the new-only count.

Everything goes through ``data.load_weekend`` + ``predict()``: OpenF1 from
the recorded Monza 2024 fixture, FastF1 from the scripted fakes ticket 40's
tests use. No network.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from f1_strategy import data, fastf1_loader
from f1_strategy.degradation import team_degradation
from f1_strategy.openf1_loader import PastRaceSamples
from f1_strategy.predictor import RemainingSetsRule, predict
from f1_strategy.report import format_table
from f1_strategy.scorer import compare
from f1_strategy.settings import Settings
from f1_strategy.weekend import Compound, Lap

from test_data_router import _FixtureClient
from test_fastf1_fetch_errors import _FakeFastF1

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"

CONVENTIONAL = {Compound.SOFT: 8, Compound.MEDIUM: 3, Compound.HARD: 2}
ALTERNATIVE = {Compound.SOFT: 4, Compound.MEDIUM: 4, Compound.HARD: 3}


@pytest.fixture
def monza() -> dict[str, list[dict]]:
    with (FIXTURES / "monza_2024.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def _fastf1_2022_history(season, event, **kwargs) -> PastRaceSamples:
    return PastRaceSamples(
        pit_losses=(28.0, 29.0, 30.0),
        stint_rates=(
            (Compound.SOFT, 0.12, 15),
            (Compound.MEDIUM, 0.08, 18),
            (Compound.HARD, 0.05, 20),
        ),
    )


def _with_a_long_run(fixture: dict) -> dict:
    """The recording has no Long Run, and ``predict()`` needs one for its
    base lap time: give LEC a 12-lap Medium run in FP2."""
    fixture = copy.deepcopy(fixture)
    fixture["stints?session_key=9582"] = fixture["stints?session_key=9582"] + [
        {
            "driver_number": 16,
            "stint_number": 1,
            "compound": "MEDIUM",
            "lap_start": 1,
            "lap_end": 12,
            "tyre_age_at_start": 0,
        }
    ]
    fixture["laps?session_key=9582"] = fixture["laps?session_key=9582"] + [
        {
            "driver_number": 16,
            "lap_number": n,
            "lap_duration": 95.0 if n == 1 else 86.0 + 0.08 * n,
            "is_pit_out_lap": n == 1,
        }
        for n in range(1, 13)
    ]
    return fixture


def _load_openf1(fixture: dict, season: int, event: str):
    return data.load_weekend(
        season,
        event,
        openf1_client=_FixtureClient(_with_a_long_run(fixture)),
        fastf1_load_past_race_samples=_fastf1_2022_history,
    )


def _over_counted(fixture: dict) -> dict:
    """VER's FP1 rewritten so OpenF1 claims more new sets than he has: five
    back-to-back Medium stints and three Hard stints, every one
    ``tyre_age_at_start: 0`` (the 2024 Singapore pattern in the ticket)."""
    fixture = copy.deepcopy(fixture)
    stints = [s for s in fixture["stints?session_key=9581"] if s["driver_number"] != 1]
    laps = [l for l in fixture["laps?session_key=9581"] if l["driver_number"] != 1]
    compounds = ["MEDIUM"] * 5 + ["HARD"] * 3
    for n, compound in enumerate(compounds, start=1):
        first = 2 * n - 1
        stints.append(
            {
                "driver_number": 1,
                "stint_number": n,
                "compound": compound,
                "lap_start": first,
                "lap_end": first + 1,
                "tyre_age_at_start": 0,
            }
        )
        laps += [
            {"driver_number": 1, "lap_number": first, "lap_duration": 84.0, "is_pit_out_lap": True},
            {"driver_number": 1, "lap_number": first + 1, "lap_duration": 82.0, "is_pit_out_lap": False},
        ]
    fixture["stints?session_key=9581"] = stints
    fixture["laps?session_key=9581"] = laps
    return fixture


def _relabelled_2023(fixture: dict, meeting_name: str, location: str) -> dict:
    """The Monza 2024 recording served as a 2023 weekend under another name,
    so the Alternative Tyre Allocation lookup can be exercised without a new
    recording. Its history comes from the 2022 FastF1 fake only."""
    fixture = copy.deepcopy(fixture)
    meeting = dict(fixture["meetings?year=2024"][-1])
    meeting.update(
        meeting_name=meeting_name,
        location=location,
        date_start="2023-09-01T11:30:00+00:00",
    )
    fixture["meetings?year=2023"] = [meeting]
    return fixture


# ---------------------------------------------------------------------------
# OpenF1: full allocation, whatever tyre_age_at_start says.
# ---------------------------------------------------------------------------


def test_openf1_weekend_says_set_usage_is_unknown(monza) -> None:
    weekend = _load_openf1(monza, 2024, "Italian Grand Prix")
    assert weekend.pre_race.set_usage_known is False


def test_openf1_over_counted_new_sets_still_get_the_full_allocation(monza) -> None:
    weekend = _load_openf1(_over_counted(monza), 2024, "Italian Grand Prix")
    # The loader still reads OpenF1's age-0 stints as new (criterion 5)...
    ver_fp1 = [
        lap for lap in weekend.pre_race.sessions[0].laps if lap.driver == "VER"
    ]
    assert len({lap.tyre_set for lap in ver_fp1 if lap.new_when_fitted}) == 8

    predictions = predict(weekend)

    # ...but Remaining Sets ignores it: every driver gets the full allocation.
    for driver in ("VER", "LEC"):
        assert predictions[driver].remaining_sets == CONVENTIONAL
        assert predictions[driver].remaining_sets_rule is RemainingSetsRule.FULL_ALLOCATION
    # A one-stop M → H is a Candidate, which the new-only count (M=0, H=0)
    # would have ruled out.
    assert any(
        c.strategy.compounds == (Compound.MEDIUM, Compound.HARD)
        for c in predictions["VER"].candidates
    )


def test_the_single_race_report_labels_a_full_allocation_prediction(monza) -> None:
    weekend = _load_openf1(_over_counted(monza), 2024, "Italian Grand Prix")
    predictions = predict(weekend)
    table = format_table(predictions, compare(predictions, weekend))
    for line in table.splitlines():
        if line.startswith(("VER", "LEC")):
            assert "[full allocation (set usage unknown)]" in line


def test_full_allocation_does_not_move_degradation(monza) -> None:
    """Long Run classification groups laps by ``tyre_set``; the new field
    only feeds Remaining Sets, so Degradation is the same either way."""
    pre_race = _load_openf1(_over_counted(monza), 2024, "Italian Grand Prix").pre_race
    known = dataclasses.replace(pre_race, set_usage_known=True)
    assert team_degradation(pre_race, Settings()) == team_degradation(known, Settings())


# ---------------------------------------------------------------------------
# Alternative Tyre Allocation, 2023 Hungary and Monza.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "meeting_name, location",
    [("Hungarian Grand Prix", "Budapest"), ("Italian Grand Prix", "Monza")],
)
def test_2023_alternative_tyre_allocation_weekends(monza, meeting_name, location) -> None:
    fixture = _relabelled_2023(monza, meeting_name, location)
    weekend = _load_openf1(fixture, 2023, meeting_name)

    assert weekend.pre_race.tyre_allocation == ALTERNATIVE
    for prediction in predict(weekend).values():
        assert prediction.remaining_sets == ALTERNATIVE


def test_other_2023_weekends_keep_the_regulation_allocation(monza) -> None:
    fixture = _relabelled_2023(monza, "Dutch Grand Prix", "Zandvoort")
    weekend = _load_openf1(fixture, 2023, "Dutch Grand Prix")

    assert weekend.pre_race.tyre_allocation is None
    for prediction in predict(weekend).values():
        assert prediction.remaining_sets == CONVENTIONAL


def test_the_alternative_allocation_was_2023_only(monza) -> None:
    weekend = _load_openf1(monza, 2024, "Italian Grand Prix")
    assert weekend.pre_race.tyre_allocation is None


# ---------------------------------------------------------------------------
# FastF1 (2022): unchanged, new-only with the ADR-0002 fallbacks.
# ---------------------------------------------------------------------------


def _fastf1_lap(n: int, compound: Compound, stint: int, new: bool) -> Lap:
    return Lap(
        driver="VER",
        lap_number=n,
        lap_time=82.0,
        tyre_set=f"VER-FP1-stint{stint}-{compound.value}",
        compound=compound,
        tyre_age=1 if new else 6,
        new_when_fitted=new,
    )


@pytest.fixture
def fastf1_2022(monkeypatch) -> dict[str, tuple[Lap, ...]]:
    """A scripted 2022 FastF1 weekend; tests fill in FP1's laps. FP3 has a
    used-Soft Long Run (``predict()`` needs one) that takes no new set."""
    fake = _FakeFastF1()
    laps_by_session: dict[str, tuple[Lap, ...]] = {
        "FP3": tuple(
            dataclasses.replace(
                _fastf1_lap(n, Compound.SOFT, 1, new=False),
                tyre_set="VER-FP3-stint1-S",
                lap_time=86.0 + 0.08 * n,
                tyre_age=5 + n,
            )
            for n in range(1, 13)
        )
    }
    monkeypatch.setattr(fastf1_loader.fastf1, "get_session", fake.get_session)
    monkeypatch.setattr(fastf1_loader.fastf1, "get_event_schedule", fake.get_event_schedule)
    monkeypatch.setattr(fastf1_loader.fastf1.Cache, "enable_cache", lambda *a, **k: None)
    monkeypatch.setattr(fastf1_loader, "_starters_and_teams", lambda race: {"VER": "Red Bull Racing"})
    monkeypatch.setattr(
        fastf1_loader, "_laps_from", lambda session, name, drivers: laps_by_session.get(name, ())
    )
    monkeypatch.setattr(fastf1_loader, "_race_stints", lambda race, drivers: ())
    monkeypatch.setattr(fastf1_loader, "_neutralisation_periods", lambda race: ())
    monkeypatch.setattr(fastf1_loader, "_finishing_status", lambda race, drivers: {})
    monkeypatch.setattr(fastf1_loader, "_pit_losses_in", lambda race: [22.0])
    monkeypatch.setattr(
        fastf1_loader,
        "_historical_stint_rates",
        lambda race, fuel, min_len: [
            (Compound.SOFT, 0.12, 15),
            (Compound.MEDIUM, 0.08, 18),
            (Compound.HARD, 0.05, 20),
        ],
    )
    return laps_by_session


def _load_2022(tmp_path):
    return data.load_weekend(2022, "Spanish Grand Prix", fastf1_cache_dir=tmp_path)


def test_fastf1_weekend_says_set_usage_is_known(fastf1_2022, tmp_path) -> None:
    assert _load_2022(tmp_path).pre_race.set_usage_known is True


def test_fastf1_weekend_keeps_the_new_only_count(fastf1_2022, tmp_path) -> None:
    fastf1_2022["FP1"] = (
        _fastf1_lap(1, Compound.MEDIUM, 1, new=True),
        _fastf1_lap(2, Compound.HARD, 2, new=True),
        _fastf1_lap(3, Compound.SOFT, 3, new=False),
    )
    ver = predict(_load_2022(tmp_path))["VER"]
    assert ver.remaining_sets_rule is RemainingSetsRule.NEW_ONLY
    assert ver.remaining_sets == {Compound.SOFT: 8, Compound.MEDIUM: 2, Compound.HARD: 1}


def test_fastf1_weekend_still_falls_back_on_used_sets(fastf1_2022, tmp_path) -> None:
    # Every Medium and Hard used new (none left), one used Medium seen.
    fastf1_2022["FP1"] = (
        *(_fastf1_lap(n, Compound.MEDIUM, n, new=True) for n in range(1, 4)),
        *(_fastf1_lap(n, Compound.HARD, n, new=True) for n in range(4, 6)),
        _fastf1_lap(6, Compound.MEDIUM, 6, new=False),
    )
    ver = predict(_load_2022(tmp_path))["VER"]
    assert ver.remaining_sets_rule is RemainingSetsRule.USED_SET_FALLBACK
    assert ver.remaining_sets == {Compound.SOFT: 8, Compound.MEDIUM: 1, Compound.HARD: 0}
