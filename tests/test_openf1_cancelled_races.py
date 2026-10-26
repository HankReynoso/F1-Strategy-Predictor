"""Fast tests for ticket 29: a cancelled meeting is never a race.

The 2026-10-26 baseline excluded 2025 Emilia Romagna with "OpenF1
/v1/session_result returned no rows for race session 9086". Session 9086
belongs to the 2023 Imola meeting (1209), which OpenF1 lists with
``is_cancelled: true``. The 2025 weekend itself resolved its own 2025
sessions; the failing request came from the past-race history scan, which
matched the cancelled 2023 meeting by name and read its (empty) results.

Everything goes through the existing ``data.load_weekend`` /
``data.list_season`` calls and the OpenF1 loader's own, against the
recorded rows in ``fixtures/openf1/imola_2023_2025.json``. No network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from f1_strategy import data
from f1_strategy.openf1_loader import (
    PastRaceSamples,
    RaceCancelledError,
    _round_number,
    list_season as openf1_list_season,
    load_weekend as openf1_load_weekend,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"
EVENT = "Emilia Romagna Grand Prix"
CANCELLED_2023_RACE = 9086
SESSIONS_2023 = {9079, 9080, 9081, 9082, 9086}


class _RecordingClient:
    """URL-keyed OpenF1 stand-in that remembers every request."""

    def __init__(self) -> None:
        with (FIXTURES / "imola_2023_2025.json").open(encoding="utf-8") as f:
            raw = json.load(f)
        self._fixture = {k: v for k, v in raw.items() if not k.startswith("_")}
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        self.requests.append((endpoint, params))
        key = endpoint
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key = f"{endpoint}?{query}"
        if key not in self._fixture:
            raise AssertionError(f"no OpenF1 fixture row for {key!r}")
        return self._fixture[key]

    def session_keys(self) -> set[int]:
        return {
            int(p["session_key"]) for _, p in self.requests if "session_key" in p
        }


def _no_fastf1(season, event, **kwargs) -> PastRaceSamples:
    return PastRaceSamples(pit_losses=(), stint_rates=())


def _load_2025_via_router(client: _RecordingClient):
    return data.load_weekend(
        2025,
        EVENT,
        openf1_client=client,
        fastf1_load_past_race_samples=_no_fastf1,
    )


def test_2025_imola_loads_through_the_router_and_is_not_blocked_by_2023() -> None:
    weekend = _load_2025_via_router(_RecordingClient())

    assert weekend.pre_race.season == 2025
    assert weekend.pre_race.circuit == "Imola"
    # History came from 2024 Imola only: the cancelled 2023 race has none.
    assert weekend.pre_race.pit_loss_seasons == (2024,)


def test_2025_imola_reads_only_its_own_sessions_and_never_the_cancelled_one() -> None:
    client = _RecordingClient()
    _load_2025_via_router(client)

    assert client.session_keys().isdisjoint(SESSIONS_2023)
    # The 2025 weekend's own pre-race sessions and race were read.
    assert {9980, 9981, 9982, 9983, 9987} <= client.session_keys()
    # Meeting lookups for 2025 resolved meeting 1260, not 2023's 1209.
    session_meetings = [
        p["meeting_key"] for e, p in client.requests if e == "sessions"
    ]
    assert 1260 in session_meetings


def test_a_cancelled_past_race_is_a_warning_not_a_failure() -> None:
    weekend = _load_2025_via_router(_RecordingClient())

    warnings = weekend.pre_race.data_quality_warnings
    assert any("2023" in w and "Imola" in w for w in warnings)


def test_direct_load_of_a_cancelled_race_says_it_was_cancelled() -> None:
    client = _RecordingClient()
    with pytest.raises(RaceCancelledError, match="cancelled"):
        data.load_weekend(2023, EVENT, openf1_client=client)

    # It is a ValueError for callers that already catch the loader's
    # lookup failures, and it never touched the empty results of 9086.
    assert issubclass(RaceCancelledError, ValueError)
    assert CANCELLED_2023_RACE not in client.session_keys()


def test_season_listing_omits_the_cancelled_race() -> None:
    client = _RecordingClient()
    events = [spec.event for spec in data.list_season(2023, openf1_client=client)]

    assert EVENT not in events
    assert "Monaco Grand Prix" in events  # a held 2023 race is still listed
    assert "Pre-Season Testing" not in events


def test_season_listing_still_lists_the_same_race_in_a_season_it_ran() -> None:
    for season in (2024, 2025):
        events = [
            spec.event
            for spec in openf1_list_season(season, client=_RecordingClient())
        ]
        assert events == [EVENT]


def test_round_numbers_skip_cancelled_meetings() -> None:
    meetings = _RecordingClient().get("meetings", year=2023)
    monaco = next(m for m in meetings if m["meeting_name"] == "Monaco Grand Prix")
    cancelled = next(m for m in meetings if m["meeting_name"] == EVENT)

    assert _round_number(meetings, monaco) == 1  # testing and Imola excluded
    with pytest.raises(ValueError):
        _round_number(meetings, cancelled)


def test_the_same_event_name_in_two_seasons_resolves_to_its_own_meeting() -> None:
    """The ticket 29 invariant: one name, three seasons, three meetings,
    and a load only ever reads sessions its own meeting listed."""
    client = _RecordingClient()
    weekend = openf1_load_weekend(2025, EVENT, client=client)

    assert weekend.pre_race.season == 2025
    meeting_keys = [p["meeting_key"] for e, p in client.requests if e == "sessions"]
    assert meeting_keys[0] == 1260
    # The only other meeting its history scan may open is an earlier
    # season's Imola, never the 2025 one twice or a later season.
    assert set(meeting_keys) <= {1235, 1260}
    assert CANCELLED_2023_RACE not in client.session_keys()
