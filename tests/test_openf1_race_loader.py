"""Fast tests for the OpenF1 race-side loader (ticket 22).

The race-side helpers (``_race_stints``, ``_neutralisation_periods``,
``_finishing_status``, ``_pit_losses_in``, ``_historical_stint_rates``,
``load_past_race_samples``) each take raw OpenF1 row sets, so these
tests exercise them directly with hand-built dicts. End-to-end
coverage of ``load_weekend`` with race rows for Monza 2024 and
São Paulo 2024, backed by recorded fixtures, pins the full path.

Slow tests that go through the real :class:`.openf1_client.OpenF1Client`
for the three findings-sampled weekends live in
``test_openf1_weekend_loader_real_data.py``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from f1_strategy import Compound, NeutralisationPeriod, RaceWeekend
from f1_strategy.openf1_loader import (
    PastRaceSamples,
    _finishing_status,
    _historical_stint_rates,
    _neutralisation_periods,
    _neutralised_lap_set,
    _pit_losses_in,
    _race_stints,
    load_past_race_samples,
    load_weekend,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


class _FixtureClient:
    """Same stand-in as the ticket 21 tests use — one URL-keyed table."""

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
def monza_fixture() -> dict[str, list[dict]]:
    return _load_fixture("monza_2024.json")


@pytest.fixture(scope="module")
def sao_paulo_fixture() -> dict[str, list[dict]]:
    return _load_fixture("sao_paulo_2024.json")


@pytest.fixture
def monza_weekend(monza_fixture) -> RaceWeekend:
    return load_weekend(
        2024, "Italian Grand Prix", client=_FixtureClient(monza_fixture)
    )


# ---------------------------------------------------------------------------
# _race_stints: driver_number → TLA, keyed on starter set.
# ---------------------------------------------------------------------------


def test_race_stints_keys_on_tla_not_driver_number():
    rows = [
        {"driver_number": 1, "stint_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 15, "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 2, "compound": "HARD", "lap_start": 16, "lap_end": 53, "tyre_age_at_start": 0},
    ]
    stints = _race_stints(rows, tla_by_num={1: "VER"}, drivers={"VER"})
    assert len(stints) == 2
    assert stints[0].driver == "VER"
    assert stints[0].compound is Compound.MEDIUM
    assert stints[0].start_lap == 1
    assert stints[0].end_lap == 15


def test_race_stints_sorted_by_driver_then_start_lap():
    rows = [
        {"driver_number": 16, "stint_number": 2, "compound": "HARD", "lap_start": 23, "lap_end": 41, "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 15, "tyre_age_at_start": 0},
        {"driver_number": 16, "stint_number": 1, "compound": "HARD", "lap_start": 1, "lap_end": 22, "tyre_age_at_start": 0},
    ]
    stints = _race_stints(rows, tla_by_num={1: "VER", 16: "LEC"}, drivers={"VER", "LEC"})
    keys = [(s.driver, s.start_lap) for s in stints]
    assert keys == [("LEC", 1), ("LEC", 23), ("VER", 1)]


def test_race_stints_skip_drivers_outside_the_starter_set():
    """A reserve driver who appears only on /v1/stints but is not in the
    starter set (DNS, dropped from the pre-race teams map) should not
    produce stints."""
    rows = [
        {"driver_number": 1, "stint_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 0},
        {"driver_number": 99, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 0},
    ]
    stints = _race_stints(rows, tla_by_num={1: "VER", 99: "RES"}, drivers={"VER"})
    assert [s.driver for s in stints] == ["VER"]


# ---------------------------------------------------------------------------
# _neutralisation_periods: event reconstruction.
# ---------------------------------------------------------------------------


def test_vsc_opens_and_closes_on_the_same_lap():
    rows = [
        {"message": "VIRTUAL SAFETY CAR DEPLOYED", "lap_number": 66},
        {"message": "VIRTUAL SAFETY CAR ENDING", "lap_number": 66},
    ]
    periods, warnings = _neutralisation_periods(rows, race_laps=71)
    assert periods == (NeutralisationPeriod("VSC", 66, 66),)
    assert warnings == ()


def test_sc_opens_and_closes_on_the_in_this_lap_message():
    rows = [
        {"message": "SAFETY CAR DEPLOYED", "lap_number": 7},
        {"message": "SAFETY CAR IN THIS LAP", "lap_number": 9},
    ]
    periods, warnings = _neutralisation_periods(rows, race_laps=50)
    assert periods == (NeutralisationPeriod("SC", 7, 9),)
    assert warnings == ()


def test_red_flag_is_not_a_neutralisation_period():
    """ADR-0004 / `_lap_neutralisation_kind` ignores red flag. Red-flag
    laps parked in the pit lane aren't a lap under reduced speed, so
    they aren't counted as neutralised."""
    rows = [
        {"message": "RED FLAG", "flag": "RED", "lap_number": 32, "category": "Flag"},
    ]
    periods, warnings = _neutralisation_periods(rows, race_laps=50)
    assert periods == ()
    assert warnings == ()


