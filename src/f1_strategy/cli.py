"""Command: predict a named race's Strategies and compare them with what happened,
or run a Backtest over chosen seasons.

Single-race mode (unchanged):

    uv run f1-strategy 2024 "Italian Grand Prix"

Loads the weekend through FastF1, makes every driver's Pre-race Prediction,
compares it with the actual race and prints the per-driver table followed by
the race summary. A race that isn't a Dry Race is refused.

Backtest mode:

    uv run f1-strategy backtest 2024
    uv run f1-strategy backtest 2022 2023 2024 2025

Lists the chosen seasons' race weekends through FastF1 and runs each one
through `predict` and `compare`, printing progress and the Backtest Result.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from .backtest import SMOKE_SET, RaceSpec, format_backtest, run_backtest
from .backtest_compare import compare_backtest_results, format_comparison
from .backtest_io import (
    RunMetadata,
    default_run_at,
    detect_code_version,
    load_backtest_result,
    save_backtest_result,
)
from .predictor import NotDryRaceError, predict
from .report import format_header, format_summary, format_table
from .scorer import compare
from .settings import Settings
from .weekend import RaceWeekend

Loader = Callable[[int, str], RaceWeekend]
SeasonLister = Callable[[int], Sequence[RaceSpec]]


def main(
    argv: Sequence[str] | None = None,
    load: Loader | None = None,
    list_season: SeasonLister | None = None,
) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if argv and argv[0] == "backtest":
        return _run_backtest_mode(argv[1:], load=load, list_season=list_season)
    if argv and argv[0] == "smoke":
        return _run_smoke_mode(argv[1:], load=load)
    if argv and argv[0] == "compare":
        return _run_compare_mode(argv[1:])
    return _run_single_race(argv, load=load)


def _run_single_race(argv: Sequence[str], load: Loader | None) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-strategy",
        description="Pre-race Predictions for one race, compared with the actual race.",
    )
    parser.add_argument("season", type=int, help="e.g. 2024")
    parser.add_argument("event", help='event or location name, e.g. "Italian Grand Prix"')
    args = parser.parse_args(argv)

    if load is None:
        load = _fastf1_load()

    settings = Settings()
    weekend = load(args.season, args.event)
    try:
        predictions = predict(weekend, settings)
    except NotDryRaceError as refusal:
        print(refusal, file=sys.stderr)
        return 2
    except ValueError as refusal:
        # Clear refusal (not a crash) when the Degradation fallback chain
        # cannot produce a rate for some Compound (ticket 11, ADR-0003):
        # no team ran it, no circuit race history for it, and no softer
        # Compound to bound it by. Reported to stderr, exit code 2, so
        # a pipe never sees a half report.
        print(
            f"Cannot predict {weekend.pre_race.season} {weekend.pre_race.circuit}: "
            f"{refusal}",
            file=sys.stderr,
        )
        return 2
    comparison = compare(predictions, weekend)

    print(format_header(weekend.pre_race, settings, predictions))
    print()
    print(format_table(predictions, comparison))
    print()
    print(format_summary(comparison))
    return 0


def _run_backtest_mode(
    argv: Sequence[str], load: Loader | None, list_season: SeasonLister | None
) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-strategy backtest",
        description="Run a Backtest over chosen seasons' race weekends.",
    )
    parser.add_argument(
        "seasons", type=int, nargs="+", help="seasons to include, e.g. 2024 2025"
    )
    parser.add_argument(
        "--label",
        default=None,
        help=(
            "short label for this run (e.g. 'baseline'). When set, the run "
            "writes a Backtest Result data and summary file. When omitted, "
            "the run prints but does not save (Smoke-Set-style)."
        ),
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="run and print only; never save, even if --label is given.",
    )
    parser.add_argument(
        "--results-dir",
        default="results/backtest",
        help="where saved Backtest Results go (default: results/backtest).",
    )
    args = parser.parse_args(argv)

    if list_season is None or load is None:
        default_load, default_list = _fastf1_load_and_list()
        if load is None:
            load = default_load
        if list_season is None:
            list_season = default_list

    races: list[RaceSpec] = []
    for season in args.seasons:
        races.extend(list_season(season))

    def progress(label: str) -> None:
        print(f"  {label}", file=sys.stderr, flush=True)

    settings = Settings()
    print(
        f"Backtest over {len(races)} race weekend(s) "
        f"in season(s) {', '.join(str(s) for s in args.seasons)}",
        file=sys.stderr,
    )
    result = run_backtest(races, load=load, settings=settings, progress=progress)
    print(format_backtest(result))

    if args.label and not args.no_save:
        commit, dirty = detect_code_version()
        metadata = RunMetadata(
            label=args.label,
            run_at=default_run_at(),
            code_commit=commit,
            uncommitted_changes=dirty,
            seasons_in_scope=tuple(args.seasons),
            settings=settings,
        )
        paths = save_backtest_result(result, args.results_dir, metadata=metadata)
        print(
            f"Saved Backtest Result {args.label!r} to:\n"
            f"  {paths.data}\n  {paths.summary}",
            file=sys.stderr,
        )
    return 0


def _run_smoke_mode(argv: Sequence[str], load: Loader | None) -> int:
    """Run the Smoke Set and print its Backtest Result without saving it."""
    parser = argparse.ArgumentParser(
        prog="f1-strategy smoke",
        description=(
            "Run the Smoke Set: a small fixed set of races covering every "
            "path through the model (Singapore, Monza, Baku, Austin and "
            "Jeddah 2024, plus Hungary 2022). Prints the Backtest Result "
            "without saving it."
        ),
    )
    parser.parse_args(argv)

    if load is None:
        load = _fastf1_load()

    def progress(label: str) -> None:
        print(f"  {label}", file=sys.stderr, flush=True)

    settings = Settings()
    print(
        f"Smoke Set over {len(SMOKE_SET)} race weekend(s)", file=sys.stderr
    )
    result = run_backtest(SMOKE_SET, load=load, settings=settings, progress=progress)
    print(format_backtest(result))
    return 0


def _run_compare_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-strategy compare",
        description=(
            "Compare two saved Backtest Results: show the before, after and "
            "change for every headline score and breakdown, the biggest-"
            "moving races in each direction, and any scope warnings."
        ),
    )
    parser.add_argument("before", help="path to the earlier Backtest Result JSON")
    parser.add_argument("after", help="path to the later Backtest Result JSON")
    args = parser.parse_args(argv)

    before_result, before_md = load_backtest_result(args.before)
    after_result, after_md = load_backtest_result(args.after)
    comparison = compare_backtest_results(
        before_result,
        after_result,
        before_metadata=before_md,
        after_metadata=after_md,
    )
    print(f"Comparing {before_md.label!r} → {after_md.label!r}")
    print()
    print(format_comparison(comparison))
    return 0


def _fastf1_load() -> Loader:
    import fastf1
    from .fastf1_loader import load_weekend

    fastf1.set_log_level("WARNING")
    return load_weekend


def _fastf1_load_and_list() -> tuple[Loader, SeasonLister]:
    import fastf1
    from .fastf1_loader import list_season, load_weekend

    fastf1.set_log_level("WARNING")
    return load_weekend, list_season


if __name__ == "__main__":
    sys.exit(main())
