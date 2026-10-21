"""Plain-text report of Pre-race Predictions against the actual race.

`format_table` prints one block per driver: their top Candidate Strategies
with probabilities and Stop Windows, then on the driver's first line the
actual Strategy and how it scored. `format_summary` prints the race summary.
"""

from dataclasses import fields
from fractions import Fraction

from .degradation import DegradationSource
from .predictor import CandidateStrategy, RemainingSetsRule, StrategyPrediction
from .regulation_era import era_start
from .scorer import DriverScore, RaceComparison
from .settings import Settings
from .weekend import DRY_COMPOUNDS, Compound, PreRaceInfo

TOP_SHOWN = 3

_HEADER = (
    f"{'Driver':<8}{'#':<3}{'Candidate Strategy':<24}{'Prob':>5}  "
    f"{'Stop Windows':<22}{'Actual Strategy':<36}Result"
)


def strategy_label(compounds: tuple[Compound, ...]) -> str:
    """A Strategy as commentators say it, e.g. "1-stop: M → H"."""
    return f"{len(compounds) - 1}-stop: " + " → ".join(c.value for c in compounds)


def format_header(
    pre_race: PreRaceInfo,
    settings: Settings,
    predictions: dict[str, StrategyPrediction] | None = None,
) -> str:
    used = ", ".join(f"{f.name}={getattr(settings, f.name)}" for f in fields(settings))
    parts = [
        f"{pre_race.season} {pre_race.circuit}: {pre_race.race_laps} laps, "
        f"Pit Loss {pre_race.pit_loss:.1f} s",
        f"Settings: {used}",
    ]
    if pre_race.estimated_pit_loss:
        parts.append(
            "Pit Loss estimated from pit lane length and speed limit "
            "(ticket 07, no circuit history)"
        )
    else:
        pre_era_seasons = _pit_loss_pre_era_seasons(pre_race)
        if pre_era_seasons:
            parts.append(
                "Pit Loss from pre-era seasons "
                f"{_season_list(pre_era_seasons)} (ADR-0004 exception)"
            )
    if predictions:
        fallback = _historical_fallback_lines(pre_race, predictions)
        if fallback:
            parts.append("Historical Degradation fallbacks:")
            parts.extend(f"  {line}" for line in fallback)
    return "\n".join(parts)


def _historical_fallback_lines(
    pre_race: PreRaceInfo,
    predictions: dict[str, StrategyPrediction],
) -> list[str]:
    """One line per dry Compound whose field-level fallback was circuit
    history or the next-softer bound. Teams that have no own data on a
    Compound all share the same source for it, so reading the first
    prediction suffices.
    """
    if not predictions:
        return []
    first = next(iter(predictions.values()))
    lines: list[str] = []
    for compound in DRY_COMPOUNDS:
        estimate = first.team_degradation[compound]
        if estimate.source is DegradationSource.CIRCUIT_HISTORY:
            hist = pre_race.historical_degradation.get(compound)
            provenance = (
                f"circuit history: seasons {_season_list(hist.seasons)}, "
                f"{hist.stint_count} Stints"
                if hist
                else "circuit history"
            )
            lines.append(
                f"{compound.name.title()}: {estimate.rate:.3f} s/lap ({provenance})"
            )
        elif estimate.source is DegradationSource.NEXT_SOFTER_BOUND:
            idx = DRY_COMPOUNDS.index(compound)
            softer = DRY_COMPOUNDS[idx - 1].name.title()
            lines.append(
                f"{compound.name.title()}: {estimate.rate:.3f} s/lap "
                f"(next-softer bound from {softer})"
            )
    return lines


def _season_list(seasons: tuple[int, ...]) -> str:
    return ", ".join(str(s) for s in seasons)


def _pit_loss_pre_era_seasons(pre_race: PreRaceInfo) -> tuple[int, ...]:
    """Seasons used for Pit Loss that fall before the race's Regulation Era.

    Non-empty only when the ADR-0004 Pit Loss exception kicked in (first-
    season race at a circuit with no same-era history). Same-era-only Pit
    Loss leaves it empty, so the header stays unchanged.
    """
    if not pre_race.pit_loss_seasons:
        return ()
    try:
        era = era_start(pre_race.season)
    except ValueError:
        return ()
    return tuple(s for s in pre_race.pit_loss_seasons if s < era)


def format_table(
    predictions: dict[str, StrategyPrediction], comparison: RaceComparison
) -> str:
    lines = [_HEADER, "-" * len(_HEADER)]
    for driver, prediction in predictions.items():
        score = comparison.scores[driver]
        rule_note = _rule_note(prediction.remaining_sets_rule)
        for rank, candidate in enumerate(prediction.candidates[:TOP_SHOWN], start=1):
            first_column = driver if rank == 1 else ""
            row = f"{first_column:<8}{rank:<3}{_candidate_columns(candidate)}"
            if rank == 1:
                row += _score_columns(score)
                if rule_note:
                    row = row.rstrip() + f"  [{rule_note}]"
            lines.append(row.rstrip())
    return "\n".join(lines)


def _rule_note(rule: RemainingSetsRule) -> str:
    return "" if rule is RemainingSetsRule.NEW_ONLY else rule.value


def format_summary(comparison: RaceComparison) -> str:
    summary = comparison.summary
    scoreable = summary.scoreable_drivers
    actual_stops = sum(
        len(s.stop_window_hits) for s in comparison.scores.values() if not s.unscoreable
    )
    return "\n".join(
        [
            f"Scoreable drivers: {scoreable} of {len(comparison.scores)}",
            f"Top-1 Strategy Match: {_credit_count(summary.top_1_credit, scoreable)}",
            f"Top-3 Strategy Match: {_credit_count(summary.top_3_credit, scoreable)}",
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
        f"{actual:<36}top-1 {_credit(score.top_1_credit)} · "
        f"top-3 {_credit(score.top_3_credit)} · Stop Window hits {hits}"
    )


def _count(part: int, whole: int, unit: str = "") -> str:
    of = f"{part}/{whole}" + (f" {unit}" if unit else "")
    return f"{of} ({part / whole:.0%})" if whole else of


def _credit_count(part: float, whole: int, unit: str = "") -> str:
    numerator = _credit_total(part)
    of = f"{numerator}/{whole}" + (f" {unit}" if unit else "")
    return f"{of} ({part / whole:.0%})" if whole else of


def _credit(credit: float) -> str:
    """Fraction string for a per-driver credit, e.g. "1", "0", "1/2"."""
    fraction = Fraction(credit).limit_denominator(100)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    return f"{fraction.numerator}/{fraction.denominator}"


def _credit_total(total: float) -> str:
    """A sum of credits for the race summary. Shown as an integer when whole,
    else to one decimal (e.g. 2.5)."""
    rounded = round(total, 6)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"
