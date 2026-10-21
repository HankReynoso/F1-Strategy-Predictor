"""Seam 1: run a Backtest.

Most Backtest tests go through `run_backtest` with hand-built race weekends
and a fake loader, so no internet is needed. The command's Backtest mode is
tested with the same injected `load` and `list_season` seams.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    BacktestResult,
    Compound,
    ExcludedRace,
    ExclusionReason,
    NeutralisationPeriod,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    Stint,
    predict,
    run_backtest,
)
from f1_strategy.backtest import format_backtest
from f1_strategy.cli import main
from f1_strategy.settings import Settings

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


def with_race(base, *, stints=(), neutralisations=(), finishing_status=None):
    stints = tuple(stints)
    if finishing_status is None:
        last_by_driver: dict[str, int] = {}
        for stint in stints:
            last_by_driver[stint.driver] = max(
                last_by_driver.get(stint.driver, 0), stint.end_lap
            )
        finishing_status = {
            driver: last_lap >= base.pre_race.race_laps
            for driver, last_lap in last_by_driver.items()
        }
    return RaceWeekend(
        pre_race=base.pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=tuple(neutralisations),
            finishing_status=dict(finishing_status),
        ),
    )


def green_weekend() -> RaceWeekend:
    """A hand-built conventional green weekend where VER picks M → H by top."""
    base = weekend(standard_practice(), TEAMS)
    top = predict(base)["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    return with_race(
        base,
        stints=[
            Stint("VER", top.strategy.compounds[0], 1, stop_lap),
            Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
        ],
    )


def neutralised_weekend() -> RaceWeekend:
    """Same shape as green_weekend but flagged as a Neutralised Race."""
    base = weekend(standard_practice(), TEAMS)
    top = predict(base)["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    return with_race(
        base,
        stints=[
            Stint("VER", top.strategy.compounds[0], 1, stop_lap),
            Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
        ],
        neutralisations=[NeutralisationPeriod("SC", 10, 12)],
    )


def wet_weekend() -> RaceWeekend:
    base = weekend(standard_practice(), TEAMS)
    return with_race(
        base,
        stints=[
            Stint("VER", Compound.INTERMEDIATE, 1, 20),
            Stint("VER", M, 21, 57),
        ],
    )


def miss_weekend() -> RaceWeekend:
    """A green weekend where VER's actual Strategy is not the top pick."""
    base = weekend(standard_practice(), TEAMS)
    # S → H → M is a 2-stop and will not be VER's top pick in the standard
    # practice setup (where M → H / H → M dominate).
    return with_race(
        base,
        stints=[
            Stint("VER", S, 1, 15),
            Stint("VER", H, 16, 40),
            Stint("VER", M, 41, 57),
        ],
    )


def make_loader(mapping: dict[tuple[int, str], RaceWeekend]):
    def load(season: int, event: str) -> RaceWeekend:
        return mapping[(season, event)]

    return load


# ---------------------------------------------------------------------------
# Public call shape
# ---------------------------------------------------------------------------


def test_run_backtest_returns_a_backtest_result_with_each_scored_race():
    races = [RaceSpec(2024, "Test A"), RaceSpec(2024, "Test B")]
    weekends = {(2024, "Test A"): green_weekend(), (2024, "Test B"): green_weekend()}

    result = run_backtest(races, load=make_loader(weekends))

    assert isinstance(result, BacktestResult)
    assert len(result.races) == 2
    assert [r.event for r in result.races] == ["Test A", "Test B"]
    assert result.excluded == ()


def test_each_race_result_carries_its_metadata_and_summary():
    races = [RaceSpec(2024, "Test A")]
    weekends = {(2024, "Test A"): green_weekend()}

    [first] = run_backtest(races, load=make_loader(weekends)).races

    assert first.season == 2024
    assert first.event == "Test A"
    assert first.circuit == "Test Circuit"
    assert first.is_sprint_weekend is False
    assert first.neutralised_race is False
    assert first.summary.scoreable_drivers == 1  # VER only has stints


# ---------------------------------------------------------------------------
# Excluded Races
# ---------------------------------------------------------------------------


def test_a_wet_race_becomes_an_excluded_race_with_reason_not_dry():
    races = [RaceSpec(2024, "wet"), RaceSpec(2024, "dry")]
    weekends = {(2024, "wet"): wet_weekend(), (2024, "dry"): green_weekend()}

    result = run_backtest(races, load=make_loader(weekends))

    assert len(result.races) == 1
    assert result.races[0].event == "dry"
    assert len(result.excluded) == 1
    assert result.excluded[0].reason is ExclusionReason.NOT_DRY_RACE
    assert result.excluded[0].event == "wet"
    assert "Dry Race" in result.excluded[0].detail


def test_a_race_whose_prediction_raises_becomes_an_excluded_race():
    def exploding_predict(weekend_arg, settings):
        raise RuntimeError("boom from predict")

    races = [RaceSpec(2024, "bang"), RaceSpec(2024, "ok")]
    weekends = {(2024, "bang"): green_weekend(), (2024, "ok"): green_weekend()}

    import f1_strategy.backtest as backtest_mod

    real_predict = backtest_mod.predict

    def flaky(weekend_arg, settings=None):
        if weekend_arg is weekends[(2024, "bang")]:
            raise RuntimeError("boom from predict")
        return real_predict(weekend_arg, settings)

    backtest_mod.predict = flaky
    try:
        result = run_backtest(races, load=make_loader(weekends))
    finally:
        backtest_mod.predict = real_predict

    assert len(result.races) == 1
    assert result.races[0].event == "ok"
    assert len(result.excluded) == 1
    assert result.excluded[0].reason is ExclusionReason.PREDICTION_FAILED
    assert "boom from predict" in result.excluded[0].detail


