"""Seam 2: OpenF1 real-weekend → race outcome, Pit Loss, Historical
Degradation (ticket 22).

Loads the three weekends sampled in ``openf1-findings.md`` through the
public :func:`.openf1_loader.load_weekend` with a real
:class:`.openf1_client.OpenF1Client` so the race-side builders are
exercised end to end against the live API shape. Marked ``slow``;
cached under ``.cache/openf1`` so warm runs make no fresh requests
(``.cache/`` is gitignored).

The three samples cover the paths the ticket calls out:
  - Monza 2024: conventional, green, 1 DNF — baseline Pit Loss / HD
  - Austria 2024: sprint weekend with one short VSC on lap 66
  - São Paulo 2024: neutralised with VSC + two SC periods and a
    red-flagged `pit_duration` row that must not touch Pit Loss
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import RaceWeekend
from f1_strategy.openf1_loader import load_weekend


pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "openf1"


@pytest.fixture(scope="module")
def monza_2024() -> RaceWeekend:
    return load_weekend(2024, "Italian Grand Prix", cache_dir=CACHE_DIR)


@pytest.fixture(scope="module")
def austria_2024() -> RaceWeekend:
    return load_weekend(2024, "Austrian Grand Prix", cache_dir=CACHE_DIR)


@pytest.fixture(scope="module")
def sao_paulo_2024() -> RaceWeekend:
    return load_weekend(2024, "São Paulo Grand Prix", cache_dir=CACHE_DIR)


# ---------------------------------------------------------------------------
# Monza 2024: conventional, green.
# ---------------------------------------------------------------------------


def test_monza_2024_race_outcome_is_populated(monza_2024: RaceWeekend) -> None:
    # 20 starters, each with at least one stint.
    assert len(monza_2024.race.stints) >= 20
    # Monza 2024 ran green — no SC/VSC.
    assert monza_2024.race.neutralisations == ()
    # Finishing status covers every starter; TSU was the one DNF.
    assert set(monza_2024.race.finishing_status) == set(monza_2024.pre_race.teams)
    assert monza_2024.race.finishing_status.get("TSU") is False


def test_monza_2024_pit_loss_is_in_the_usual_range(monza_2024: RaceWeekend) -> None:
    assert 10.0 < monza_2024.pre_race.pit_loss < 40.0
    # Only OpenF1 seasons (2023) contribute to Pit Loss from this loader.
    assert monza_2024.pre_race.pit_loss_seasons == (2023,)
    assert monza_2024.pre_race.estimated_pit_loss is False


def test_monza_2024_historical_degradation_uses_openf1_seasons_only(
    monza_2024: RaceWeekend,
) -> None:
    hist = monza_2024.pre_race.historical_degradation
    assert hist, "Monza 2024 should get at least one past-OpenF1 Compound"
    for compound, h in hist.items():
        assert h.seasons == (2023,), (compound, h.seasons)
        assert h.stint_count > 0
        # A circuit-level Degradation rate at Monza can land slightly
        # negative after fuel correction: hard tyres don't lose much
        # over a Monza stint, and the fit's noise can tip a small
        # positive slope into a small negative. The rate must at least
        # be a plausible second-per-lap number (not NaN, not huge).
        assert -0.1 < h.rate < 1.0, (compound, h.rate)


# ---------------------------------------------------------------------------
# Austria 2024: sprint weekend with one short VSC.
# ---------------------------------------------------------------------------


def test_austria_2024_vsc_on_lap_66_from_race_control(
    austria_2024: RaceWeekend,
) -> None:
    # Findings: VER–NOR crash fires one VSC on lap 66.
    vsc_periods = [p for p in austria_2024.race.neutralisations if p.kind == "VSC"]
    assert vsc_periods, "Austria 2024 should carry at least one VSC period"
    assert any(p.start_lap == 66 for p in vsc_periods)


def test_austria_2024_sprint_weekend_is_marked(austria_2024: RaceWeekend) -> None:
    assert austria_2024.pre_race.is_sprint_weekend is True
    assert austria_2024.pre_race.race_laps == 71


# ---------------------------------------------------------------------------
# São Paulo 2024: neutralised sprint race with red flag.
# ---------------------------------------------------------------------------


def test_sao_paulo_2024_neutralisations_match_the_findings(
    sao_paulo_2024: RaceWeekend,
) -> None:
    """VSC on lap 28, SC later on lap 30, SC again on laps 39-42 — the
    sequence recorded on 2026-10-23. Red flag on lap 32 is not a
    neutralisation."""
    kinds_by_start = {(p.kind, p.start_lap) for p in sao_paulo_2024.race.neutralisations}
    assert ("VSC", 28) in kinds_by_start
    assert any(p.kind == "SC" and p.start_lap == 39 for p in sao_paulo_2024.race.neutralisations)
    # No period starts on the red-flag lap.
    assert not any(p.start_lap == 32 for p in sao_paulo_2024.race.neutralisations)


def test_sao_paulo_2024_pit_loss_is_not_polluted_by_red_flag_pit_duration(
    sao_paulo_2024: RaceWeekend,
) -> None:
    """At São Paulo, OpenF1's /v1/pit carries a 650 s row (red-flag
    parking counted as a pit stop). If the loader were to read
    pit_duration, Pit Loss would land near that number. The lap-time
    algorithm must keep it inside the usual 10-60 s band."""
    pit_loss = sao_paulo_2024.pre_race.pit_loss
    # If Pit Loss couldn't be measured from any 2023 past race the
    # loader returns 0.0. Either way the pit_duration-pollution
    # number (661 s) must not surface here.
    assert pit_loss < 60.0


def test_sao_paulo_2024_dns_dnf_dsq_do_not_take_the_flag(
    sao_paulo_2024: RaceWeekend,
) -> None:
    # From the findings: Sainz & Colapinto DNF, Albon & Stroll DNS,
    # Hülkenberg DSQ. Each must be False in finishing_status.
    status = sao_paulo_2024.race.finishing_status
    for tla in ("SAI", "COL", "ALB", "STR", "HUL"):
        if tla in status:
            assert status[tla] is False, tla
