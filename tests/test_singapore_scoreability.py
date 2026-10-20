"""Slow end-to-end check: Singapore 2024 scores 18 drivers, not 7.

Before ticket 10, the scorer inferred retirement from a Stint ending before
the race distance, which folded 11 lapped finishers into "retired". The
official 2024 Singapore classification is 19 finishers and 2 retirements
(MAG retired lap 57 of 62 but was classified 19th; ALB retired lap 15).
Per ticket 10's triage decision, scoreability requires the chequered flag,
so Magnussen stays unscoreable: 19 - 1 = 18 scoreable drivers.
"""

from pathlib import Path

import pytest

from f1_strategy import compare, predict
from f1_strategy.fastf1_loader import load_weekend

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastf1"


def test_singapore_2024_scores_18_drivers() -> None:
    weekend = load_weekend(2024, "Singapore Grand Prix", cache_dir=CACHE_DIR)
    # FastF1's race Status, verified against the official classification:
    # 18 drivers took the chequered flag (7 lead-lap, 11 lapped). The two
    # others — MAG (Status "Retired", classified 19th after retiring lap 57)
    # and ALB (retired lap 15) — did not take the flag. The official FIA
    # classification shows 19 drivers; ticket 10's triage decision excludes
    # the one who was classified despite retiring, leaving 18.
    assert sum(weekend.race.finishing_status.values()) == 18
    assert weekend.race.finishing_status["MAG"] is False
    assert weekend.race.finishing_status["ALB"] is False
    assert weekend.race.finishing_status["NOR"] is True
    # ALO was lapped (8th, +1 lap) — a classified finisher who took the flag.
    assert weekend.race.finishing_status["ALO"] is True

    comparison = compare(predict(weekend), weekend)

    assert comparison.summary.scoreable_drivers == 18
