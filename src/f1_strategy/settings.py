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