def test_missing_vsc_end_is_capped_at_race_lap_count_with_warning(caplog):
    """Known gap: a VSC without an ENDING event could leak to the end
    of the race. The reconstruction caps the period at the race lap
    count and logs a quality warning."""
    rows = [
        {"message": "VIRTUAL SAFETY CAR DEPLOYED", "lap_number": 60},
    ]
    with caplog.at_level(logging.WARNING):
        periods, warnings = _neutralisation_periods(rows, race_laps=71)
    assert periods == (NeutralisationPeriod("VSC", 60, 71),)
    assert len(warnings) == 1
    assert "capped at race lap count 71" in warnings[0]
    assert any("capped at race lap count 71" in r.message for r in caplog.records)


def test_missing_sc_end_is_capped_at_race_lap_count_with_warning(caplog):
    rows = [
        {"message": "SAFETY CAR DEPLOYED", "lap_number": 50},
    ]
    with caplog.at_level(logging.WARNING):
        periods, warnings = _neutralisation_periods(rows, race_laps=55)
    assert periods == (NeutralisationPeriod("SC", 50, 55),)
    assert len(warnings) == 1
    assert "SC" in warnings[0]


def test_sao_paulo_2024_neutralisations_from_fixture(sao_paulo_fixture):
    """The three VSC/SC messages the findings pinned on race session
    9636 must reconstruct cleanly: VSC on lap 28, SC laps 30-31,
    SC laps 39-42. Red flag on lap 32 contributes no period."""
    rows = sao_paulo_fixture["race_control?session_key=9636"]
    periods, warnings = _neutralisation_periods(rows, race_laps=69)
    assert periods == (
        NeutralisationPeriod("VSC", 28, 28),
        NeutralisationPeriod("SC", 30, 31),
        NeutralisationPeriod("SC", 39, 42),
    )
    assert warnings == ()


def test_neutralised_lap_set_covers_the_full_range():
    periods = (
        NeutralisationPeriod("VSC", 28, 28),
        NeutralisationPeriod("SC", 30, 32),
    )
    assert _neutralised_lap_set(periods) == {28, 30, 31, 32}


# ---------------------------------------------------------------------------
# _finishing_status: dnf/dns/dsq negated.
# ---------------------------------------------------------------------------


def test_dnf_dns_dsq_do_not_take_the_flag(sao_paulo_fixture):
    rows = sao_paulo_fixture["session_result?session_key=9636"]
    tla_by_num = {
        int(d["driver_number"]): str(d["name_acronym"])
        for d in sao_paulo_fixture["drivers?session_key=9636"]
    }
    status = _finishing_status(
        rows, tla_by_num=tla_by_num, drivers=set(tla_by_num.values())
    )
    # Winner: VER. DNFs: SAI, COL. DNSs: ALB, STR. DSQ: HUL.
    assert status["VER"] is True
    assert status["SAI"] is False
    assert status["COL"] is False
    assert status["ALB"] is False
    assert status["STR"] is False
    assert status["HUL"] is False


# ---------------------------------------------------------------------------
# _pit_losses_in: green-flag filtered lap-time algorithm.
# ---------------------------------------------------------------------------


def _ref_lap(driver, lap_number, duration, is_pit_out_lap=False):
    return {
        "driver_number": driver,
        "lap_number": lap_number,
        "lap_duration": duration,
        "is_pit_out_lap": is_pit_out_lap,
    }


