"""Fast tests for ticket 40: FastF1 errors never become silently missing data.

FastF1's ``Session.load`` and ``get_event_schedule`` catch nearly every
error themselves: they log it (a DEBUG record carrying the traceback) and
return with the data missing. Only the rate limit is raised. The loader
used to treat every missing session or past race the same way: drop it.

Each fake below fails the way FastF1 really does. A non-critical error goes
through FastF1's own ``soft_exceptions`` wrapper, so it is logged and
swallowed exactly as in ``Session.load``. "Refused" is FastF1's own
``SessionNotAvailableError``, which is what a 401 or an empty archive turns
into. "Network" is a ``requests`` ``ConnectionError``. No network, no cache,
no sleeping.
"""

from __future__ import annotations

import functools
from typing import Any

import pandas as pd
import pytest
import requests
from fastf1._api import SessionNotAvailableError
from fastf1.exceptions import RateLimitExceededError
from fastf1.logger import get_logger, soft_exceptions

from f1_strategy import fastf1_loader
from f1_strategy.backtest import (
    ExclusionReason,
    RaceSpec,
    _load_with_rate_limit_retry,
    run_backtest,
)
from f1_strategy.data import measure_pit_loss_and_history
from f1_strategy.fastf1_errors import FastF1FetchError
from f1_strategy.openf1_loader import PastRaceSamples
from f1_strategy.weekend import Compound


_CORE_LOGGER = get_logger("core")

OK = "ok"
RATE_LIMIT = "rate limit"


def _network() -> requests.exceptions.ConnectionError:
    return requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='livetiming.formula1.com'): Max retries exceeded"
    )


def _refused() -> SessionNotAvailableError:
    return SessionNotAvailableError("No data for this session!")


class _Logged:
    """An error FastF1 logs and swallows inside ``Session.load``."""

    def __init__(self, error: Exception):
        self.error = error


class _LoggedButLoaded(_Logged):
    """FastF1 logs a failure on a side lookup but the laps load anyway, as
    with the Ergast first-lap-time lookup."""


class _Raised:
    """An error that escapes ``fastf1.get_session`` itself."""

    def __init__(self, error: Exception):
        self.error = error


class _FakeSession:
    def __init__(self, outcome: Any, event: dict):
        self._outcome = outcome
        self.event = event
        self.total_laps = 66

    def load(self, **_kwargs) -> None:
        if self._outcome == RATE_LIMIT:
            raise RateLimitExceededError("any API: 500 calls/h")
        if isinstance(self._outcome, _Logged):
            error = self._outcome.error

            @soft_exceptions("lap timing data", "Failed to load timing data!", _CORE_LOGGER)
            def _load_laps_data() -> None:
                raise error

            _load_laps_data()
            if not isinstance(self._outcome, _LoggedButLoaded):
                return
        self._laps = "loaded"


class _FakeFastF1:
    """Scripted ``fastf1.get_session`` / ``fastf1.get_event_schedule``.

    Sessions are keyed by ``(season, kind)``, ``kind`` being "R", "FP1" and
    so on. Each key holds a list of outcomes used in order; the last one
    repeats. Every call is recorded.
    """

    def __init__(self) -> None:
        self.outcomes: dict[tuple[int, str], list[Any]] = {}
        self.schedules: dict[int, Any] = {}
        self.calls: list[tuple[int, str]] = []

    def script(self, season: int, kind: str, *outcomes: Any) -> None:
        self.outcomes[(season, kind)] = list(outcomes)

    def get_session(self, season: int, _event: Any, kind: str) -> _FakeSession:
        self.calls.append((season, kind))
        queue = self.outcomes.get((season, kind), [OK])
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, _Raised):
            raise outcome.error
        return _FakeSession(outcome, _EVENT)

    def get_event_schedule(self, season: int, **_kwargs) -> pd.DataFrame:
        scripted = self.schedules.get(season)
        if isinstance(scripted, _Logged):
            # What a schedule outage looks like: every backend logged and
            # swallowed, then FastF1 raises a plain ValueError.
            @soft_exceptions("FastF1 schedule", "Failed to load schedule!", _CORE_LOGGER)
            def _load_schedule() -> None:
                raise scripted.error

            _load_schedule()
            raise ValueError("Failed to load any schedule data.")
        location = scripted or "Barcelona"
        return pd.DataFrame(
            [
                {
                    "RoundNumber": 5,
                    "EventName": f"{location} Grand Prix",
                    "Location": location,
                    "EventFormat": "conventional",
                }
            ]
        )