def test_a_race_whose_loader_raises_becomes_an_excluded_race():
    def load(season, event):
        if event == "missing":
            raise FileNotFoundError("no cache for missing")
        return green_weekend()

    races = [RaceSpec(2024, "missing"), RaceSpec(2024, "ok")]

    result = run_backtest(races, load=load)

    assert len(result.races) == 1
    assert result.races[0].event == "ok"
    assert len(result.excluded) == 1
    assert result.excluded[0].reason is ExclusionReason.DATA_UNAVAILABLE
    assert "no cache" in result.excluded[0].detail


# ---------------------------------------------------------------------------
# Pooled headline
# ---------------------------------------------------------------------------


def test_green_headline_excludes_neutralised_races_and_the_neutralised_figure_includes_them():
    green = green_weekend()
    neutralised = neutralised_weekend()

    result = run_backtest(
        [RaceSpec(2024, "green"), RaceSpec(2024, "SC")],
        load=make_loader({(2024, "green"): green, (2024, "SC"): neutralised}),
    )

    assert result.green_headline.races == 1
    assert result.green_headline.scoreable_drivers == 1
    assert result.neutralised.races == 1
    assert result.neutralised.scoreable_drivers == 1
    assert result.all_races.races == 2
    assert result.all_races.scoreable_drivers == 2


def test_split_tie_credit_carries_through_to_every_total():
    # VER's top pick on the standard practice weekend is a mirrored M → H /
    # H → M tie (ticket 14 splits credit 1/2). Three identical green weekends
    # should sum to exactly 3 * 0.5 top-1 credit, both in the green headline
    # and in the all-races total.
    races = [RaceSpec(2024, name) for name in ("A", "B", "C")]
    weekends = {(2024, name): green_weekend() for name in ("A", "B", "C")}

    result = run_backtest(races, load=make_loader(weekends))

    assert result.green_headline.top_1_credit == pytest.approx(1.5)
    assert result.green_headline.top_3_credit == pytest.approx(3.0)
    assert result.all_races.top_1_credit == pytest.approx(1.5)
    # Scoreable drivers are summed across races.
    assert result.green_headline.scoreable_drivers == 3


def test_stop_window_hits_are_counted_over_actual_stops():
    # The hand-built weekend's VER top pick's Stop Window contains the
    # chosen stop lap by construction, so stop_window_hits=1 and
    # actual_stops=1 for VER's 1-stop. Two races → 2/2 hits.
    races = [RaceSpec(2024, "A"), RaceSpec(2024, "B")]
    weekends = {(2024, "A"): green_weekend(), (2024, "B"): green_weekend()}

    result = run_backtest(races, load=make_loader(weekends))

    assert result.green_headline.stop_window_hits == 2
    assert result.green_headline.actual_stops == 2


# ---------------------------------------------------------------------------
# Isolation between races
# ---------------------------------------------------------------------------


def test_one_races_outcome_never_changes_another_races_prediction():
    # Running the same green weekend before vs after a "miss" weekend must
    # give the first race the same prediction summary either way, which is
    # what "no leakage between races" means for the Backtest.
    green = green_weekend()
    miss = miss_weekend()

    only = run_backtest(
        [RaceSpec(2024, "g")], load=make_loader({(2024, "g"): green})
    )
    with_miss_first = run_backtest(
        [RaceSpec(2024, "m"), RaceSpec(2024, "g")],
        load=make_loader({(2024, "m"): miss, (2024, "g"): green}),
    )
    g_only = only.races[0]
    g_after = next(r for r in with_miss_first.races if r.event == "g")

    assert g_after.summary == g_only.summary


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_format_backtest_shows_headline_and_excluded_counts():
    race = green_weekend()
    wet = wet_weekend()
    result = run_backtest(
        [RaceSpec(2024, "g"), RaceSpec(2024, "wet")],
        load=make_loader({(2024, "g"): race, (2024, "wet"): wet}),
    )

    text = format_backtest(result)

    assert "Top-1 Strategy Match: " in text
    assert "/1 " in text  # one scoreable driver
    assert "Excluded Races: 1" in text
    assert "not a Dry Race" in text
    assert "wet" in text


# ---------------------------------------------------------------------------
# Command's Backtest mode
# ---------------------------------------------------------------------------


def test_command_backtest_mode_runs_chosen_seasons_and_prints_result(capsys):
    weekends = {
        (2024, "Alpha GP"): green_weekend(),
        (2024, "Beta GP"): green_weekend(),
    }
    specs = [
        RaceSpec(2024, "Alpha GP"),
        RaceSpec(2024, "Beta GP"),
    ]

    def load(season, event):
        return weekends[(season, event)]

    def list_season(season):
        assert season == 2024
        return specs

    exit_code = main(["backtest", "2024"], load=load, list_season=list_season)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Races scored: 2" in captured.out
    assert "Top-1 Strategy Match" in captured.out
    # Progress goes to stderr so a pipe never sees a half report.
    assert "Alpha GP" in captured.err
    assert "Beta GP" in captured.err


def test_command_single_race_mode_is_unchanged(capsys):
    race = green_weekend()

    exit_code = main(
        ["2024", "Test Grand Prix"], load=lambda season, event: race
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Top-1 Strategy Match" in out
    assert "Races scored" not in out
