"""Backtest: run Pre-race Predictions over a list of race weekends and score them.

One public call, `run_backtest`, takes a list of race specs, an injectable
loader function and settings, and returns a `BacktestResult`. For each race
it loads, predicts and compares using the existing `predict()` and
`compare()` unchanged. A refused race (not a Dry Race), a race whose
prediction raises, and a race whose loader raises each become an
`ExcludedRace` with a reason category and detail; the loop carries on.

Aggregates are derivable from the per-race records: the headline score is
pooled over scoreable drivers in green races only (ticket 14's split tie
credit), with Neutralised-only and all-races figures reported alongside,
plus a race-averaged version of each so a few big races can't dominate
silently. Breakdowns are kept pooled (by season, by circuit, by sprint
weekend, and Tuning Seasons vs Held-out Season from the run's settings)
and add up to the totals. Each race also records how many (team,
Compound) Degradation estimates came from each source, which the
Backtest Result sums into a run-wide count. Every score shows numerator
and denominator.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .degradation import DegradationSource
from .predictor import NotDryRaceError, predict
from .scorer import RaceSummary, compare
from .settings import Settings
from .weekend import RaceWeekend

Loader = Callable[[int, str], RaceWeekend]
Progress = Callable[[str], None]


@dataclass(frozen=True)
class RaceSpec:
    """One race weekend to include in a Backtest."""

    season: int
    event: str
    is_sprint_weekend: bool = False


class ExclusionReason(Enum):
    """Why a race in the Backtest's scope produced no scores."""

    NOT_DRY_RACE = "not a Dry Race"
    PREDICTION_FAILED = "prediction failed"
    DATA_UNAVAILABLE = "data unavailable"


@dataclass(frozen=True)
class ExcludedRace:
    season: int
    event: str
    reason: ExclusionReason
    detail: str


@dataclass(frozen=True)
class RaceResult:
    """One scored race's record inside a Backtest Result.

    `degradation_sources` counts, over this race's unique teams and dry
    Compounds, how many per-team per-Compound Degradation estimates came
    from each `DegradationSource`. Summed across races, it is the run's
    "how often each Degradation source was used" (spec story 32).

    `estimated_pit_loss` is True when this race's Pit Loss was estimated
    from pit lane length and speed limit instead of measured from past
    races (ticket 07). Carried on the per-race record so the Backtest
    Result and the compare command can flag which races rest on an
    estimate (spec story 31).
    """

    season: int
    event: str
    circuit: str
    is_sprint_weekend: bool
    neutralised_race: bool
    summary: RaceSummary
    actual_stops: int
    degradation_sources: Mapping[DegradationSource, int] = field(
        default_factory=dict
    )
    estimated_pit_loss: bool = False


@dataclass(frozen=True)
class ScoreTotals:
    """A pooled score across a subset of races.

    `numerator`/`denominator` are the inputs the headline percentage reads;
    for Strategy Match the denominator is scoreable drivers, for Stop
    Window hits it is the number of actual stops those drivers made.
    """

    scoreable_drivers: int
    top_1_credit: float
    top_3_credit: float
    stop_window_hits: int
    actual_stops: int
    races: int


@dataclass(frozen=True)
class RaceAveraged:
    """Race-averaged (unweighted mean of per-race percentages) scores.

    Shown next to the pooled headline so a few big races can't dominate
    silently. `top_1_rate_sum` is the sum over contributing races of
    `top_1_credit / scoreable_drivers`, and the race-averaged percentage
    is `top_1_rate_sum / races_with_scoreable`. Races with no scoreable
    drivers don't contribute to the Strategy-Match averages; races with
    no actual stops don't contribute to the Stop-Window average.
    """

    top_1_rate_sum: float
    top_3_rate_sum: float
    stop_window_rate_sum: float
    races_with_scoreable: int
    races_with_stops: int


@dataclass(frozen=True)
class BacktestResult:
    """Everything one Backtest run produces.

    Aggregates are derivable from `races`, so a comparison or a future
    report can recompute them. `tuning_seasons` and `held_out_season` are
    carried from the run's `Settings`, not hard-coded into scoring.
    """

    races: tuple[RaceResult, ...]
    excluded: tuple[ExcludedRace, ...]
    green_headline: ScoreTotals
    neutralised: ScoreTotals
    all_races: ScoreTotals
    green_headline_averaged: RaceAveraged
    neutralised_averaged: RaceAveraged
    all_races_averaged: RaceAveraged
    by_season: Mapping[int, ScoreTotals]
    by_circuit: Mapping[str, ScoreTotals]
    by_sprint_weekend: Mapping[bool, ScoreTotals]
    tuning: ScoreTotals
    held_out: ScoreTotals
    tuning_seasons: tuple[int, ...]
    held_out_season: int | None
    degradation_source_counts: Mapping[DegradationSource, int]