_EVENT = {
    "EventName": "Spanish Grand Prix",
    "Location": "Barcelona",
    "EventFormat": "conventional",
    "Session1": "Practice 1",
    "Session2": "Practice 2",
    "Session3": "Practice 3",
    "Session4": "Qualifying",
    "Session5": "Race",
}


@pytest.fixture
def fake(monkeypatch) -> _FakeFastF1:
    fake = _FakeFastF1()
    monkeypatch.setattr(fastf1_loader.fastf1, "get_session", fake.get_session)
    monkeypatch.setattr(
        fastf1_loader.fastf1, "get_event_schedule", fake.get_event_schedule
    )
    monkeypatch.setattr(fastf1_loader.fastf1.Cache, "enable_cache", lambda *a, **k: None)
    # The parts of the weekend that aren't under test.
    monkeypatch.setattr(fastf1_loader, "_starters_and_teams", lambda race: {"VER": "Red Bull Racing"})
    monkeypatch.setattr(fastf1_loader, "_laps_from", lambda session, name, drivers: ())
    monkeypatch.setattr(fastf1_loader, "_race_stints", lambda race, drivers: ())
    monkeypatch.setattr(fastf1_loader, "_neutralisation_periods", lambda race: ())
    monkeypatch.setattr(fastf1_loader, "_finishing_status", lambda race, drivers: {})
    monkeypatch.setattr(fastf1_loader, "_pit_losses_in", lambda race: [22.0])
    monkeypatch.setattr(
        fastf1_loader,
        "_historical_stint_rates",
        lambda race, fuel, min_len: [(Compound.MEDIUM, 0.05, 20)],
    )
    return fake


def _load_2022(tmp_path):
    return functools.partial(fastf1_loader.load_weekend, cache_dir=tmp_path)


SPEC = RaceSpec(season=2022, event="Spanish Grand Prix")


# ---------------------------------------------------------------------------
# Pre-race sessions.
# ---------------------------------------------------------------------------


def test_rate_limit_on_a_pre_race_session_propagates(fake, tmp_path) -> None:
    fake.script(2022, "FP2", RATE_LIMIT)
    with pytest.raises(RateLimitExceededError):
        fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)


def test_rate_limit_on_a_pre_race_session_is_waited_out_and_retried(fake, tmp_path) -> None:
    """The Backtest's wait-and-retry loads the weekend again, and the
    weekend it gets has every session, FP2 included."""
    fake.script(2022, "FP2", RATE_LIMIT, OK)
    waits: list[float] = []
    weekend = _load_with_rate_limit_retry(
        SPEC,
        load=_load_2022(tmp_path),
        wait=lambda seconds, reason: waits.append(seconds),
        progress=None,
        max_retries=2,
    )
    assert len(waits) == 1
    assert [s.name for s in weekend.pre_race.sessions] == ["FP1", "FP2", "FP3", "Q"]
    assert weekend.pre_race.data_quality_warnings == ()


def test_network_error_on_a_pre_race_session_is_fetch_failed(fake, tmp_path) -> None:
    fake.script(2022, "FP1", _Logged(_network()))
    result = run_backtest([SPEC], load=_load_2022(tmp_path), wait=lambda s, r: None)
    assert result.races == ()
    [excluded] = result.excluded
    assert excluded.reason is ExclusionReason.FETCH_FAILED
    assert "FP1" in excluded.detail


def test_network_error_raised_by_get_session_is_fetch_failed(fake, tmp_path) -> None:
    fake.script(2022, "Q", _Raised(_network()))
    with pytest.raises(FastF1FetchError, match="Q"):
        fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)


def test_a_session_the_archive_has_no_data_for_is_a_warning(fake, tmp_path) -> None:
    """A refused or empty session is missing for a known reason: the race
    still loads, without it, and says so."""
    fake.script(2022, "FP3", _Logged(_refused()))
    weekend = fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)
    assert [s.name for s in weekend.pre_race.sessions] == ["FP1", "FP2", "Q"]
    [warning] = [w for w in weekend.pre_race.data_quality_warnings if "FP3" in w]
    assert "live-timing archive returned no data" in warning
    assert "fetch succeeded" not in warning


def test_a_session_that_fails_for_another_reason_names_the_error(fake, tmp_path) -> None:
    fake.script(2022, "FP2", _Raised(ValueError("Session type 'FP2' does not exist")))
    weekend = fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)
    [warning] = [w for w in weekend.pre_race.data_quality_warnings if "FP2" in w]
    assert "ValueError" in warning and "does not exist" in warning


