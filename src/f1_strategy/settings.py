from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """All tunable settings, with defaults. Tuned later by Backtesting."""

    # Backtest run partitioning: the Tuning Seasons are available for later
    # settings tuning; the Held-out Season is kept aside so its Backtest score
    # shows how the model does on races it wasn't tuned on. Carried on
    # Settings (not hard-coded into scoring) so a Backtest run records which
    # seasons it treated as which, and the tuning spec can reuse them.
    tuning_seasons: tuple[int, ...] = (2022, 2023, 2024)
    held_out_season: int | None = 2025

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

    # Degradation shrinkage: a team's own fitted Degradation on a Compound is
    # blended with the field average (the raw, unshrunk, unclamped mean across
    # the other teams on that Compound, weighted by each team's lap count).
    # The blend weights the team's own fit by its lap count and the field
    # average by this many "equivalent laps". A team at the minimum Long Run
    # length (4) sits at a 50/50 blend; a team with two clean 8-lap runs is
    # 80% its own fit. Final estimate clamped at zero.
    degradation_shrinkage_laps: float = 4.0

    # Minimum race Stint length. A Candidate Strategy must have every Stint at
    # least this long, and no Stop Window puts a stop so early (or so late)
    # that any Stint on either side would be shorter. 5 laps because planned
    # (non-Deviation) race Stints below 5 laps are essentially never seen in
    # modern F1; a 5-lap undercut or overcut window still fits comfortably.
    min_stint_length: int = 5