def run_backtest(
    races: Sequence[RaceSpec],
    load: Loader,
    settings: Settings | None = None,
    progress: Progress | None = None,
) -> BacktestResult:
    """Load, predict and compare each race; aggregate into a Backtest Result.

    A refused race, a race whose prediction raises and a race whose loader
    raises each become an `ExcludedRace` with the right reason category,
    and the remaining races are still scored. Each race is passed to
    `predict()` and `compare()` in isolation, so one race's outcome never
    changes another race's prediction.
    """
    settings = settings or Settings()
    scored: list[RaceResult] = []
    excluded: list[ExcludedRace] = []
    for spec in races:
        if progress is not None:
            progress(f"{spec.season} {spec.event}")
        try:
            weekend = load(spec.season, spec.event)
        except Exception as error:
            excluded.append(
                ExcludedRace(
                    season=spec.season,
                    event=spec.event,
                    reason=ExclusionReason.DATA_UNAVAILABLE,
                    detail=str(error),
                )
            )
            continue
        try:
            predictions = predict(weekend, settings)
        except NotDryRaceError as refusal:
            excluded.append(
                ExcludedRace(
                    season=spec.season,
                    event=spec.event,
                    reason=ExclusionReason.NOT_DRY_RACE,
                    detail=str(refusal),
                )
            )
            continue
        except Exception as error:
            excluded.append(
                ExcludedRace(
                    season=spec.season,
                    event=spec.event,
                    reason=ExclusionReason.PREDICTION_FAILED,
                    detail=str(error),
                )
            )
            continue
        comparison = compare(predictions, weekend)
        actual_stops = sum(
            len(s.stop_window_hits)
            for s in comparison.scores.values()
            if not s.unscoreable
        )
        scored.append(
            RaceResult(
                season=spec.season,
                event=spec.event,
                circuit=weekend.pre_race.circuit,
                is_sprint_weekend=weekend.pre_race.is_sprint_weekend,
                neutralised_race=comparison.neutralised_race,
                summary=comparison.summary,
                actual_stops=actual_stops,
                degradation_sources=_count_degradation_sources(
                    predictions, weekend
                ),
            )
        )
    return BacktestResult(
        races=tuple(scored),
        excluded=tuple(excluded),
        green_headline=_totals(r for r in scored if not r.neutralised_race),
        neutralised=_totals(r for r in scored if r.neutralised_race),
        all_races=_totals(scored),
        green_headline_averaged=_race_averaged(
            r for r in scored if not r.neutralised_race
        ),
        neutralised_averaged=_race_averaged(
            r for r in scored if r.neutralised_race
        ),
        all_races_averaged=_race_averaged(scored),
        by_season=_group_totals(scored, key=lambda r: r.season),
        by_circuit=_group_totals(scored, key=lambda r: r.circuit),
        by_sprint_weekend=_group_totals(scored, key=lambda r: r.is_sprint_weekend),
        tuning=_totals(r for r in scored if r.season in settings.tuning_seasons),
        held_out=_totals(
            r for r in scored if r.season == settings.held_out_season
        ),
        tuning_seasons=tuple(settings.tuning_seasons),
        held_out_season=settings.held_out_season,
        degradation_source_counts=_sum_degradation_sources(scored),
    )


def _count_degradation_sources(
    predictions, weekend: RaceWeekend
) -> dict[DegradationSource, int]:
    """How many (team, Compound) Degradation estimates used each source.

    Teams, not drivers: two drivers on one team share the same estimates
    and would otherwise be double-counted.
    """
    counts: dict[DegradationSource, int] = {}
    seen_teams: set[str] = set()
    for driver, prediction in predictions.items():
        team = weekend.pre_race.teams.get(driver)
        if team is None or team in seen_teams:
            continue
        seen_teams.add(team)
        for estimate in prediction.team_degradation.values():
            counts[estimate.source] = counts.get(estimate.source, 0) + 1
    return counts


def _sum_degradation_sources(
    races: Sequence[RaceResult],
) -> dict[DegradationSource, int]:
    totals: dict[DegradationSource, int] = {}
    for race in races:
        for source, count in race.degradation_sources.items():
            totals[source] = totals.get(source, 0) + count
    return totals


def _totals(races) -> ScoreTotals:
    races = list(races)
    return ScoreTotals(
        scoreable_drivers=sum(r.summary.scoreable_drivers for r in races),
        top_1_credit=sum(r.summary.top_1_credit for r in races),
        top_3_credit=sum(r.summary.top_3_credit for r in races),
        stop_window_hits=sum(r.summary.stop_window_hits for r in races),
        actual_stops=sum(r.actual_stops for r in races),
        races=len(races),
    )


def _race_averaged(races) -> RaceAveraged:
    top_1 = 0.0
    top_3 = 0.0
    stop_window = 0.0
    with_scoreable = 0
    with_stops = 0
    for race in races:
        scoreable = race.summary.scoreable_drivers
        if scoreable:
            top_1 += race.summary.top_1_credit / scoreable
            top_3 += race.summary.top_3_credit / scoreable
            with_scoreable += 1
        if race.actual_stops:
            stop_window += race.summary.stop_window_hits / race.actual_stops
            with_stops += 1
    return RaceAveraged(
        top_1_rate_sum=top_1,
        top_3_rate_sum=top_3,
        stop_window_rate_sum=stop_window,
        races_with_scoreable=with_scoreable,
        races_with_stops=with_stops,
    )


