from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """All tunable settings, with defaults. Tuned later by Backtesting."""

    # How sharply probability falls off with Simulated Race Time gap: a
    # Candidate Strategy this many seconds slower than the fastest is e times
    # less likely. Smaller means sharper.
    probability_scale_s: float = 5.0