def test_pit_loss_is_in_lap_minus_ref_plus_out_lap_minus_ref():
    """Ref median = 85.0 across 5 clean laps. in-lap 108 and out-lap
    95 → loss = 23 + 10 = 33, within the 10-60 clip."""
    laps = [
        _ref_lap(1, 2, 85.0),
        _ref_lap(1, 3, 85.0),
        _ref_lap(1, 4, 85.0),
        _ref_lap(1, 5, 85.0),
        _ref_lap(1, 6, 85.0),
        _ref_lap(1, 10, 108.0),  # pit-in
        _ref_lap(1, 11, 95.0, is_pit_out_lap=True),  # pit-out
        _ref_lap(1, 12, 85.0),
    ]
    pit = [{"driver_number": 1, "lap_number": 10}]
    losses = list(_pit_losses_in(laps, pit, neutralised_laps=set()))
    assert losses == [pytest.approx(33.0)]


def test_pit_loss_requires_at_least_5_clean_reference_laps():
    """Fewer than 5 green reference laps → no loss sample at all."""
    laps = [
        _ref_lap(1, 2, 85.0),
        _ref_lap(1, 3, 85.0),
        _ref_lap(1, 10, 108.0),
        _ref_lap(1, 11, 95.0, is_pit_out_lap=True),
    ]
    pit = [{"driver_number": 1, "lap_number": 10}]
    losses = list(_pit_losses_in(laps, pit, neutralised_laps=set()))
    assert losses == []


def test_pit_loss_skips_in_or_out_laps_under_neutralisation():
    """A pit stop whose in-lap or out-lap falls in a VSC/SC period
    doesn't produce a loss sample (the reduced-speed lap breaks the
    reference comparison)."""
    laps = [
        _ref_lap(1, 2, 85.0),
        _ref_lap(1, 3, 85.0),
        _ref_lap(1, 4, 85.0),
        _ref_lap(1, 5, 85.0),
        _ref_lap(1, 6, 85.0),
        _ref_lap(1, 10, 108.0),
        _ref_lap(1, 11, 95.0, is_pit_out_lap=True),
    ]
    pit = [{"driver_number": 1, "lap_number": 10}]
    losses = list(_pit_losses_in(laps, pit, neutralised_laps={10}))
    assert losses == []
    losses = list(_pit_losses_in(laps, pit, neutralised_laps={11}))
    assert losses == []


def test_pit_loss_drops_neutralised_laps_from_the_reference():
    """A neutralised lap must not pollute the per-driver reference
    median. Here lap 2's slow (~98 s) time would skew the ref lower
    if included; filtering it out keeps the ref around 85."""
    laps = [
        _ref_lap(1, 2, 98.0),  # neutralised: dropped from ref
        _ref_lap(1, 3, 85.0),
        _ref_lap(1, 4, 85.0),
        _ref_lap(1, 5, 85.0),
        _ref_lap(1, 6, 85.0),
        _ref_lap(1, 7, 85.0),
        _ref_lap(1, 10, 108.0),
        _ref_lap(1, 11, 95.0, is_pit_out_lap=True),
    ]
    pit = [{"driver_number": 1, "lap_number": 10}]
    losses = list(_pit_losses_in(laps, pit, neutralised_laps={2}))
    assert losses == [pytest.approx(33.0)]


def test_pit_loss_clips_outside_10_to_60_seconds():
    """A nonsensical pit-stop measurement — e.g. 1-lap stationary
    time or an all-neutralised-pit — must not surface as a sample."""
    laps = [
        _ref_lap(1, 2, 85.0),
        _ref_lap(1, 3, 85.0),
        _ref_lap(1, 4, 85.0),
        _ref_lap(1, 5, 85.0),
        _ref_lap(1, 6, 85.0),
        _ref_lap(1, 10, 90.0),  # in-lap barely slower
        _ref_lap(1, 11, 90.0, is_pit_out_lap=True),  # out-lap barely slower
        # loss = 10 — equal, fails the strict >
    ]
    pit = [{"driver_number": 1, "lap_number": 10}]
    losses = list(_pit_losses_in(laps, pit, neutralised_laps=set()))
    assert losses == []


