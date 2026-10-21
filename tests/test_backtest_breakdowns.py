"""Seam 1 (continued): breakdowns and race-averaged scores on a Backtest Result.

All through `run_backtest` with hand-built race weekends and a fake
loader. Covers:

- race-averaged scores alongside the pooled headline, differing when
  races have different numbers of scoreable drivers
- season / circuit / sprint-vs-conventional breakdowns adding up to the
  totals
- Tuning Seasons and Held-out Season partitions read from Settings, not
  hard-coded
- Degradation source counts and the Excluded Race count
- the formatter prints each of these
"""

from __future__ import annotations

from dataclasses import replace

from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    DegradationSource,
    NeutralisationPeriod,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    Stint,
    predict,
    run_backtest,
)
from f1_strategy.backtest import format_backtest
from f1_strategy.settings import Settings

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


# ---------------------------------------------------------------------------
# Weekend fixtures: hand-built so season / circuit / sprint / scoreable-count
# can be varied one axis at a time.
# ---------------------------------------------------------------------------


def _with_race(base, *, stints=(), neutralisations=()):
    stints = tuple(stints)
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


def _top_picked_stints(base: RaceWeekend, driver: str) -> list[Stint]:
    top = predict(base)[driver].candidates[0]
    stop_lap = top.stops[0].best_lap
    return [
        Stint(driver, top.strategy.compounds[0], 1, stop_lap),
        Stint(driver, top.strategy.compounds[1], stop_lap + 1, 57),
    ]


def one_scoreable_green(
    season: int = 2024,
    circuit: str = "Alpha",
    is_sprint_weekend: bool = False,
) -> RaceWeekend:
    """VER-only hand-built green weekend; VER picks the top-pick Strategy."""
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base,
        pre_race=replace(
            base.pre_race,
            season=season,
            circuit=circuit,
            is_sprint_weekend=is_sprint_weekend,
        ),
    )
    return _with_race(base, stints=_top_picked_stints(base, "VER"))


def two_scoreable_green_both_miss(
    season: int = 2024,
    circuit: str = "Alpha",
    is_sprint_weekend: bool = False,
) -> RaceWeekend:
    """VER and LEC are both scoreable; both run S → H → M, which is not the
    top-1 pick on the standard practice setup, so both score 0 credit."""
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base,
        pre_race=replace(
            base.pre_race,
            season=season,
            circuit=circuit,
            is_sprint_weekend=is_sprint_weekend,
        ),
    )
    stints = [
        Stint("VER", S, 1, 15),
        Stint("VER", H, 16, 40),
        Stint("VER", M, 41, 57),
        Stint("LEC", S, 1, 15),
        Stint("LEC", H, 16, 40),
        Stint("LEC", M, 41, 57),
    ]
    return _with_race(base, stints=stints)


def neutralised(
    season: int = 2024, circuit: str = "Alpha", is_sprint_weekend: bool = False
) -> RaceWeekend:
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base,
        pre_race=replace(
            base.pre_race,
            season=season,
            circuit=circuit,
            is_sprint_weekend=is_sprint_weekend,
        ),
    )
    return _with_race(
        base,
        stints=_top_picked_stints(base, "VER"),
        neutralisations=[NeutralisationPeriod("SC", 10, 12)],
    )


def wet_weekend(season: int = 2024, circuit: str = "Alpha") -> RaceWeekend:
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base,
        pre_race=replace(base.pre_race, season=season, circuit=circuit),
    )
    return _with_race(
        base,
        stints=[
            Stint("VER", Compound.INTERMEDIATE, 1, 20),
            Stint("VER", M, 21, 57),
        ],
    )


def make_loader(mapping: dict[tuple[int, str], RaceWeekend]):
    def load(season: int, event: str) -> RaceWeekend:
        return mapping[(season, event)]

    return load


# ---------------------------------------------------------------------------
# Race-averaged scores alongside the pooled headline
# ---------------------------------------------------------------------------