def _group_totals(races, *, key) -> dict:
    groups: dict = {}
    for race in races:
        groups.setdefault(key(race), []).append(race)
    return {k: _totals(group) for k, group in groups.items()}


def format_backtest(result: BacktestResult) -> str:
    """A readable Backtest Result summary.

    The green-race headline comes first (split tie credit carries through),
    with its race-averaged counterpart beside it, then Neutralised-only
    and all-races figures. Below that, breakdowns by season, by circuit,
    by sprint weekend, and Tuning Seasons vs Held-out Season, followed by
    Degradation source counts. Every score shows its numerator and
    denominator; Excluded Races are listed last with reason and detail.
    """
    lines = [
        f"Races scored: {len(result.races)} "
        f"(green: {result.green_headline.races}, "
        f"Neutralised: {result.neutralised.races})",
        f"Excluded Races: {len(result.excluded)}",
        "",
        "Green-race headline (pooled over scoreable drivers):",
        *_totals_lines(result.green_headline),
        "",
        "Green-race headline (race-averaged):",
        *_averaged_lines(result.green_headline_averaged),
    ]
    if result.neutralised.races:
        lines += [
            "",
            "Neutralised Races only:",
            *_totals_lines(result.neutralised),
        ]
    lines += [
        "",
        "All races (green + Neutralised):",
        *_totals_lines(result.all_races),
    ]
    if result.by_season:
        lines += ["", "By season (pooled):"]
        for season in sorted(result.by_season):
            lines.append(f"  {season}:")
            lines += [f"  {line}" for line in _totals_lines(result.by_season[season])]
    if result.by_circuit:
        lines += ["", "By circuit (pooled):"]
        for circuit in sorted(result.by_circuit):
            lines.append(f"  {circuit}:")
            lines += [f"  {line}" for line in _totals_lines(result.by_circuit[circuit])]
    if result.by_sprint_weekend:
        lines += ["", "Sprint vs conventional (pooled):"]
        for is_sprint in sorted(result.by_sprint_weekend):
            label = "sprint" if is_sprint else "conventional"
            lines.append(f"  {label}:")
            lines += [
                f"  {line}"
                for line in _totals_lines(result.by_sprint_weekend[is_sprint])
            ]
    held_out = result.held_out_season
    held_out_label = (
        f"Held-out Season ({held_out})" if held_out is not None else "Held-out Season"
    )
    tuning_label = (
        "Tuning Seasons ("
        + ", ".join(str(s) for s in result.tuning_seasons)
        + ")"
        if result.tuning_seasons
        else "Tuning Seasons"
    )
    lines += [
        "",
        f"{tuning_label}:",
        *_totals_lines(result.tuning),
        "",
        f"{held_out_label}:",
        *_totals_lines(result.held_out),
    ]
    if result.degradation_source_counts:
        lines += ["", "Degradation source counts (team × Compound):"]
        for source in sorted(
            result.degradation_source_counts, key=lambda s: s.value
        ):
            count = result.degradation_source_counts[source]
            lines.append(f"  {source.value}: {count}")
    if result.excluded:
        lines += ["", "Excluded Races:"]
        for excluded in result.excluded:
            lines.append(
                f"  {excluded.season} {excluded.event}: "
                f"{excluded.reason.value} — {excluded.detail}"
            )
    return "\n".join(lines)


def _totals_lines(totals: ScoreTotals) -> list[str]:
    scoreable = totals.scoreable_drivers
    stops = totals.actual_stops
    return [
        f"  Top-1 Strategy Match: {_credit(totals.top_1_credit, scoreable)}",
        f"  Top-3 Strategy Match: {_credit(totals.top_3_credit, scoreable)}",
        f"  Stop Window hits: {_hits(totals.stop_window_hits, stops)}",
    ]


def _averaged_lines(averaged: RaceAveraged) -> list[str]:
    return [
        f"  Top-1 Strategy Match: "
        f"{_mean_rate(averaged.top_1_rate_sum, averaged.races_with_scoreable)}",
        f"  Top-3 Strategy Match: "
        f"{_mean_rate(averaged.top_3_rate_sum, averaged.races_with_scoreable)}",
        f"  Stop Window hits: "
        f"{_mean_rate(averaged.stop_window_rate_sum, averaged.races_with_stops)}",
    ]


def _credit(credit: float, denominator: int) -> str:
    rounded = round(credit, 6)
    numerator: str = (
        str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"
    )
    pct = f" ({credit / denominator:.0%})" if denominator else ""
    return f"{numerator}/{denominator}{pct}"


def _hits(hits: int, denominator: int) -> str:
    pct = f" ({hits / denominator:.0%})" if denominator else ""
    return f"{hits}/{denominator} actual stops{pct}"


def _mean_rate(rate_sum: float, denominator: int) -> str:
    if not denominator:
        return "— (0 races)"
    mean = rate_sum / denominator
    return f"mean {mean:.0%} over {denominator} race(s)"
