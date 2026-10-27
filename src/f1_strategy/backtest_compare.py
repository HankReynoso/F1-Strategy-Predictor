"""Compare two Backtest Results.

One public call, `compare_backtest_results`, takes two `BacktestResult`s
(and the `RunMetadata` of each, when available) and returns a
`BacktestComparison`: every headline score and every breakdown's before,
after and change; the races whose credit moved most in each direction;
and warnings when the two runs don't cover like-for-like scope.

Diffs run pairwise over `ScoreTotals` and `RaceAveraged`, since every
aggregate is already derivable from the per-race records (ADR-0005).
Breakdown keys present in only one side are reported as added or removed
rather than crashing; the pooled aggregate for the missing side is None,
so the formatter can show "—" for the half that doesn't exist.

Warnings cover the four scope dimensions a diff that silently papers
over would mislead a reader (tickets 04 and 05's review feedback):

- `metadata.seasons_in_scope` differ
- the run's `tuning_seasons` / `held_out_season` partition differs
- the set of races that were scored vs excluded differs
- the set of races whose Pit Loss was estimated (ticket 07) differs,
  since the two runs are comparing a measured race on one side and an
  estimate on the other
- the Data Quality Warnings (tickets 28, 30) of a race scored on both sides
  differ, since the two runs scored it on different data; when a side was
  read from a format-version-1 file, which never saved its warnings, that
  is said once instead
- either side was read from a file before format version 3, which never
  saved Predicted-Strategy Stops, so Stop Window hits on predicted
  Strategies and Stop Window width can't be compared (ticket 58)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .backtest import (
    BacktestResult,
    RaceAveraged,
    RaceResult,
    ScoreTotals,
)
from .backtest_io import RunMetadata


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreChange:
    """Pooled score before and after, with the change in percentage points.

    `change_pp` is None when either side has a zero denominator — the
    percentage is undefined there and a fabricated delta would mislead.
    """

    label: str
    before_numerator: float
    before_denominator: int
    after_numerator: float
    after_denominator: int
    before_pct: float | None
    after_pct: float | None
    change_pp: float | None


@dataclass(frozen=True)
class AveragedChange:
    """Race-averaged score before and after.

    `before_mean` / `after_mean` are the mean per-race rates (0.0–1.0),
    with the per-race denominator carried as `*_races`. `change_pp` is
    None when either side had no contributing races.
    """

    label: str
    before_mean: float | None
    after_mean: float | None
    before_races: int
    after_races: int
    change_pp: float | None


@dataclass(frozen=True)
class WidthChange:
    """Average Stop Window width before and after, in laps.

    Pooled, `*_total` is the summed width of the Stop Windows of
    Predicted-Strategy Stops and `*_count` is those stops. Race-averaged,
    `*_total` sums each race's average width and `*_count` is the races
    with at least one Predicted-Strategy Stop. `*_mean` is total / count,
    and `change_laps` is None when either side's count is zero.
    """

    label: str
    before_total: float
    before_count: int
    after_total: float
    after_count: int
    before_mean: float | None
    after_mean: float | None
    change_laps: float | None


@dataclass(frozen=True)
class ScoreBucketDiff:
    """Every headline score for one bucket (pooled).

    `predicted_strategy_stop_window` and `stop_window_width` are None when
    either side didn't record its Predicted-Strategy Stops (a file before
    format version 3).
    """

    label: str
    top_1: ScoreChange
    top_3: ScoreChange
    stop_window: ScoreChange
    predicted_strategy_stop_window: ScoreChange | None
    stop_window_width: WidthChange | None


@dataclass(frozen=True)
class AveragedBucketDiff:
    label: str
    top_1: AveragedChange
    top_3: AveragedChange
    stop_window: AveragedChange
    predicted_strategy_stop_window: AveragedChange | None
    stop_window_width: WidthChange | None


@dataclass(frozen=True)
class RaceMovement:
    """One race's change in top-1 Strategy-Match rate between two runs.

    `rate` is `top_1_credit / scoreable_drivers`; the per-race rate is the
    same quantity `_race_averaged` sums over races. Only races present in
    both runs with scoreable drivers on both sides contribute.
    """

    season: int
    event: str
    circuit: str
    before_rate: float
    after_rate: float
    change_pp: float


@dataclass(frozen=True)
class BacktestComparison:
    """Every change between two Backtest Results."""

    pooled: tuple[ScoreBucketDiff, ...]
    averaged: tuple[AveragedBucketDiff, ...]
    by_season: Mapping[int, ScoreBucketDiff]
    by_circuit: Mapping[str, ScoreBucketDiff]
    by_sprint_weekend: Mapping[bool, ScoreBucketDiff]
    top_gainers: tuple[RaceMovement, ...]
    top_losers: tuple[RaceMovement, ...]
    warnings: tuple[str, ...]
    # "before" and/or "after": the sides that didn't record
    # Predicted-Strategy Stops, for the formatter's "not recorded" lines.
    predicted_strategy_stops_not_recorded_in: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compare_backtest_results(
    before: BacktestResult,
    after: BacktestResult,
    *,
    before_metadata: RunMetadata | None = None,
    after_metadata: RunMetadata | None = None,
    top_n: int = 5,
) -> BacktestComparison:
    """Return every score change and the biggest-moving races.

    `top_n` caps the number of races listed in each direction. Metadata
    is optional — when both sides are provided, scope warnings about
    `seasons_in_scope` and `Settings`-based partitioning are added.
    """
    pooled = (
        _bucket("Green-race headline", before.green_headline, after.green_headline),
        _bucket("Neutralised Races", before.neutralised, after.neutralised),
        _bucket("All races", before.all_races, after.all_races),
        _bucket("Tuning Seasons", before.tuning, after.tuning),
        _bucket("Held-out Season", before.held_out, after.held_out),
    )
    averaged = (
        _averaged_bucket(
            "Green-race headline",
            before.green_headline_averaged,
            after.green_headline_averaged,
        ),
        _averaged_bucket(
            "Neutralised Races",
            before.neutralised_averaged,
            after.neutralised_averaged,
        ),
        _averaged_bucket(
            "All races",
            before.all_races_averaged,
            after.all_races_averaged,
        ),
    )
    empties = (_empty_like(before.all_races), _empty_like(after.all_races))
    by_season = _diff_breakdown(
        before.by_season, after.by_season, key_label=str, empties=empties
    )
    by_circuit = _diff_breakdown(
        before.by_circuit, after.by_circuit, key_label=str, empties=empties
    )
    by_sprint = _diff_breakdown(
        before.by_sprint_weekend,
        after.by_sprint_weekend,
        key_label=lambda k: "sprint" if k else "conventional",
        empties=empties,
    )

    movements = _race_movements(before.races, after.races)
    gainers = tuple(
        m for m in sorted(movements, key=lambda m: -m.change_pp) if m.change_pp > 0
    )[:top_n]
    losers = tuple(
        m for m in sorted(movements, key=lambda m: m.change_pp) if m.change_pp < 0
    )[:top_n]

    not_recorded = tuple(
        side
        for side, result in (("before", before), ("after", after))
        if result.all_races.predicted_strategy_stops is None
    )
    warnings = _scope_warnings(before, after, before_metadata, after_metadata)

    return BacktestComparison(
        pooled=pooled,
        averaged=averaged,
        by_season=by_season,
        by_circuit=by_circuit,
        by_sprint_weekend=by_sprint,
        top_gainers=gainers,
        top_losers=losers,
        warnings=warnings,
        predicted_strategy_stops_not_recorded_in=not_recorded,
    )


# ---------------------------------------------------------------------------
# Pooled score diffs
# ---------------------------------------------------------------------------


def _bucket(label: str, before: ScoreTotals, after: ScoreTotals) -> ScoreBucketDiff:
    return ScoreBucketDiff(
        label=label,
        top_1=_score_change(
            "Top-1 Strategy Match",
            before.top_1_credit, before.scoreable_drivers,
            after.top_1_credit, after.scoreable_drivers,
        ),
        top_3=_score_change(
            "Top-3 Strategy Match",
            before.top_3_credit, before.scoreable_drivers,
            after.top_3_credit, after.scoreable_drivers,
        ),
        stop_window=_score_change(
            "Stop Window hits",
            before.stop_window_hits, before.actual_stops,
            after.stop_window_hits, after.actual_stops,
        ),
        predicted_strategy_stop_window=(
            _score_change(
                _PREDICTED_STRATEGY_HITS,
                before.stop_window_hits, before.predicted_strategy_stops,
                after.stop_window_hits, after.predicted_strategy_stops,
            )
            if _both_recorded(before, after)
            else None
        ),
        stop_window_width=(
            _width_change(
                before.stop_window_laps, before.predicted_strategy_stops,
                after.stop_window_laps, after.predicted_strategy_stops,
            )
            if _both_recorded(before, after)
            else None
        ),
    )


_PREDICTED_STRATEGY_HITS = "Stop Window hits on predicted Strategies"
_WIDTH = "Average Stop Window width"


def _both_recorded(before: ScoreTotals, after: ScoreTotals) -> bool:
    return (
        before.predicted_strategy_stops is not None
        and after.predicted_strategy_stops is not None
    )


def _width_change(
    before_total: float,
    before_count: int,
    after_total: float,
    after_count: int,
) -> WidthChange:
    before_mean = (before_total / before_count) if before_count else None
    after_mean = (after_total / after_count) if after_count else None
    change_laps: float | None
    if before_mean is None or after_mean is None:
        change_laps = None
    else:
        change_laps = after_mean - before_mean
    return WidthChange(
        label=_WIDTH,
        before_total=before_total,
        before_count=before_count,
        after_total=after_total,
        after_count=after_count,
        before_mean=before_mean,
        after_mean=after_mean,
        change_laps=change_laps,
    )


def _score_change(
    label: str,
    before_num: float,
    before_den: int,
    after_num: float,
    after_den: int,
) -> ScoreChange:
    before_pct = (before_num / before_den) if before_den else None
    after_pct = (after_num / after_den) if after_den else None
    change_pp: float | None
    if before_pct is None or after_pct is None:
        change_pp = None
    else:
        change_pp = after_pct - before_pct
    return ScoreChange(
        label=label,
        before_numerator=before_num,
        before_denominator=before_den,
        after_numerator=after_num,
        after_denominator=after_den,
        before_pct=before_pct,
        after_pct=after_pct,
        change_pp=change_pp,
    )


# ---------------------------------------------------------------------------
# Race-averaged diffs
# ---------------------------------------------------------------------------


def _averaged_bucket(
    label: str, before: RaceAveraged, after: RaceAveraged
) -> AveragedBucketDiff:
    recorded = (
        before.races_with_predicted_strategy_stops is not None
        and after.races_with_predicted_strategy_stops is not None
    )
    return AveragedBucketDiff(
        label=label,
        top_1=_averaged_change(
            "Top-1 Strategy Match",
            before.top_1_rate_sum, before.races_with_scoreable,
            after.top_1_rate_sum, after.races_with_scoreable,
        ),
        top_3=_averaged_change(
            "Top-3 Strategy Match",
            before.top_3_rate_sum, before.races_with_scoreable,
            after.top_3_rate_sum, after.races_with_scoreable,
        ),
        stop_window=_averaged_change(
            "Stop Window hits",
            before.stop_window_rate_sum, before.races_with_stops,
            after.stop_window_rate_sum, after.races_with_stops,
        ),
        predicted_strategy_stop_window=(
            _averaged_change(
                _PREDICTED_STRATEGY_HITS,
                before.predicted_strategy_hit_rate_sum,
                before.races_with_predicted_strategy_stops,
                after.predicted_strategy_hit_rate_sum,
                after.races_with_predicted_strategy_stops,
            )
            if recorded
            else None
        ),
        stop_window_width=(
            _width_change(
                before.stop_window_width_sum,
                before.races_with_predicted_strategy_stops,
                after.stop_window_width_sum,
                after.races_with_predicted_strategy_stops,
            )
            if recorded
            else None
        ),
    )


def _averaged_change(
    label: str,
    before_sum: float,
    before_races: int,
    after_sum: float,
    after_races: int,
) -> AveragedChange:
    before_mean = (before_sum / before_races) if before_races else None
    after_mean = (after_sum / after_races) if after_races else None
    change_pp: float | None
    if before_mean is None or after_mean is None:
        change_pp = None
    else:
        change_pp = after_mean - before_mean
    return AveragedChange(
        label=label,
        before_mean=before_mean,
        after_mean=after_mean,
        before_races=before_races,
        after_races=after_races,
        change_pp=change_pp,
    )


# ---------------------------------------------------------------------------
# Breakdowns
# ---------------------------------------------------------------------------


def _empty_like(totals: ScoreTotals) -> ScoreTotals:
    """An empty bucket for a breakdown key missing on one side.

    Predicted-Strategy Stops stay not recorded (None) when that side's
    result never recorded them, so the missing key doesn't read as 0 stops.
    """
    recorded = totals.predicted_strategy_stops is not None
    return ScoreTotals(
        0, 0.0, 0.0, 0, 0, 0,
        predicted_strategy_stops=0 if recorded else None,
        stop_window_laps=0 if recorded else None,
    )


def _diff_breakdown(
    before: Mapping[Any, ScoreTotals],
    after: Mapping[Any, ScoreTotals],
    *,
    key_label,
    empties: tuple[ScoreTotals, ScoreTotals],
) -> dict[Any, ScoreBucketDiff]:
    """Pairwise score diffs per group key, including keys present on only one side.

    A key only in `before` has an empty `after` bucket (zero everything,
    percentage None); a key only in `after` has an empty `before`. The
    caller renders those as "removed" and "added" respectively. `empties`
    is the (before, after) empty bucket.
    """
    empty_before, empty_after = empties
    keys = sorted(set(before) | set(after), key=key_label)
    return {
        key: _bucket(
            key_label(key),
            before.get(key, empty_before),
            after.get(key, empty_after),
        )
        for key in keys
    }


# ---------------------------------------------------------------------------
# Biggest-moving races
# ---------------------------------------------------------------------------


def _race_movements(
    before: tuple[RaceResult, ...], after: tuple[RaceResult, ...]
) -> list[RaceMovement]:
    before_by_key = {(r.season, r.event): r for r in before}
    movements: list[RaceMovement] = []
    for after_race in after:
        key = (after_race.season, after_race.event)
        before_race = before_by_key.get(key)
        if before_race is None:
            continue
        if not before_race.summary.scoreable_drivers:
            continue
        if not after_race.summary.scoreable_drivers:
            continue
        before_rate = (
            before_race.summary.top_1_credit / before_race.summary.scoreable_drivers
        )
        after_rate = (
            after_race.summary.top_1_credit / after_race.summary.scoreable_drivers
        )
        change = after_rate - before_rate
        if change == 0:
            continue
        movements.append(
            RaceMovement(
                season=after_race.season,
                event=after_race.event,
                circuit=after_race.circuit,
                before_rate=before_rate,
                after_rate=after_rate,
                change_pp=change,
            )
        )
    return movements


# ---------------------------------------------------------------------------
# Scope warnings
# ---------------------------------------------------------------------------


def _scope_warnings(
    before: BacktestResult,
    after: BacktestResult,
    before_metadata: RunMetadata | None,
    after_metadata: RunMetadata | None,
) -> tuple[str, ...]:
    warnings: list[str] = []

    scored_before = {(r.season, r.event) for r in before.races}
    scored_after = {(r.season, r.event) for r in after.races}
    if scored_before != scored_after:
        only_before = sorted(scored_before - scored_after)
        only_after = sorted(scored_after - scored_before)
        detail = []
        if only_before:
            detail.append(
                "only in before: " + ", ".join(f"{s} {e}" for s, e in only_before)
            )
        if only_after:
            detail.append(
                "only in after: " + ", ".join(f"{s} {e}" for s, e in only_after)
            )
        warnings.append(
            "Scored races differ between the two Backtest Results ("
            + "; ".join(detail)
            + ")"
        )

    excluded_before = {(r.season, r.event, r.reason.value) for r in before.excluded}
    excluded_after = {(r.season, r.event, r.reason.value) for r in after.excluded}
    if excluded_before != excluded_after:
        only_before = sorted(excluded_before - excluded_after)
        only_after = sorted(excluded_after - excluded_before)
        detail = []
        if only_before:
            detail.append(
                "only in before: "
                + ", ".join(f"{s} {e} ({r})" for s, e, r in only_before)
            )
        if only_after:
            detail.append(
                "only in after: "
                + ", ".join(f"{s} {e} ({r})" for s, e, r in only_after)
            )
        warnings.append(
            "Excluded Races differ between the two Backtest Results ("
            + "; ".join(detail)
            + ")"
        )

    estimated_before = {
        (r.season, r.event) for r in before.races if r.estimated_pit_loss
    }
    estimated_after = {
        (r.season, r.event) for r in after.races if r.estimated_pit_loss
    }
    # Only warn when the race was scored on both sides but the Pit Loss
    # provenance flipped — the "scored races differ" warning already covers
    # races that appear on only one side.
    shared = scored_before & scored_after
    flipped = (estimated_before ^ estimated_after) & shared
    if flipped:
        warnings.append(
            "Races with an estimated Pit Loss differ between the two Backtest "
            "Results (" + ", ".join(f"{s} {e}" for s, e in sorted(flipped)) + ")"
        )

    warnings.extend(
        _data_quality_warnings_diff(
            before, after, shared, before_metadata, after_metadata
        )
    )
    warnings.extend(
        _predicted_strategy_stops_unrecorded(
            before, after, before_metadata, after_metadata
        )
    )

    if before.tuning_seasons != after.tuning_seasons:
        warnings.append(
            f"Tuning Seasons differ: before={list(before.tuning_seasons)}, "
            f"after={list(after.tuning_seasons)}"
        )
    if before.held_out_season != after.held_out_season:
        warnings.append(
            f"Held-out Season differs: before={before.held_out_season}, "
            f"after={after.held_out_season}"
        )

    if before_metadata is not None and after_metadata is not None:
        if before_metadata.seasons_in_scope != after_metadata.seasons_in_scope:
            warnings.append(
                "Seasons in scope differ: "
                f"before={list(before_metadata.seasons_in_scope)}, "
                f"after={list(after_metadata.seasons_in_scope)}"
            )

    return tuple(warnings)


def _data_quality_warnings_diff(
    before: BacktestResult,
    after: BacktestResult,
    shared: set[tuple[int, str]],
    before_metadata: RunMetadata | None,
    after_metadata: RunMetadata | None,
) -> list[str]:
    unsaved = [
        side
        for side, metadata in (("before", before_metadata), ("after", after_metadata))
        if metadata is not None and metadata.format_version < 2
    ]
    if unsaved:
        # Every warned race on the other side would differ for no reason.
        verb = "was" if len(unsaved) == 1 else "were"
        return [
            f"Data Quality Warnings can't be compared: {' and '.join(unsaved)} "
            f"{verb} saved in format version 1, which didn't record them"
        ]
    warnings_before = {(r.season, r.event): r.history_warnings for r in before.races}
    warnings_after = {(r.season, r.event): r.history_warnings for r in after.races}
    differing = sorted(
        key for key in shared if warnings_before[key] != warnings_after[key]
    )
    if not differing:
        return []
    return [
        "Data Quality Warnings differ between the two Backtest Results ("
        + ", ".join(f"{s} {e}" for s, e in differing)
        + ")"
    ]


def _predicted_strategy_stops_unrecorded(
    before: BacktestResult,
    after: BacktestResult,
    before_metadata: RunMetadata | None,
    after_metadata: RunMetadata | None,
) -> list[str]:
    unrecorded = [
        (side, metadata)
        for side, result, metadata in (
            ("before", before, before_metadata),
            ("after", after, after_metadata),
        )
        if result.all_races.predicted_strategy_stops is None
    ]
    if not unrecorded:
        return []
    versions = sorted(
        {metadata.format_version for _, metadata in unrecorded if metadata}
    )
    if versions and all(metadata for _, metadata in unrecorded):
        noun = "format version" if len(versions) == 1 else "format versions"
        saved_in = f"{noun} {' and '.join(map(str, versions))}"
    else:
        saved_in = "a format version before 3"
    verb = "was" if len(unrecorded) == 1 else "were"
    return [
        f"{_PREDICTED_STRATEGY_HITS} and Stop Window width can't be compared: "
        f"{' and '.join(side for side, _ in unrecorded)} {verb} saved in "
        f"{saved_in}, which didn't record them"
    ]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_comparison(comparison: BacktestComparison) -> str:
    """A readable Backtest Result comparison.

    Headline buckets first (pooled, then race-averaged), then breakdowns
    by season / circuit / sprint, then the biggest-moving races in each
    direction, then any scope warnings at the end so a reader doesn't
    miss them.
    """
    lines: list[str] = []
    if comparison.warnings:
        lines.append("WARNINGS:")
        for w in comparison.warnings:
            lines.append(f"  ! {w}")
        lines.append("")

    not_recorded = comparison.predicted_strategy_stops_not_recorded_in
    lines.append("Headline (pooled):")
    for bucket in comparison.pooled:
        lines += _bucket_lines(bucket, not_recorded)
    lines.append("")

    lines.append("Headline (race-averaged):")
    for bucket in comparison.averaged:
        lines += _averaged_bucket_lines(bucket, not_recorded)
    lines.append("")

    if comparison.by_season:
        lines.append("By season:")
        for key in sorted(comparison.by_season):
            lines += _bucket_lines(comparison.by_season[key], not_recorded)
        lines.append("")

    if comparison.by_circuit:
        lines.append("By circuit:")
        for key in sorted(comparison.by_circuit):
            lines += _bucket_lines(comparison.by_circuit[key], not_recorded)
        lines.append("")

    if comparison.by_sprint_weekend:
        lines.append("Sprint vs conventional:")
        for key in sorted(comparison.by_sprint_weekend):
            lines += _bucket_lines(comparison.by_sprint_weekend[key], not_recorded)
        lines.append("")

    lines.append("Biggest gainers (top-1 Strategy Match rate):")
    if comparison.top_gainers:
        for m in comparison.top_gainers:
            lines.append(f"  {_movement_line(m)}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Biggest losers (top-1 Strategy Match rate):")
    if comparison.top_losers:
        for m in comparison.top_losers:
            lines.append(f"  {_movement_line(m)}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def _bucket_lines(
    bucket: ScoreBucketDiff, not_recorded: tuple[str, ...]
) -> list[str]:
    return [
        f"  {bucket.label}:",
        f"    {_score_change_line(bucket.top_1)}",
        f"    {_score_change_line(bucket.top_3)}",
        f"    {_score_change_line(bucket.stop_window)}",
        "    "
        + (
            _score_change_line(bucket.predicted_strategy_stop_window)
            if bucket.predicted_strategy_stop_window is not None
            else _not_recorded_line(_PREDICTED_STRATEGY_HITS, not_recorded)
        ),
        "    "
        + (
            _width_change_line(bucket.stop_window_width, unit="stops")
            if bucket.stop_window_width is not None
            else _not_recorded_line(_WIDTH, not_recorded)
        ),
    ]


def _averaged_bucket_lines(
    bucket: AveragedBucketDiff, not_recorded: tuple[str, ...]
) -> list[str]:
    return [
        f"  {bucket.label}:",
        f"    {_averaged_change_line(bucket.top_1)}",
        f"    {_averaged_change_line(bucket.top_3)}",
        f"    {_averaged_change_line(bucket.stop_window)}",
        "    "
        + (
            _averaged_change_line(bucket.predicted_strategy_stop_window)
            if bucket.predicted_strategy_stop_window is not None
            else _not_recorded_line(_PREDICTED_STRATEGY_HITS, not_recorded)
        ),
        "    "
        + (
            _width_change_line(bucket.stop_window_width, unit="races")
            if bucket.stop_window_width is not None
            else _not_recorded_line(_WIDTH, not_recorded)
        ),
    ]


def _not_recorded_line(label: str, sides: tuple[str, ...]) -> str:
    return f"{label}: not recorded in {' and '.join(sides)}"


def _width_change_line(change: WidthChange, *, unit: str) -> str:
    before = _fmt_width(change.before_mean, change.before_count, unit)
    after = _fmt_width(change.after_mean, change.after_count, unit)
    if change.change_laps is None:
        delta = "no change computable"
    else:
        delta = f"{change.change_laps:+.1f} laps"
    return f"{change.label}: {before} → {after} ({delta})"


def _fmt_width(mean: float | None, count: int, unit: str) -> str:
    if mean is None:
        return f"— (0 {unit})"
    if unit == "races":
        return f"mean {mean:.1f} laps over {count} race(s)"
    return f"{mean:.1f} laps over {count} stops"


def _score_change_line(change: ScoreChange) -> str:
    before = _fmt_fraction(change.before_numerator, change.before_denominator)
    after = _fmt_fraction(change.after_numerator, change.after_denominator)
    delta = _fmt_delta_pp(change.change_pp)
    return f"{change.label}: {before} → {after} ({delta})"


def _averaged_change_line(change: AveragedChange) -> str:
    before = _fmt_mean(change.before_mean, change.before_races)
    after = _fmt_mean(change.after_mean, change.after_races)
    delta = _fmt_delta_pp(change.change_pp)
    return f"{change.label}: {before} → {after} ({delta})"


def _movement_line(m: RaceMovement) -> str:
    delta = _fmt_delta_pp(m.change_pp)
    return (
        f"{m.season} {m.event} ({m.circuit}): "
        f"{m.before_rate:.0%} → {m.after_rate:.0%} ({delta})"
    )


def _fmt_fraction(numerator: float, denominator: int) -> str:
    if not denominator:
        return "—"
    rounded = round(numerator, 6)
    num_str = str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"
    pct = numerator / denominator
    return f"{num_str}/{denominator} ({pct:.0%})"


def _fmt_mean(mean: float | None, races: int) -> str:
    if mean is None:
        return "— (0 races)"
    return f"mean {mean:.0%} over {races} race(s)"


def _fmt_delta_pp(change_pp: float | None) -> str:
    if change_pp is None:
        return "no change computable"
    pp = change_pp * 100
    sign = "+" if pp >= 0 else ""
    return f"{sign}{pp:.1f} pp"