def test_race_averaged_scores_sit_next_to_the_pooled_headline():
    # One VER-only race (scores 0.5 top-1 credit on a mirrored tie) and one
    # two-driver race where both finishers miss (0 credit over 2 drivers).
    # Pooled: 0.5 / 3 ≈ 16.7%. Race-averaged: (50% + 0%) / 2 = 25%.
    races = [RaceSpec(2024, "A"), RaceSpec(2024, "B")]
    weekends = {
        (2024, "A"): one_scoreable_green(circuit="Alpha"),
        (2024, "B"): two_scoreable_green_both_miss(circuit="Beta"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    assert result.green_headline.top_1_credit == 0.5
    assert result.green_headline.scoreable_drivers == 3
    averaged = result.green_headline_averaged
    assert averaged.races_with_scoreable == 2
    # 0.5/1 + 0/2 = 0.5
    assert averaged.top_1_rate_sum == 0.5
    # The two agree on direction but differ: pooled ≈ 16.7%, averaged = 25%.
    pooled_pct = (
        result.green_headline.top_1_credit / result.green_headline.scoreable_drivers
    )
    averaged_pct = averaged.top_1_rate_sum / averaged.races_with_scoreable
    assert averaged_pct > pooled_pct


def test_race_averaged_pooled_match_when_races_have_equal_scoreable_counts():
    races = [RaceSpec(2024, "A"), RaceSpec(2024, "B")]
    weekends = {
        (2024, "A"): one_scoreable_green(circuit="Alpha"),
        (2024, "B"): one_scoreable_green(circuit="Beta"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    pooled_pct = (
        result.green_headline.top_1_credit / result.green_headline.scoreable_drivers
    )
    averaged = result.green_headline_averaged
    averaged_pct = averaged.top_1_rate_sum / averaged.races_with_scoreable
    assert averaged_pct == pooled_pct


# ---------------------------------------------------------------------------
# Breakdowns add up to the totals
# ---------------------------------------------------------------------------


def test_season_breakdown_adds_up_to_the_all_races_total():
    races = [
        RaceSpec(2022, "A"),
        RaceSpec(2023, "B"),
        RaceSpec(2024, "C"),
    ]
    weekends = {
        (2022, "A"): one_scoreable_green(season=2022, circuit="Alpha"),
        (2023, "B"): one_scoreable_green(season=2023, circuit="Beta"),
        (2024, "C"): one_scoreable_green(season=2024, circuit="Gamma"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    assert set(result.by_season) == {2022, 2023, 2024}
    sum_scoreable = sum(t.scoreable_drivers for t in result.by_season.values())
    sum_top_1 = sum(t.top_1_credit for t in result.by_season.values())
    sum_stops = sum(t.actual_stops for t in result.by_season.values())
    sum_races = sum(t.races for t in result.by_season.values())
    assert sum_scoreable == result.all_races.scoreable_drivers
    assert sum_top_1 == result.all_races.top_1_credit
    assert sum_stops == result.all_races.actual_stops
    assert sum_races == result.all_races.races


def test_circuit_breakdown_adds_up_to_the_all_races_total():
    races = [
        RaceSpec(2024, "A"),
        RaceSpec(2024, "B"),
        RaceSpec(2024, "C"),
    ]
    weekends = {
        (2024, "A"): one_scoreable_green(circuit="Alpha"),
        (2024, "B"): one_scoreable_green(circuit="Beta"),
        (2024, "C"): one_scoreable_green(circuit="Alpha"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    assert set(result.by_circuit) == {"Alpha", "Beta"}
    assert result.by_circuit["Alpha"].races == 2
    assert result.by_circuit["Beta"].races == 1
    sum_top_1 = sum(t.top_1_credit for t in result.by_circuit.values())
    assert sum_top_1 == result.all_races.top_1_credit


def test_sprint_vs_conventional_breakdown_adds_up_to_the_all_races_total():
    races = [
        RaceSpec(2024, "sprint"),
        RaceSpec(2024, "conv"),
    ]
    weekends = {
        (2024, "sprint"): one_scoreable_green(circuit="Alpha", is_sprint_weekend=True),
        (2024, "conv"): one_scoreable_green(circuit="Beta", is_sprint_weekend=False),
    }

    result = run_backtest(races, load=make_loader(weekends))

    assert set(result.by_sprint_weekend) == {True, False}
    assert result.by_sprint_weekend[True].races == 1
    assert result.by_sprint_weekend[False].races == 1
    sum_top_1 = sum(t.top_1_credit for t in result.by_sprint_weekend.values())
    assert sum_top_1 == result.all_races.top_1_credit


# ---------------------------------------------------------------------------
# Tuning Seasons vs Held-out Season come from settings
# ---------------------------------------------------------------------------


def test_tuning_and_held_out_are_reported_side_by_side_from_settings():
    # Default Settings: tuning 2022-2024, held-out 2025.
    races = [
        RaceSpec(2022, "A"),
        RaceSpec(2024, "B"),
        RaceSpec(2025, "C"),
    ]
    weekends = {
        (2022, "A"): one_scoreable_green(season=2022, circuit="Alpha"),
        (2024, "B"): one_scoreable_green(season=2024, circuit="Beta"),
        (2025, "C"): one_scoreable_green(season=2025, circuit="Gamma"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    assert result.tuning_seasons == (2022, 2023, 2024)
    assert result.held_out_season == 2025
    assert result.tuning.races == 2
    assert result.held_out.races == 1
    # Together they cover every scored race (no 2026-plus here).
    assert result.tuning.races + result.held_out.races == result.all_races.races
    assert (
        result.tuning.top_1_credit + result.held_out.top_1_credit
        == result.all_races.top_1_credit
    )


def test_tuning_and_held_out_follow_the_settings_not_a_hard_coded_year():
    # Flip the partition: 2025 is now a Tuning Season, 2024 is Held-out.
    settings = Settings(tuning_seasons=(2022, 2023, 2025), held_out_season=2024)
    races = [RaceSpec(2024, "A"), RaceSpec(2025, "B")]
    weekends = {
        (2024, "A"): one_scoreable_green(season=2024, circuit="Alpha"),
        (2025, "B"): one_scoreable_green(season=2025, circuit="Beta"),
    }

    result = run_backtest(races, load=make_loader(weekends), settings=settings)

    assert result.tuning_seasons == (2022, 2023, 2025)
    assert result.held_out_season == 2024
    assert result.tuning.races == 1
    assert result.held_out.races == 1
    [held_out_race] = [r for r in result.races if r.season == result.held_out_season]
    assert held_out_race.season == 2024


# ---------------------------------------------------------------------------
# Degradation source counts
# ---------------------------------------------------------------------------


def test_degradation_source_counts_are_recorded_per_race_and_summed_on_the_result():
    races = [RaceSpec(2024, "A"), RaceSpec(2024, "B")]
    weekends = {
        (2024, "A"): one_scoreable_green(circuit="Alpha"),
        (2024, "B"): one_scoreable_green(circuit="Beta"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    # Each race records a non-empty source count derived from its predictions.
    assert all(r.degradation_sources for r in result.races)
    # The run-level counts equal the per-race sums.
    for source in result.degradation_source_counts:
        assert result.degradation_source_counts[source] == sum(
            r.degradation_sources.get(source, 0) for r in result.races
        )
    # And the sources that appear are DegradationSource members.
    for source in result.degradation_source_counts:
        assert isinstance(source, DegradationSource)


# ---------------------------------------------------------------------------
# Excluded Race count
# ---------------------------------------------------------------------------


def test_excluded_race_count_is_reported():
    races = [
        RaceSpec(2024, "wet"),
        RaceSpec(2024, "ok"),
        RaceSpec(2024, "boom"),
    ]
    weekends = {
        (2024, "wet"): wet_weekend(),
        (2024, "ok"): one_scoreable_green(circuit="Alpha"),
        (2024, "boom"): one_scoreable_green(circuit="Beta"),
    }

    def load(season, event):
        if event == "boom":
            raise FileNotFoundError("no cache")
        return weekends[(season, event)]

    result = run_backtest(races, load=load)

    assert len(result.excluded) == 2
    assert len(result.races) == 1
    text = format_backtest(result)
    assert "Excluded Races: 2" in text


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def test_format_backtest_prints_breakdowns_tuning_held_out_and_sources():
    races = [
        RaceSpec(2022, "A"),
        RaceSpec(2024, "B"),
        RaceSpec(2025, "C"),
    ]
    weekends = {
        (2022, "A"): one_scoreable_green(season=2022, circuit="Alpha"),
        (2024, "B"): one_scoreable_green(season=2024, circuit="Beta"),
        (2025, "C"): one_scoreable_green(season=2025, circuit="Gamma"),
    }

    result = run_backtest(races, load=make_loader(weekends))

    text = format_backtest(result)

    assert "race-averaged" in text
    assert "By season" in text
    assert "2022" in text and "2024" in text and "2025" in text
    assert "By circuit" in text
    assert "Alpha" in text and "Beta" in text and "Gamma" in text
    assert "Sprint vs conventional" in text
    assert "conventional" in text
    assert "Tuning Seasons (2022, 2023, 2024)" in text
    assert "Held-out Season (2025)" in text
    assert "Degradation source counts" in text
