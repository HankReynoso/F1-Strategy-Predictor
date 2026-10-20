"""Command: predict a named race's Strategies and compare them with what happened.

    uv run f1-strategy 2024 "Italian Grand Prix"

Loads the weekend through FastF1, makes every driver's Pre-race Prediction,
compares it with the actual race and prints the per-driver table followed by
the race summary. A race that isn't a Dry Race is refused.
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from .predictor import NotDryRaceError, predict
from .report import format_header, format_summary, format_table
from .scorer import compare
from .settings import Settings
from .weekend import RaceWeekend

Loader = Callable[[int, str], RaceWeekend]


def main(argv: Sequence[str] | None = None, load: Loader | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-strategy",
        description="Pre-race Predictions for one race, compared with the actual race.",
    )
    parser.add_argument("season", type=int, help="e.g. 2024")
    parser.add_argument("event", help='event or location name, e.g. "Italian Grand Prix"')
    args = parser.parse_args(argv)

    if load is None:
        import fastf1

        from .fastf1_loader import load_weekend as load

        fastf1.set_log_level("WARNING")

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


if __name__ == "__main__":
    sys.exit(main())
