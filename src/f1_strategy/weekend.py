"""The plain, project-owned description of one race weekend.

Pre-race information (practice, sprint and qualifying running, teams, Pit Loss)
lives in `PreRaceInfo`. What actually happened in the race lives in
`RaceOutcome`. Pre-race Predictions read only `PreRaceInfo`.
"""

from dataclasses import dataclass, field
from enum import Enum


class Compound(Enum):
    SOFT = "S"
    MEDIUM = "M"
    HARD = "H"
    INTERMEDIATE = "I"
    WET = "W"

    @property
    def is_dry(self) -> bool:
        return self in DRY_COMPOUNDS


DRY_COMPOUNDS = (Compound.SOFT, Compound.MEDIUM, Compound.HARD)


@dataclass(frozen=True)
class Lap:
    """One timed lap by one driver in a pre-race session."""

    driver: str
    lap_number: int
    lap_time: float  # seconds
    tyre_set: str  # identity of the Tyre Set fitted
    compound: Compound
    tyre_age: int  # laps on this Tyre Set, including this one
    new_when_fitted: bool
    pit_in: bool = False
    pit_out: bool = False
    neutralised: bool = False  # under a Safety Car or VSC


@dataclass(frozen=True)
class Session:
    name: str  # e.g. "FP1", "FP2", "FP3", "Sprint", "Q"
    laps: tuple[Lap, ...]


@dataclass(frozen=True)
class HistoricalDegradation:
    """One Compound's Degradation estimated from previous seasons' race Stints
    at the same circuit, with provenance for the report."""

    rate: float  # seconds per lap, fuel-corrected
    seasons: tuple[int, ...]  # the past seasons that contributed, oldest first
    stint_count: int  # how many clean race Stints the fit pooled across


@dataclass(frozen=True)
class PreRaceInfo:
    circuit: str
    season: int
    race_laps: int
    is_sprint_weekend: bool
    sessions: tuple[Session, ...]
    teams: dict[str, str]  # driver -> team, for every driver who starts
    pit_loss: float  # seconds lost per pit stop at this circuit
    # Past seasons that contributed to Pit Loss, oldest first. Normally all
    # within the race's Regulation Era; for a first-season race with no
    # same-era history, falls back to pre-era seasons (ADR-0004 exception).
    # Empty when Pit Loss was estimated from pit lane length and speed
    # limit (ticket 07) and for hand-built test weekends that pass
    # `pit_loss` directly.
    pit_loss_seasons: tuple[int, ...] = ()
    # True when Pit Loss came from the hand-maintained pit lane table and
    # the estimation formula (ticket 07), not from measured past races.
    # Set when a first-time circuit has neither same-era nor pre-era
    # history to measure from.
    estimated_pit_loss: bool = False
    # New sets of each dry Compound allocated to every driver this weekend.
    # None means use the FIA regulation default for the weekend format.
    tyre_allocation: dict["Compound", int] | None = None
    # Whether the source says which Tyre Sets were new when fitted. FastF1
    # carries F1's own "new" flag; OpenF1 doesn't, and its
    # `tyre_age_at_start` reads 0 on many re-fitted sets (ticket 50). When
    # False, every driver's Remaining Sets is the full Tyre Allocation
    # (ADR-0002 amendment, 2026-10-27). `Lap.new_when_fitted` is still
    # filled in either way; only Remaining Sets reads this field.
    set_usage_known: bool = True
    # Field-level Degradation per dry Compound from previous seasons' race
    # Stints at this circuit (ticket 11, ADR-0003). A Compound is absent when
    # no clean past-race Stints were available for it, or (deliberately) when
    # the weekend is a hand-built test that doesn't need the fallback.
    historical_degradation: dict["Compound", "HistoricalDegradation"] = field(
        default_factory=dict
    )
    # Human-readable notes from the cross-source past-race scan (ticket 28):
    # which past seasons/circuits returned no usable samples, and why. Empty
    # for a race where every same-era past season contributed. Carries
    # through load_weekend → Backtest's per-race record so a reader can tell
    # a measured history apart from a partially-empty one. Does not include
    # fetch failures, which propagate instead (rate limit, OpenF1 outage);
    # only genuine "no rows / no clean laps" cases land here.
    data_quality_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stint:
    """A Stint actually run in the race."""

    driver: str
    compound: Compound
    start_lap: int
    end_lap: int


@dataclass(frozen=True)
class NeutralisationPeriod:
    """A Safety Car or Virtual Safety Car period in the race."""

    kind: str  # "SC" or "VSC"
    start_lap: int
    end_lap: int


@dataclass(frozen=True)
class RaceOutcome:
    stints: tuple[Stint, ...] = ()
    neutralisations: tuple[NeutralisationPeriod, ...] = field(default=())
    # Driver -> took the chequered flag. Lapped finishers are True; drivers
    # who retired, were disqualified, or did not start are False. Belongs to
    # the race outcome, never to pre-race information, so changing it never
    # changes a Pre-race Prediction.
    finishing_status: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class RaceWeekend:
    pre_race: PreRaceInfo
    race: RaceOutcome