def test_a_logged_side_failure_on_a_session_that_loads_is_ignored(fake, tmp_path) -> None:
    fake.script(2022, "FP1", _LoggedButLoaded(_network()))
    weekend = fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)
    assert [s.name for s in weekend.pre_race.sessions] == ["FP1", "FP2", "FP3", "Q"]
    assert weekend.pre_race.data_quality_warnings == ()


def test_network_error_on_the_race_itself_is_fetch_failed(fake, tmp_path) -> None:
    fake.script(2022, "R", _Logged(_network()))
    with pytest.raises(FastF1FetchError):
        fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# Past races read by a 2022 race (FastF1 loader, ADR-0004 pre-era pass).
# ---------------------------------------------------------------------------


def test_refused_pre_era_races_are_recorded_with_the_archive_reason(fake, tmp_path) -> None:
    """2018–2020 sit behind the archive's 401 (ADR-0006). Spain 2022 still
    gets its Pit Loss from 2021, and each refused season is a Data Quality
    Warning that says why."""
    for season in (2018, 2019, 2020):
        fake.script(season, "R", _Logged(_refused()))
    weekend = fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)
    assert weekend.pre_race.pit_loss_seasons == (2021,)
    warnings = weekend.pre_race.data_quality_warnings
    assert [w[:4] for w in warnings] == ["2018", "2019", "2020"]
    for warning in warnings:
        assert "Barcelona" in warning
        assert "live-timing archive returned no data" in warning
        assert "ADR-0006" in warning
        assert "fetch succeeded" not in warning


def test_network_error_on_a_pre_era_race_is_fetch_failed(fake, tmp_path) -> None:
    fake.script(2019, "R", _Logged(_network()))
    result = run_backtest([SPEC], load=_load_2022(tmp_path), wait=lambda s, r: None)
    [excluded] = result.excluded
    assert excluded.reason is ExclusionReason.FETCH_FAILED
    assert "2019" in excluded.detail


def test_schedule_outage_on_a_pre_era_season_is_fetch_failed(fake, tmp_path) -> None:
    fake.schedules[2020] = _Logged(_network())
    with pytest.raises(FastF1FetchError, match="2020"):
        fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)


def test_target_and_history_warnings_are_both_kept_target_first(fake, tmp_path) -> None:
    """Same order as the OpenF1 loader: the weekend's own warnings, then
    the history scan's."""
    fake.script(2022, "FP1", _Logged(_refused()))
    fake.script(2019, "R", _Logged(_refused()))
    weekend = fastf1_loader.load_weekend(2022, "Spanish Grand Prix", cache_dir=tmp_path)
    warnings = weekend.pre_race.data_quality_warnings
    assert len(warnings) == 2
    assert warnings[0].startswith("FP1")
    assert warnings[1].startswith("2019")


# ---------------------------------------------------------------------------
# A 2022 past race read by a 2023+ race (router, FastF1 branch).
# ---------------------------------------------------------------------------


def _openf1_2023(client, season, event, **kwargs) -> PastRaceSamples:
    return PastRaceSamples(
        pit_losses=(21.0,),
        stint_rates=((Compound.MEDIUM, 0.05, 20),),
        race_id=f"openf1 {season}",
    )


def test_network_error_on_a_fastf1_past_race_propagates_through_the_router(fake) -> None:
    fake.script(2022, "R", _Logged(_network()))
    with pytest.raises(FastF1FetchError, match="2022"):
        measure_pit_loss_and_history(
            circuit="Barcelona",
            race_season=2024,
            openf1_client=None,
            openf1_load_past_race_samples=_openf1_2023,
        )


def test_refused_fastf1_past_race_warning_gives_the_reason(fake) -> None:
    fake.script(2022, "R", _Logged(_refused()))
    *_, warnings = measure_pit_loss_and_history(
        circuit="Barcelona",
        race_season=2024,
        openf1_client=None,
        openf1_load_past_race_samples=_openf1_2023,
        return_warnings=True,
    )
    [warning] = warnings
    assert warning.startswith("2022 Barcelona")
    assert "live-timing archive returned no data" in warning
    assert "fetch succeeded" not in warning


def test_schedule_outage_on_a_fastf1_past_season_propagates_through_the_router(fake) -> None:
    fake.schedules[2022] = _Logged(_network())
    with pytest.raises(FastF1FetchError, match="2022"):
        measure_pit_loss_and_history(
            circuit="Barcelona",
            race_season=2024,
            openf1_client=None,
            openf1_load_past_race_samples=_openf1_2023,
        )


def test_a_fastf1_past_race_that_loads_has_no_note(fake) -> None:
    samples = fastf1_loader.load_past_race_samples(2022, "Barcelona")
    assert samples.pit_losses == (22.0,)
    assert samples.note is None
