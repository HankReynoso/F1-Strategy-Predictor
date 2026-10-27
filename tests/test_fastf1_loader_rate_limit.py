"""Rate-limit propagation out of the FastF1 loader's past-race scan.

The past-race scanner used to swallow every exception from
``fastf1.get_session(...).load(...)`` with ``except Exception: continue``,
which silently turned a `RateLimitExceededError` on a past race into
"no history at this circuit". These tests pin that a critical FastF1
exception now propagates through `_past_races_at_circuit` and
`_measure_pit_loss_and_history`, so the Backtest's rate-limit retry can
see it and wait.

These are fast tests: they monkeypatch FastF1's own entry points so no
network or cache is touched.
"""

from __future__ import annotations

import pytest
from fastf1.exceptions import RateLimitExceededError

from f1_strategy import fastf1_loader


class _FakeSchedule:
    """Mimics a FastF1 schedule DataFrame enough for `_past_races_at_circuit`.

    `.isin()` is exposed on the fake Location column, and iterrows yields
    one row per matching event with a RoundNumber field.
    """

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __getitem__(self, key):
        if key == "Location":
            return _FakeLocationColumn(self._rows)
        # Boolean mask returned from isin(): filter rows.
        if isinstance(key, _BoolMask):
            return _FakeSchedule([r for r, keep in zip(self._rows, key.values) if keep])
        raise KeyError(key)

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, row

    @property
    def empty(self) -> bool:
        return not self._rows


class _FakeLocationColumn:
    def __init__(self, rows):
        self._rows = rows

    def isin(self, values):
        values = set(values)
        return _BoolMask([r["Location"] in values for r in self._rows])


class _BoolMask:
    def __init__(self, values):
        self.values = values


def test_rate_limit_from_past_schedule_propagates(monkeypatch, tmp_path):
    """A `RateLimitExceededError` from `fastf1.get_event_schedule` while
    scanning past seasons must propagate, not be swallowed."""

    def boom_schedule(season, **_kwargs):
        raise RateLimitExceededError("any API: 500 calls/h")

    monkeypatch.setattr(fastf1_loader.fastf1, "get_event_schedule", boom_schedule)

    with pytest.raises(RateLimitExceededError):
        fastf1_loader._past_races_at_circuit(
            circuit="Melbourne",
            race_season=2022,
            min_season=2018,
            cache_dir=tmp_path,
            fuel_effect_s_per_lap=0.03,
            history_min_stint_length=4,
            pit_loss_min_season=2018,
            history_min_season=2022,
            pit_loss_required=False,
        )


def test_rate_limit_from_past_race_load_propagates(monkeypatch, tmp_path):
    """A `RateLimitExceededError` while loading a past season's race must
    propagate instead of being treated as 'this race genuinely has no
    data' — which is what caused 2022 Australia and Canada to drop out of
    the first baseline attempt."""

    def fake_schedule(season, **_kwargs):
        return _FakeSchedule(
            [{"Location": "Melbourne", "RoundNumber": 1}]
        )

    class _FakeRace:
        def load(self, **_kwargs):
            raise RateLimitExceededError("any API: 500 calls/h")

    def fake_get_session(season, round_number, kind):
        return _FakeRace()

    monkeypatch.setattr(fastf1_loader.fastf1, "get_event_schedule", fake_schedule)
    monkeypatch.setattr(fastf1_loader.fastf1, "get_session", fake_get_session)

    with pytest.raises(RateLimitExceededError):
        fastf1_loader._past_races_at_circuit(
            circuit="Melbourne",
            race_season=2022,
            min_season=2018,
            cache_dir=tmp_path,
            fuel_effect_s_per_lap=0.03,
            history_min_stint_length=4,
            pit_loss_min_season=2018,
            history_min_season=2022,
            pit_loss_required=False,
        )


def test_non_critical_exceptions_still_swallowed(monkeypatch, tmp_path):
    """A plain `ValueError` from a past race load is still treated as 'no
    data for that race', now with a Data Quality Warning naming the error
    (ticket 40). A network error no longer is: ticket 40's
    ``tests/test_fastf1_fetch_errors.py`` pins that it raises."""

    def fake_schedule(season, **_kwargs):
        return _FakeSchedule(
            [{"Location": "Melbourne", "RoundNumber": 1}]
        )

    class _FakeRace:
        def load(self, **_kwargs):
            raise ValueError("some non-critical FastF1 problem")

    def fake_get_session(season, round_number, kind):
        return _FakeRace()

    monkeypatch.setattr(fastf1_loader.fastf1, "get_event_schedule", fake_schedule)
    monkeypatch.setattr(fastf1_loader.fastf1, "get_session", fake_get_session)

    pit, seasons, hist, warnings = fastf1_loader._past_races_at_circuit(
        circuit="Melbourne",
        race_season=2022,
        min_season=2018,
        cache_dir=tmp_path,
        fuel_effect_s_per_lap=0.03,
        history_min_stint_length=4,
        pit_loss_min_season=2018,
        history_min_season=2022,
        pit_loss_required=False,
    )
    assert pit is None
    assert seasons == ()
    assert hist == {}
    assert len(warnings) == 4  # 2018–2021, one per season
    assert "ValueError: some non-critical FastF1 problem" in warnings[0]
