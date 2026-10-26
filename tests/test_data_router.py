"""Fast tests for the data facade (ticket 23).

The facade in :mod:`.data` is the one call every top-level caller
(``cli``, Backtest, Smoke Set) uses: ``load_weekend`` and
``list_season`` dispatch to :mod:`.openf1_loader` for season >= 2023
(ADR-0006) and :mod:`.fastf1_loader` otherwise, and the past-race
history scan loops across both sources so a 2024 race's history can
combine a 2022 FastF1 sample with a 2023 OpenF1 sample under one shared
weighting (ADR-0004).

The facade also enforces the pit-loss guard the ticket pins: a race
whose cross-source Pit Loss comes back empty must either reach the
existing pre-era / pit-lane-table fallback or fail loudly as an
Excluded Race. ``load_weekend`` never returns ``pit_loss=0.0`` with no
provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from f1_strategy import Compound, RaceSpec, RaceWeekend
from f1_strategy.data import (
    load_weekend,
    list_season,
    measure_pit_loss_and_history,
)
from f1_strategy.openf1_loader import PastRaceSamples
from f1_strategy.weekend import HistoricalDegradation


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


class _FixtureClient:
    """URL-keyed OpenF1 client stand-in; shared with the ticket 21/22 tests."""

    def __init__(self, fixture: dict[str, list[dict]]):
        self._fixture = {k: v for k, v in fixture.items() if not k.startswith("_")}

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        key = endpoint
        if params:
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key = f"{endpoint}?{query}"
        if key not in self._fixture:
            raise AssertionError(f"no OpenF1 fixture row for {key!r}")
        return self._fixture[key]


def _load_fixture(name: str) -> dict[str, list[dict]]:
    with (FIXTURES / name).open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def monza_fixture() -> dict[str, list[dict]]:
    return _load_fixture("monza_2024.json")


# ---------------------------------------------------------------------------
# Season router: load_weekend picks the right source.
# ---------------------------------------------------------------------------


def test_load_weekend_dispatches_2022_to_fastf1(monkeypatch) -> None:
    """2022 races go through the FastF1 loader (ADR-0006: OpenF1 doesn't
    cover 2022). The facade's job is to pick the source, not to transform
    the result."""
    sentinel = object()
    seen: dict[str, tuple] = {}

    def fake_fastf1(season, event, **kwargs):
        seen["fastf1"] = (season, event)
        return sentinel

    def fake_openf1(season, event, **kwargs):  # pragma: no cover - must not fire
        seen["openf1"] = (season, event)
        return sentinel

    from f1_strategy import data

    monkeypatch.setattr(data.fastf1_loader, "load_weekend", fake_fastf1)
    monkeypatch.setattr(data.openf1_loader, "load_weekend", fake_openf1)
    out = load_weekend(2022, "Italian Grand Prix")
    assert out is sentinel
    assert "fastf1" in seen and "openf1" not in seen
    assert seen["fastf1"] == (2022, "Italian Grand Prix")


def test_load_weekend_dispatches_2023_to_openf1(monkeypatch) -> None:
    """2023 races go through the OpenF1 loader (ADR-0006)."""
    sentinel = object()
    seen: dict[str, tuple] = {}

    def fake_fastf1(season, event, **kwargs):  # pragma: no cover
        seen["fastf1"] = (season, event)
        return sentinel

    def fake_openf1(season, event, **kwargs):
        seen["openf1"] = (season, event)
        return sentinel

    from f1_strategy import data

    monkeypatch.setattr(data.fastf1_loader, "load_weekend", fake_fastf1)
    monkeypatch.setattr(data.openf1_loader, "load_weekend", fake_openf1)
    load_weekend(2023, "Italian Grand Prix")
    assert "openf1" in seen and "fastf1" not in seen


def test_load_weekend_dispatches_2024_to_openf1(monkeypatch) -> None:
    sentinel = object()
    seen: dict[str, tuple] = {}

    def fake_openf1(season, event, **kwargs):
        seen["openf1"] = (season, event)
        return sentinel

    from f1_strategy import data

    monkeypatch.setattr(data.openf1_loader, "load_weekend", fake_openf1)
    load_weekend(2024, "Italian Grand Prix")
    assert seen["openf1"] == (2024, "Italian Grand Prix")


# ---------------------------------------------------------------------------
# list_season: router.
# ---------------------------------------------------------------------------


def test_list_season_dispatches_2022_to_fastf1(monkeypatch) -> None:
    out = [RaceSpec(2022, "Fake GP", is_sprint_weekend=False)]
    seen: dict[str, int] = {}

    def fake_fastf1(season, **kwargs):
        seen["fastf1"] = season
        return out

    def fake_openf1(season, **kwargs):  # pragma: no cover
        seen["openf1"] = season
        return out

    from f1_strategy import data

    monkeypatch.setattr(data.fastf1_loader, "list_season", fake_fastf1)
    monkeypatch.setattr(data.openf1_loader, "list_season", fake_openf1)
    assert list_season(2022) is out
    assert seen == {"fastf1": 2022}


def test_list_season_dispatches_2024_to_openf1(monkeypatch) -> None:
    out = [RaceSpec(2024, "Fake GP", is_sprint_weekend=True)]
    seen: dict[str, int] = {}

    def fake_openf1(season, **kwargs):
        seen["openf1"] = season
        return out

    from f1_strategy import data

    monkeypatch.setattr(data.openf1_loader, "list_season", fake_openf1)
    assert list_season(2024) is out
    assert seen == {"openf1": 2024}


# ---------------------------------------------------------------------------
# Cross-source history: 2024 race combines 2022 FastF1 and 2023 OpenF1.
# ---------------------------------------------------------------------------


def test_measure_history_combines_2022_fastf1_with_2023_openf1() -> None:
    """A 2024 race's history budget spans 2022 (FastF1) and 2023 (OpenF1).
    The cross-source scan must call the right source per past season and
    merge the samples under one weighting (ADR-0004 + ADR-0006 + ticket
    22's "How ticket 23 uses this" seam)."""
    fastf1_called: list[tuple[int, str]] = []
    openf1_called: list[tuple[int, str]] = []

    def fake_fastf1(season, event, **kwargs):
        fastf1_called.append((season, event))
        # 2022 Monza FastF1: 30 s pit loss, soft rate 0.12.
        return PastRaceSamples(
            pit_losses=(30.0, 30.5, 29.5),
            stint_rates=((Compound.MEDIUM, 0.12, 20),),
        )

    def fake_openf1(client, season, event, **kwargs):
        openf1_called.append((season, event))
        # 2023 Monza OpenF1: 20 s pit loss, soft rate 0.08.
        return PastRaceSamples(
            pit_losses=(20.0, 21.0, 19.0),
            stint_rates=((Compound.MEDIUM, 0.08, 25),),
        )

    pit_loss, pit_loss_seasons, estimated, hist = measure_pit_loss_and_history(
        circuit="Monza",
        race_season=2024,
        openf1_client=None,  # unused by the fakes
        fastf1_load_past_race_samples=fake_fastf1,
        openf1_load_past_race_samples=fake_openf1,
    )
    # Both branches called with the right (season, event).
    assert fastf1_called == [(2022, "Monza")]
    assert openf1_called == [(2023, "Monza")]
    # Pit Loss provenance: both seasons contribute.
    assert pit_loss_seasons == (2022, 2023)
    assert estimated is False
    # 2023 is weighted 0.5**0 = 1.0, 2022 is 0.5**1 = 0.5.
    # Medians: 30.0 (2022), 20.0 (2023). Weighted mean =
    # (30 * 0.5 + 20 * 1.0) / (0.5 + 1.0) = 35 / 1.5 ≈ 23.33.
    assert pit_loss == pytest.approx((30.0 * 0.5 + 20.0 * 1.0) / 1.5)
    # Historical Degradation: both seasons contribute to MEDIUM.
    assert Compound.MEDIUM in hist
    assert set(hist[Compound.MEDIUM].seasons) == {2022, 2023}
    assert hist[Compound.MEDIUM].stint_count == 2


def test_measure_history_2023_race_uses_only_fastf1_2022() -> None:
    """A 2023 race's same-era history is just 2022 (FastF1 only).
    Ticket 22's open question flagged that an OpenF1-only load returns
    Pit Loss 0.0; the router must fix this by reaching into FastF1 for
    2022."""
    fastf1_called: list[tuple[int, str]] = []
    openf1_called: list[tuple[int, str]] = []

    def fake_fastf1(season, event, **kwargs):
        fastf1_called.append((season, event))
        return PastRaceSamples(
            pit_losses=(25.0,) * 6,
            stint_rates=((Compound.HARD, 0.09, 15),),
        )

    def fake_openf1(client, season, event, **kwargs):  # pragma: no cover
        openf1_called.append((season, event))
        return PastRaceSamples(pit_losses=(), stint_rates=())

    pit_loss, pit_loss_seasons, estimated, hist = measure_pit_loss_and_history(
        circuit="Monza",
        race_season=2023,
        openf1_client=None,
        fastf1_load_past_race_samples=fake_fastf1,
        openf1_load_past_race_samples=fake_openf1,
    )
    assert fastf1_called == [(2022, "Monza")]
    assert openf1_called == []
    assert pit_loss_seasons == (2022,)
    assert estimated is False
    assert pit_loss == pytest.approx(25.0)


def test_measure_history_scans_every_alias_group_member() -> None:
    """Ticket 16: a circuit with a cross-season rename widens its
    history search to every ``Location`` string in its alias group. The
    cross-source scan must honour the group too, in both branches."""
    fastf1_seen: list[tuple[int, str]] = []
    openf1_seen: list[tuple[int, str]] = []

    def fake_fastf1(season, event, **kwargs):
        fastf1_seen.append((season, event))
        return PastRaceSamples(pit_losses=(), stint_rates=())

    def fake_openf1(client, season, event, **kwargs):
        openf1_seen.append((season, event))
        return PastRaceSamples(pit_losses=(), stint_rates=())

    # 2025 Miami Gardens — Miami ↔ Miami Gardens alias.
    try:
        measure_pit_loss_and_history(
            circuit="Miami Gardens",
            race_season=2025,
            openf1_client=None,
            fastf1_load_past_race_samples=fake_fastf1,
            openf1_load_past_race_samples=fake_openf1,
        )
    except ValueError:
        # Expected: no measurable data in the fakes and no pit lane
        # table entry for Miami Gardens; the raise is what the pit-loss
        # guard does.
        pass
    # 2022 is FastF1 only.
    assert ("Miami", 2022) in {(e, s) for s, e in fastf1_seen} or (
        "Miami Gardens",
        2022,
    ) in {(e, s) for s, e in fastf1_seen}
    # 2023 and 2024 go through OpenF1.
    openf1_pairs = {(e, s) for s, e in openf1_seen}
    assert any(s == 2023 for _, s in openf1_pairs)
    assert any(s == 2024 for _, s in openf1_pairs)


# ---------------------------------------------------------------------------
# Pit-loss guard: 0.0 is impossible — fall back or raise.
# ---------------------------------------------------------------------------


def _no_samples(*args, **kwargs):
    return PastRaceSamples(pit_losses=(), stint_rates=())


def test_pit_loss_guard_falls_back_to_pit_lane_table_estimate() -> None:
    """A 2023+ race whose cross-source scan returns no Pit Loss, but
    whose circuit has a pit-lane-table entry (ticket 07, ticket 25),
    must use that estimate and flag it, never surface Pit Loss 0.0."""
    pit_loss, seasons, estimated, hist = measure_pit_loss_and_history(
        circuit="Las Vegas",
        race_season=2023,
        openf1_client=None,
        fastf1_load_past_race_samples=_no_samples,
        openf1_load_past_race_samples=lambda *a, **k: _no_samples(),
    )
    # Las Vegas is in the pit lane table (ticket 07). The estimate is in
    # the usual Pit Loss range.
    assert estimated is True
    assert seasons == ()
    assert 15.0 < pit_loss < 40.0


def test_pit_loss_guard_raises_when_no_history_and_no_table_entry() -> None:
    """A race whose cross-source scan comes back empty AND whose circuit
    is not in the pit lane table must raise, so the Backtest records a
    DATA_UNAVAILABLE Excluded Race instead of calling predict() with a
    0.0 Pit Loss."""
    with pytest.raises(ValueError, match="pit lane table"):
        measure_pit_loss_and_history(
            circuit="Nowhere Circuit",
            race_season=2024,
            openf1_client=None,
            fastf1_load_past_race_samples=_no_samples,
            openf1_load_past_race_samples=lambda *a, **k: _no_samples(),
        )


def test_openf1_load_weekend_wires_cross_source_history_through_the_facade(
    monza_fixture,
) -> None:
    """End-to-end: a 2024 race through the facade combines its 2023
    OpenF1 past-race sample with its 2022 FastF1 past-race sample.

    Ticket 22's open question flagged that OpenF1-alone load of a 2023+
    race returns ``pit_loss=0.0`` for a 2023 race (no past OpenF1
    season). The router removes that risk by reaching into FastF1 for
    the pre-OpenF1 past season on every 2024+ race, and this test
    pins that wiring on the shared Monza 2024 fixture.
    """
    client = _FixtureClient(monza_fixture)

    fastf1_calls: list[tuple[int, str]] = []

    def fake_fastf1_samples(season, event, **kwargs):
        fastf1_calls.append((season, event))
        return PastRaceSamples(
            pit_losses=(28.0, 29.0, 30.0, 28.5, 29.5),
            stint_rates=((Compound.MEDIUM, 0.11, 18),),
        )

    weekend = load_weekend(
        2024,
        "Italian Grand Prix",
        openf1_client=client,
        fastf1_load_past_race_samples=fake_fastf1_samples,
    )
    assert isinstance(weekend, RaceWeekend)
    # 2022 Monza went through the FastF1 fetcher; 2023 Monza through OpenF1.
    assert fastf1_calls == [(2022, "Monza")]
    # Both past seasons contribute to the measured Pit Loss.
    assert weekend.pre_race.pit_loss_seasons == (2022, 2023)
    assert weekend.pre_race.estimated_pit_loss is False
    assert 10.0 < weekend.pre_race.pit_loss < 60.0
