"""Slow test for ticket 38: no two alias names reach the same OpenF1 race.

Runs the meeting lookup over the real 2023–2025 meeting lists in the warm
``.cache/openf1`` for every alias group (ticket 16). Before ticket 38,
"Singapore" and "Marina Bay" both reached the 2023 and 2024 Singapore
meetings, so those races were counted twice in the history scan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy.location_aliases import LOCATION_ALIAS_GROUPS
from f1_strategy.openf1_client import OpenF1Client
from f1_strategy.openf1_loader import _find_meeting

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "openf1"


@pytest.mark.parametrize("season", [2023, 2024, 2025])
def test_each_alias_group_reaches_at_most_one_meeting_once(season: int) -> None:
    meetings = OpenF1Client(cache_dir=CACHE_DIR).get("meetings", year=season)
    for group in LOCATION_ALIAS_GROUPS:
        reached: list[int] = []
        for alias in sorted(group):
            try:
                reached.append(int(_find_meeting(meetings, alias)["meeting_key"]))
            except ValueError:
                continue
        assert len(reached) == 1, (season, sorted(group), reached)
