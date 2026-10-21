"""Slow Backtest check on real 2024 data.

Runs the Backtest over a small set of 2024 races and asserts that
Singapore 2024's numbers inside it match ticket 08's "Rerun after ticket
14" (top-1 6.5/18, top-3 13.75/18, Stop Window hits 3/20). This catches
Backtest and loader bugs; the ticket 08 numbers are known good.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import RaceSpec, run_backtest
from f1_strategy.fastf1_loader import load_weekend

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastf1"


def _loader(season: int, event: str):
    return load_weekend(season, event, cache_dir=CACHE_DIR)


def test_singapore_2024_backtest_matches_ticket_08_rerun_after_ticket_14() -> None:
    result = run_backtest(
        [RaceSpec(2024, "Singapore Grand Prix")],
        load=_loader,
    )

    assert result.excluded == ()
    assert len(result.races) == 1
    singapore = result.races[0]
    assert singapore.circuit == "Marina Bay"
    assert singapore.neutralised_race is False
    assert singapore.summary.scoreable_drivers == 18
    # Ticket 08, "Rerun after ticket 14": top-1 6.5/18, top-3 13.75/18,
    # Stop Window hits 3/20.
    assert singapore.summary.top_1_credit == pytest.approx(6.5)
    assert singapore.summary.top_3_credit == pytest.approx(13.75)
    assert singapore.summary.stop_window_hits == 3
    assert singapore.actual_stops == 20

    # The green-race headline must equal the single Singapore race (same
    # scoreable count, same split tie credit, same window hits).
    assert result.green_headline.scoreable_drivers == 18
    assert result.green_headline.top_1_credit == pytest.approx(6.5)
    assert result.green_headline.stop_window_hits == 3
    assert result.green_headline.actual_stops == 20
