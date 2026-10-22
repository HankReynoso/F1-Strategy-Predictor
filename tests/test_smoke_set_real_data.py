"""Slow end-to-end Smoke Set run on real FastF1 data (ticket 08).

Runs `run_backtest` over `SMOKE_SET` through the real `load_weekend`:
Singapore, Monza, Baku, Austin and Jeddah 2024 plus the chosen 2022 race
(Hungarian GP 2022, the conventional green pre-era-Pit-Loss race). The
Backtest Result must have no unexpected Excluded Races, and Singapore 2024
inside it must match its known single-race scores (ticket 08's "Rerun
after ticket 14": top-1 6.5/18, top-3 13.75/18, Stop Window hits 3/20).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import SMOKE_SET, run_backtest
from f1_strategy.fastf1_loader import load_weekend

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastf1"


def _loader(season: int, event: str):
    return load_weekend(season, event, cache_dir=CACHE_DIR)


def test_smoke_set_runs_without_unexpected_excluded_races() -> None:
    result = run_backtest(SMOKE_SET, load=_loader)

    # Every Smoke Set race was picked because it goes through the predict
    # path cleanly, so an Excluded Race is a regression. If this fails,
    # inspect `result.excluded` for the reason category and detail and
    # explain it in the ticket rather than silently relaxing the check.
    assert result.excluded == (), (
        f"Unexpected Excluded Races: {result.excluded}"
    )
    assert len(result.races) == len(SMOKE_SET)


def test_singapore_2024_inside_the_smoke_set_matches_known_scores() -> None:
    result = run_backtest(SMOKE_SET, load=_loader)

    singapore = next(
        r for r in result.races if r.season == 2024 and "Singapore" in r.event
    )
    assert singapore.circuit == "Marina Bay"
    assert singapore.neutralised_race is False
    assert singapore.summary.scoreable_drivers == 18
    # Ticket 08's known Singapore 2024 scores. A mismatch points to a
    # Backtest or loader bug, not a model change.
    assert singapore.summary.top_1_credit == pytest.approx(6.5)
    assert singapore.summary.top_3_credit == pytest.approx(13.75)
    assert singapore.summary.stop_window_hits == 3
    assert singapore.actual_stops == 20


def test_the_2022_smoke_set_race_uses_pre_era_pit_loss() -> None:
    """The 2022 pick exercises the ADR-0004 Pit Loss exception (ticket 03).

    Its Pit Loss must come from pre-era seasons (2018-2021), not from
    the pit lane estimate (ticket 07) and not from same-era history (it
    has none in 2022).
    """
    result = run_backtest(SMOKE_SET, load=_loader)

    [two_thousand_twenty_two] = [r for r in result.races if r.season == 2022]
    assert two_thousand_twenty_two.estimated_pit_loss is False
    assert two_thousand_twenty_two.pit_loss_seasons != ()
    assert all(2018 <= s <= 2021 for s in two_thousand_twenty_two.pit_loss_seasons)
    assert two_thousand_twenty_two.neutralised_race is False
