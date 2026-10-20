"""Plain-text report of Pre-race Predictions against the actual race.

`format_table` prints one block per driver: their top Candidate Strategies
with probabilities and Stop Windows, then on the driver's first line the
actual Strategy and how it scored. `format_summary` prints the race summary.
"""

from dataclasses import fields

from .predictor import CandidateStrategy, StrategyPrediction
from .scorer import DriverScore, RaceComparison
from .settings import Settings
from .weekend import Compound, PreRaceInfo

TOP_SHOWN = 3

_HEADER = (
    f"{'Driver':<8}{'#':<3}{'Candidate Strategy':<24}{'Prob':>5}  "
    f"{'Stop Windows':<22}{'Actual Strategy':<36}Result"
)


def strategy_label(compounds: tuple[Compound, ...]) -> str:
    """A Strategy as commentators say it, e.g. "1-stop: M → H"."""
    return f"{len(compounds) - 1}-stop: " + " → ".join(c.value for c in compounds)


def format_header(pre_race: PreRaceInfo, settings: Settings) -> str:
    used = ", ".join(f"{f.name}={getattr(settings, f.name)}" for f in fields(settings))
    return (
        f"{pre_race.season} {pre_race.circuit}: {pre_race.race_laps} laps, "
        f"Pit Loss {pre_race.pit_loss:.1f} s\n"
        f"Settings: {used}"
    )


def format_table(
    predictions: dict[str, StrategyPrediction], comparison: RaceComparison
) -> str:
    lines = [_HEADER, "-" * len(_HEADER)]
    for driver, prediction in predictions.items():
        score = comparison.scores[driver]
        for rank, candidate in enumerate(prediction.candidates[:TOP_SHOWN], start=1):
            first_column = driver if rank == 1 else ""
            row = f"{first_column:<8}{rank:<3}{_candidate_columns(candidate)}"
            if rank == 1:
                row += _score_columns(score)
            lines.append(row.rstrip())
    return "\n".join(lines)


def format_summary(comparison: RaceComparison) -> str:
    summary = comparison.summary
    scoreable = summary.scoreable_drivers
    actual_stops = sum(
        len(s.stop_window_hits) for s in comparison.scores.values() if not s.unscoreable
    )
    return "\n".join(
        [
            f"Scoreable drivers: {scoreable} of {len(comparison.scores)}",
            f"Top-1 Strategy Match: {_count(summary.top_1_matches, scoreable)}",
            f"Top-3 Strategy Match: {_count(summary.top_3_matches, scoreable)}",
            "Stop Window hits: "
            f"{_count(summary.stop_window_hits, actual_stops, 'actual stops')}",
            f"Neutralised Race: {'yes' if comparison.neutralised_race else 'no'}",
        ]
    )


def _candidate_columns(candidate: CandidateStrategy) -> str:
    windows = ", ".join(f"{s.first_lap}–{s.last_lap}" for s in candidate.stops)
    return (
        f"{strategy_label(candidate.strategy.compounds):<24}"
        f"{candidate.probability:>5.0%}  {windows:<22}"
    )


def _score_columns(score: DriverScore) -> str:
    if score.unscoreable or score.actual is None:
        return f"{'—':<36}unscoreable"
    stop_laps = score.actual.stop_laps
    laps = f"lap {stop_laps[0]}" if len(stop_laps) == 1 else (
        "laps " + ", ".join(str(lap) for lap in stop_laps)
    )
    actual = f"{strategy_label(score.actual.compounds)} ({laps})"
    hits = f"{sum(score.stop_window_hits)}/{len(score.stop_window_hits)}"
    return (
        f"{actual:<36}top-1 {_yes_no(score.top_1_match)} · "
        f"top-3 {_yes_no(score.top_3_match)} · Stop Window hits {hits}"
    )


def _count(part: int, whole: int, unit: str = "") -> str:
    of = f"{part}/{whole}" + (f" {unit}" if unit else "")
    return f"{of} ({part / whole:.0%})" if whole else of


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"
