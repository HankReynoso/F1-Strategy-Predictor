"""Seam: every OpenF1 weekend loads sessions from its own season (ticket 29).

Walks the real 2023-2025 OpenF1 meetings through the public
:func:`.openf1_loader.list_season` and checks, for every listed weekend,
that the meeting :func:`_find_meeting` resolves for its name belongs to
that season and that all of its sessions do too. Also loads 2025 Emilia
Romagna through the router, the race whose history scan used to run into
the cancelled 2023 meeting. Marked ``slow``; cached under
``.cache/openf1`` (gitignored), so warm runs make no requests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy import data
from f1_strategy.openf1_client import OpenF1Client
from f1_strategy.openf1_loader import _find_meeting, list_season


pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "openf1"


@pytest.fixture(scope="module")
def client() -> OpenF1Client:
    return OpenF1Client(cache_dir=CACHE_DIR)


@pytest.mark.parametrize("season", [2023, 2024, 2025])
def test_every_weekend_loads_sessions_from_its_own_season(client, season) -> None:
    meetings = client.get("meetings", year=season)
    listed = list_season(season, client=client)
    assert listed, season
    for spec in listed:
        meeting = _find_meeting(meetings, spec.event)
        assert meeting["year"] == season, spec.event
        sessions = client.get("sessions", meeting_key=meeting["meeting_key"])
        assert sessions, spec.event
        assert {s["year"] for s in sessions} == {season}, spec.event
        assert {s["meeting_key"] for s in sessions} == {meeting["meeting_key"]}
        assert sum(s["session_name"] == "Race" for s in sessions) == 1, spec.event


def test_the_2023_listing_has_22_held_races_without_imola(client) -> None:
    events = [spec.event for spec in list_season(2023, client=client)]
    assert len(events) == 22
    assert "Emilia Romagna Grand Prix" not in events


def test_2025_emilia_romagna_loads_its_own_season(client) -> None:
    weekend = data.load_weekend(
        2025, "Emilia Romagna Grand Prix", openf1_client=client
    )
    assert weekend.pre_race.season == 2025
    assert weekend.pre_race.pit_loss > 0
    assert 2023 not in weekend.pre_race.pit_loss_seasons
