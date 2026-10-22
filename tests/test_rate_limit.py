"""Seam 1: FastF1 rate-limit handling in `run_backtest`.

A full Backtest on a cold cache can trip FastF1 3.8's hourly request limit
(500 uncached calls/h; `RateLimitExceededError`). Hitting it must not turn a
race into a `data unavailable` Excluded Race, and must not silently skip
history for a later race. These tests go through the public `run_backtest`
call with a fake loader that raises `RateLimitExceededError` and a fake
`wait` so no test actually sleeps.
"""

from __future__ import annotations

import pytest
from fastf1.exceptions import RateLimitExceededError
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    ExclusionReason,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    Stint,
    predict,
    run_backtest,
)
from f1_strategy.backtest import format_backtest


def _green(base) -> RaceWeekend:
    top = predict(base)["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    stints = (
        Stint("VER", top.strategy.compounds[0], 1, stop_lap),
        Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
    )
    return RaceWeekend(
        pre_race=base.pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=(),
            finishing_status={"VER": True},
        ),
    )


def test_rate_limit_hit_once_then_succeeds_races_scored_not_excluded():
    base = weekend(standard_practice(), TEAMS)
    attempts: dict[tuple[int, str], int] = {}
    waits: list[tuple[float, str]] = []

    def load(season: int, event: str) -> RaceWeekend:
        n = attempts.get((season, event), 0) + 1
        attempts[(season, event)] = n
        if n == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return _green(base)

    def wait(seconds: float, reason: str) -> None:
        waits.append((seconds, reason))

    result = run_backtest(
        [RaceSpec(2024, "Rate Limited GP")], load=load, wait=wait
    )

    assert len(result.races) == 1
    assert result.excluded == ()
    assert attempts[(2024, "Rate Limited GP")] == 2
    assert len(waits) == 1
    assert waits[0][0] > 0.0
    assert "rate" in waits[0][1].lower()


def test_rate_limit_waiting_uses_injected_wait_so_tests_dont_sleep():
    """The injected wait must be called instead of time.sleep.

    If this test ever starts taking seconds to run it means the wait seam
    is bypassed and the Backtest is really sleeping.
    """
    base = weekend(standard_practice(), TEAMS)
    calls = [0]

    def load(season: int, event: str) -> RaceWeekend:
        calls[0] += 1
        if calls[0] == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return _green(base)

    recorded: list[float] = []

    def wait(seconds: float, reason: str) -> None:
        # Record but do not sleep.
        recorded.append(seconds)

    result = run_backtest(
        [RaceSpec(2024, "GP")],
        load=load,
        wait=wait,
    )

    assert len(result.races) == 1
    assert recorded  # the Backtest went through the wait seam


def test_rate_limit_progress_output_reports_the_wait():
    base = weekend(standard_practice(), TEAMS)
    hits = [0]

    def load(season: int, event: str) -> RaceWeekend:
        hits[0] += 1
        if hits[0] == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return _green(base)

    messages: list[str] = []

    def wait(seconds: float, reason: str) -> None:
        pass

    def progress(label: str) -> None:
        messages.append(label)

    run_backtest(
        [RaceSpec(2024, "GP")], load=load, wait=wait, progress=progress
    )

    joined = "\n".join(messages).lower()
    assert "rate" in joined or "wait" in joined
    assert "gp" in joined


def test_warm_cache_rerun_never_waits():
    """A loader that succeeds on first try must never trigger `wait`."""
    base = weekend(standard_practice(), TEAMS)

    def load(season: int, event: str) -> RaceWeekend:
        return _green(base)

    waits: list[float] = []

    def wait(seconds: float, reason: str) -> None:
        waits.append(seconds)

    result = run_backtest(
        [RaceSpec(2024, "A"), RaceSpec(2024, "B")],
        load=load,
        wait=wait,
    )

    assert len(result.races) == 2
    assert waits == []