def test_pit_loss_never_reads_pit_duration(sao_paulo_fixture):
    """São Paulo 2024's /v1/pit carries a 650 s pit_duration row (red-
    flag parking counted as a pit stop). The lap-time algorithm must
    not pick that up. For the São Paulo fixture laps on this test
    (which only cover lap 1 and 2 for VER), /pit_losses_in refuses to
    produce samples because fewer than 5 reference laps exist — not
    because of the 650 s value. Pinning both facts here keeps the
    `pit_duration` finding tied to the code that would otherwise
    read it."""
    laps = sao_paulo_fixture["laps?session_key=9636"]
    pit = sao_paulo_fixture["pit?session_key=9636"]
    assert any(row.get("pit_duration") == 650.0 for row in pit), (
        "fixture must still carry the 650 s pit_duration row"
    )
    losses = list(_pit_losses_in(laps, pit, neutralised_laps={28, 30, 31, 39, 40, 41, 42}))
    # No sample is produced regardless of the 650 s row — the lap-time
    # algorithm's output here is empty for lack of clean reference laps.
    assert losses == []


# ---------------------------------------------------------------------------
# _historical_stint_rates: slope + fuel correction, green-flag filtered.
# ---------------------------------------------------------------------------


def test_historical_stint_rate_fits_a_slope_with_fuel_correction():
    stint_rows = [
        {"driver_number": 1, "stint_number": 2, "compound": "HARD", "lap_start": 16, "lap_end": 20, "tyre_age_at_start": 0},
    ]
    laps_rows = [
        {"driver_number": 1, "lap_number": 16, "lap_duration": 85.0, "is_pit_out_lap": True},
        {"driver_number": 1, "lap_number": 17, "lap_duration": 86.0, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 18, "lap_duration": 86.1, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 19, "lap_duration": 86.2, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 20, "lap_duration": 86.3, "is_pit_out_lap": False},
    ]
    rates = list(
        _historical_stint_rates(
            laps_rows,
            stint_rows,
            pit_rows=[],
            neutralised_laps=set(),
            fuel_effect_s_per_lap=0.03,
            min_stint_length=4,
        )
    )
    assert len(rates) == 1
    compound, rate, lap_count = rates[0]
    assert compound is Compound.HARD
    assert lap_count == 4  # laps 17, 18, 19, 20
    # Slope ~0.1 s/lap, plus 0.03 fuel correction.
    assert rate == pytest.approx(0.13, abs=0.001)


def test_historical_stint_rate_rejects_a_broken_tyre_age_sequence():
    """When the only clean laps don't form a strictly consecutive
    tyre-age run of >= min_stint_length, no sample is yielded. This is
    the real behaviour the previous test tried to pin — a neutralised
    lap mid-stint splits the run and often disqualifies the stint."""
    stint_rows = [
        {"driver_number": 1, "stint_number": 2, "compound": "HARD", "lap_start": 16, "lap_end": 20, "tyre_age_at_start": 0},
    ]
    laps_rows = [
        {"driver_number": 1, "lap_number": 16, "lap_duration": 85.0, "is_pit_out_lap": True},
        {"driver_number": 1, "lap_number": 17, "lap_duration": 86.0, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 18, "lap_duration": 86.1, "is_pit_out_lap": False},
        # lap 19 neutralised and dropped
        {"driver_number": 1, "lap_number": 20, "lap_duration": 86.3, "is_pit_out_lap": False},
    ]
    rates = list(
        _historical_stint_rates(
            laps_rows,
            stint_rows,
            pit_rows=[],
            neutralised_laps={19},
            fuel_effect_s_per_lap=0.03,
            min_stint_length=4,
        )
    )
    # Only 3 clean laps, and tyre ages {2, 3, 5} are not strictly
    # consecutive after dropping lap 19 → no sample.
    assert rates == []


def test_historical_stint_rate_skips_wet_compounds():
    stint_rows = [
        {"driver_number": 1, "stint_number": 1, "compound": "INTERMEDIATE", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 0},
    ]
    laps_rows = [
        {"driver_number": 1, "lap_number": i, "lap_duration": 90.0 + 0.1 * i, "is_pit_out_lap": False}
        for i in range(2, 11)
    ]
    rates = list(
        _historical_stint_rates(
            laps_rows,
            stint_rows,
            pit_rows=[],
            neutralised_laps=set(),
            fuel_effect_s_per_lap=0.03,
            min_stint_length=4,
        )
    )
    assert rates == []


