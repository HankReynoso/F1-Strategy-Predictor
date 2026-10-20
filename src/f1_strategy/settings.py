from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """All tunable settings, with defaults. Tuned later by Backtesting."""

    # How sharply probability falls off with Simulated Race Time gap: a
    # Candidate Strategy this many seconds slower than the fastest is e times
    # less likely. Smaller means sharper.
    probability_scale_s: float = 5.0

    # Plausible: a Candidate Strategy whose Simulated Race Time is more than
    # this many seconds behind the fastest is dropped from the prediction.
    plausible_margin_s: float = 20.0

    # Stop Window: every stop lap whose Simulated Race Time is within this many
    # seconds of the best stop lap is inside the window.
    stop_window_margin_s: float = 1.0

    # Fuel effect: seconds per lap of lap time that comes from fuel burn alone,
    # added back to the Long Run slope so Degradation reflects pure tyre wear.
    fuel_effect_s_per_lap: float = 0.03

    # Long Run recognition: a run of consistently timed consecutive laps on
    # one Tyre Set must be at least this long to count as a Long Run.
    min_long_run_length: int = 4

    # Long Run recognition: a lap more than this many seconds above its run's
    # median is treated as abnormally slow (traffic, mistake, pit entry) and
    # dropped from the fit. The remaining consecutive laps are re-split and
    # each sub-run is checked against `min_long_run_length` again.
    long_run_slow_lap_margin_s: float = 3.0

    # Push Lap recognition: a lap strictly faster than both its neighbours on
    # the same Tyre Set by at least this much is a Push Lap. A Tyre Set with
    # any Push Lap is classified as Push Laps and never as a Long Run.
    push_lap_fast_margin_s: float = 1.0