def test_rate_limit_keeps_being_raised_excludes_with_fetch_failed_not_data_unavailable():
    """After retries, a persistent rate-limit becomes a FETCH_FAILED Excluded Race.

    FETCH_FAILED is a separate reason from DATA_UNAVAILABLE so a reader can
    tell a fetch problem apart from genuine missing data.
    """

    def load(season: int, event: str) -> RaceWeekend:
        raise RateLimitExceededError("any API: 500 calls/h")

    def wait(seconds: float, reason: str) -> None:
        pass

    result = run_backtest(
        [RaceSpec(2024, "Rate Limited GP")],
        load=load,
        wait=wait,
        max_rate_limit_retries=2,
    )

    assert result.races == ()
    assert len(result.excluded) == 1
    excluded = result.excluded[0]
    assert excluded.reason is ExclusionReason.FETCH_FAILED
    assert "rate" in excluded.detail.lower() or "500 calls/h" in excluded.detail


def test_fetch_failed_distinct_from_data_unavailable_in_formatted_output():
    def load(season: int, event: str) -> RaceWeekend:
        raise RateLimitExceededError("any API: 500 calls/h")

    result = run_backtest(
        [RaceSpec(2024, "GP")],
        load=load,
        wait=lambda s, r: None,
        max_rate_limit_retries=0,
    )

    text = format_backtest(result)
    assert ExclusionReason.FETCH_FAILED.value in text
    assert "GP" in text


def test_fetch_failed_reason_round_trips_through_save_and_load(tmp_path):
    """ExclusionReason.FETCH_FAILED survives a save/load round trip."""
    from f1_strategy import (
        RunMetadata,
        load_backtest_result,
        save_backtest_result,
    )
    from f1_strategy.settings import Settings

    def load(season: int, event: str) -> RaceWeekend:
        raise RateLimitExceededError("any API: 500 calls/h")

    result = run_backtest(
        [RaceSpec(2024, "GP")],
        load=load,
        wait=lambda s, r: None,
        max_rate_limit_retries=0,
    )
    paths = save_backtest_result(
        result,
        tmp_path,
        metadata=RunMetadata(
            label="t",
            run_at="2026-10-22T00:00:00+00:00",
            code_commit="abc",
            uncommitted_changes=False,
            seasons_in_scope=(2024,),
            settings=Settings(),
        ),
    )
    reloaded, _ = load_backtest_result(paths.data)
    assert reloaded.excluded[0].reason is ExclusionReason.FETCH_FAILED


def test_rate_limit_hit_in_one_race_does_not_poison_a_later_race():
    """Waiting out a rate limit on race A leaves race B scored normally."""
    base = weekend(standard_practice(), TEAMS)
    attempts: dict[str, int] = {}

    def load(season: int, event: str) -> RaceWeekend:
        attempts[event] = attempts.get(event, 0) + 1
        if event == "A" and attempts["A"] == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return _green(base)

    result = run_backtest(
        [RaceSpec(2024, "A"), RaceSpec(2024, "B")],
        load=load,
        wait=lambda s, r: None,
    )

    assert len(result.races) == 2
    assert {r.event for r in result.races} == {"A", "B"}
    assert attempts == {"A": 2, "B": 1}
    assert result.excluded == ()


def test_default_wait_is_real_sleep_for_fast_tests_we_pass_our_own(monkeypatch):
    """Sanity: when no `wait` is supplied, the Backtest uses `time.sleep`
    (not a no-op). This test replaces `time.sleep` with a recorder so it
    never actually sleeps.
    """
    import time as time_mod

    sleeps: list[float] = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleeps.append(s))

    base = weekend(standard_practice(), TEAMS)
    hits = [0]

    def load(season: int, event: str) -> RaceWeekend:
        hits[0] += 1
        if hits[0] == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return _green(base)

    result = run_backtest([RaceSpec(2024, "GP")], load=load)

    assert len(result.races) == 1
    assert sleeps  # a real sleep call was issued (just captured, not slept)
