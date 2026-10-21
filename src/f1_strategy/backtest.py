"""Backtest: run Pre-race Predictions over a list of race weekends and score them.

One public call, `run_backtest`, takes a list of race specs, an injectable
loader function and settings, and returns a `BacktestResult`. For each race
it loads, predicts and compares using the existing `predict()` and
`compare()` unchanged. A refused race (not a Dry Race), a race whose
prediction raises, and a race whose loader raises each become an
`ExcludedRace` with a reason category and detail; the loop carries on.

Aggregates are derivable from the per-race records: the headline score is
pooled over scoreable drivers in green races only (ticket 14's split tie
credit), with Neutralised-only and all-races figures reported alongside.
Every score shows numerator and denominator.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

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
    """One scored race's record inside a Backtest Result."""

    season: int
    event: str
    circuit: str
    is_sprint_weekend: bool
    neutralised_race: bool
    summary: RaceSummary
    actual_stops: int


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
class BacktestResult:
    races: tuple[RaceResult, ...]
    excluded: tuple[ExcludedRace, ...]
    green_headline: ScoreTotals
    neutralised: ScoreTotals
    all_races: ScoreTotals


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
            )
        )
    return BacktestResult(
        races=tuple(scored),
        excluded=tuple(excluded),
        green_headline=_totals(r for r in scored if not r.neutralised_race),
        neutralised=_totals(r for r in scored if r.neutralised_race),
        all_races=_totals(scored),
    )


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


def format_backtest(result: BacktestResult) -> str:
    """A readable Backtest Result summary.

    The green-race headline comes first (split tie credit carries through),
    with Neutralised-only and all-races figures beneath it. Every score
    shows its numerator and denominator. Excluded Races are listed last
    with their reason category and detail.
    """
    lines = [
        f"Races scored: {len(result.races)} "
        f"(green: {result.green_headline.races}, "
        f"Neutralised: {result.neutralised.races})",
        f"Excluded Races: {len(result.excluded)}",
        "",
        "Green-race headline (pooled over scoreable drivers):",
        *_totals_lines(result.green_headline),
    ]
    if result.neutralised.races:
        lines += ["", "Neutralised Races only:", *_totals_lines(result.neutralised)]
    lines += ["", "All races (green + Neutralised):", *_totals_lines(result.all_races)]
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