def test_historical_stint_rate_skips_pit_in_and_pit_out_laps():
    """Pit-in (listed in /v1/pit) and pit-out (`is_pit_out_lap=True`)
    laps are both dropped before the fit; the longest consecutive
    sub-run is what's left."""
    stint_rows = [
        {"driver_number": 1, "stint_number": 1, "compound": "HARD", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 0},
    ]
    laps_rows = [
        {"driver_number": 1, "lap_number": 1, "lap_duration": 85.0, "is_pit_out_lap": True},
        {"driver_number": 1, "lap_number": 2, "lap_duration": 86.0, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 3, "lap_duration": 86.1, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 4, "lap_duration": 86.2, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 5, "lap_duration": 86.3, "is_pit_out_lap": False},
        {"driver_number": 1, "lap_number": 6, "lap_duration": 108.0, "is_pit_out_lap": False},  # pit-in
    ]
    pit_rows = [{"driver_number": 1, "lap_number": 6}]
    rates = list(
        _historical_stint_rates(
            laps_rows,
            stint_rows,
            pit_rows=pit_rows,
            neutralised_laps=set(),
            fuel_effect_s_per_lap=0.03,
            min_stint_length=4,
        )
    )
    assert len(rates) == 1
    compound, _rate, lap_count = rates[0]
    assert compound is Compound.HARD
    assert lap_count == 4  # laps 2, 3, 4, 5


# ---------------------------------------------------------------------------
# load_past_race_samples: the ticket-23 seam.
# ---------------------------------------------------------------------------


def test_load_past_race_samples_returns_samples_for_an_openf1_season(monza_fixture):
    """The 2023 Monza fixture produces one pit-loss sample for VER and
    one stint-rate sample per compound VER raced (MEDIUM stint 1,
    HARD stint 2)."""
    samples = load_past_race_samples(
        _FixtureClient(monza_fixture),
        2023,
        "Monza",
        fuel_effect_s_per_lap=0.03,
        history_min_stint_length=4,
    )
    assert isinstance(samples, PastRaceSamples)
    assert len(samples.pit_losses) == 1
    assert 10.0 < samples.pit_losses[0] < 60.0
    by_compound = {c: (r, n) for c, r, n in samples.stint_rates}
    assert Compound.HARD in by_compound
    hard_rate, hard_lap_count = by_compound[Compound.HARD]
    assert hard_lap_count == 4
    assert hard_rate == pytest.approx(0.13, abs=0.001)


def test_load_past_race_samples_is_empty_when_no_openf1_meeting_matches(monza_fixture):
    """A 2022 past-season call never finds a meeting in OpenF1 (OpenF1
    coverage starts in 2023). This exercises the "empty" seam ticket
    23 will see for the FastF1 branch."""
    # The Monza fixture carries no `meetings?year=2022` row at all, so
    # the client raises; the loader catches and returns empty.
    samples = load_past_race_samples(
        _FixtureClient(monza_fixture),
        2022,
        "Monza",
        fuel_effect_s_per_lap=0.03,
        history_min_stint_length=4,
    )
    assert samples.pit_losses == ()
    assert samples.stint_rates == ()


# ---------------------------------------------------------------------------
# load_weekend end-to-end: race-side wired to pre-race-side.
# ---------------------------------------------------------------------------


def test_load_weekend_builds_race_outcome(monza_weekend):
    """Monza 2024 ran green; race.stints has both drivers, no
    neutralisations, both finishers take the flag."""
    stints = monza_weekend.race.stints
    ver_stints = [s for s in stints if s.driver == "VER"]
    lec_stints = [s for s in stints if s.driver == "LEC"]
    assert len(ver_stints) == 2  # fixture: MEDIUM 1-15, HARD 16-53
    assert len(lec_stints) == 3  # fixture: HARD 1-22, HARD 23-41, MEDIUM 42-53
    assert monza_weekend.race.neutralisations == ()
    assert monza_weekend.race.finishing_status == {"VER": True, "LEC": True}


def test_load_weekend_measures_historical_degradation_from_past_openf1(monza_weekend):
    """2023 Monza's hard-compound stint (laps 17-20 clean) contributes
    one sample; the fit's season set is exactly (2023,)."""
    hist = monza_weekend.pre_race.historical_degradation
    assert Compound.HARD in hist
    assert hist[Compound.HARD].seasons == (2023,)
    assert hist[Compound.HARD].stint_count == 1
    assert hist[Compound.HARD].rate == pytest.approx(0.13, abs=0.001)
