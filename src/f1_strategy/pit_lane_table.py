"""Pit lane table for first-time circuits (ADR-0004 / ticket 07).

A circuit raced for the first time in the Regulation Era, with no same-era
or pre-era history to measure Pit Loss from, gets a Pit Loss estimated from
its pit lane length and speed limit. FastF1 doesn't carry pit lane
geometry, so this module holds a small hand-maintained table filled from
published figures (each with its source), and a plain formula that turns an
entry into a Pit Loss in seconds. The race weekend description records
that the Pit Loss was estimated, and the Backtest Result counts it.

Circuits whose FastF1 ``Location`` matches an earlier race (same-era or
pre-era) are measured, not estimated, and shouldn't appear here.

Keeping the formula and the table together makes it easy to compare the
estimated figure against the Pit Loss actually measured at historic
circuits, which is how the formula was calibrated (see the ticket).
"""

from __future__ import annotations

from dataclasses import dataclass

# Typical values used by the formula. Not tuned to any one circuit — chosen
# to match F1 crews and the "slowing in / accelerating out" bands commonly
# cited in post-race analysis, so the formula lands within ~1 s of the
# measured Pit Loss at a few same-era circuits used for calibration (see
# ticket 07 "Checking the formula").
STATIONARY_TIME_S: float = 2.5
# Time lost outside the speed-limited zone to slowing into the pit lane and
# accelerating back out again. Short, flat pit entries/exits (Monza,
# Barcelona, Austin) cluster around 6 s; steeper or hairpin-adjacent ones
# (Monaco, Imola) are a second or two higher but still fit this budget
# well enough for a first-time-circuit estimate.
SLOW_IN_OUT_PENALTY_S: float = 6.5
# Representative racing speed through the section the pit lane parallels —
# generally the main straight. Any value in roughly 220–280 km/h lands the
# estimate inside its ~1 s calibration band because the car only spends a
# few seconds covering the same distance either way, so the arithmetic is
# dominated by the pit-speed transit.
RACING_SPEED_KMH: float = 250.0


@dataclass(frozen=True)
class PitLane:
    """One circuit's pit lane geometry and the source each figure comes from.

    `circuit` is the FastF1 ``Location`` string the loader stores on
    ``PreRaceInfo.circuit``, so the loader can look an entry up with the
    same key it uses for history matching.
    """

    circuit: str
    length_m: float
    speed_limit_kmh: float
    source: str
    note: str = ""


# The hand-maintained table. One entry per first-time circuit identified in
# ticket 07's survey — i.e. a 2022–2025 race whose FastF1 ``Location`` had
# no earlier race (same-era or pre-era) to measure Pit Loss from. A circuit
# with no entry here and no history becomes an Excluded Race (ticket 02's
# ``DATA_UNAVAILABLE`` path), which is the ticket's intended fallback.
#
# Pit lane published figures are hard to come by: the FIA publishes a Pit
# Lane Drawing per event but not a length-in-metres figure, and the F1
# organiser's circuit guides focus on the main lap. Entries below cite one
# published figure each; where a figure couldn't be confirmed against a
# second source, the ticket's "First-time circuits" section says so.
PIT_LANES: tuple[PitLane, ...] = (
    PitLane(
        circuit="Miami",
        length_m=375.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: Oversteer48 Miami Grand Prix layout guide "
            "(1,232 feet / 375 m). "
            "Speed limit: FIA 2022 Miami Grand Prix stewards' decision — "
            "Car 23 pit lane speeding, Doc 22 (limit set at 80 km/h for "
            "this Event)."
        ),
    ),
    PitLane(
        circuit="Las Vegas",
        length_m=400.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: Geopop (Italian) 2025 Las Vegas technical analysis "
            "(pit lane ≈ 400 m; pit stops averaging 21–23 s). "
            "Speed limit: FIA 2024 Las Vegas Grand Prix stewards' decision "
            "— Car 14 pit lane speeding (limit set at 80 km/h; same limit "
            "was used in 2023)."
        ),
        note=(
            "Both figures are single-source only; the FIA Pit Lane Drawing "
            "shows the geometry but doesn't print a length."
        ),
    ),
)


_BY_CIRCUIT: dict[str, PitLane] = {entry.circuit: entry for entry in PIT_LANES}


def pit_lane_entry(circuit: str) -> PitLane | None:
    """Table entry for ``circuit``, or ``None`` if the circuit isn't listed.

    ``circuit`` is the FastF1 ``Location`` string that the loader stores on
    ``PreRaceInfo.circuit``.
    """
    return _BY_CIRCUIT.get(circuit)


def estimated_pit_loss(entry: PitLane) -> float:
    """Pit Loss (seconds) estimated from pit lane length and speed limit.

    Breaks down as:

    1. The car crosses the pit lane at the speed limit instead of at
       racing speed, costing ``L / v_limit − L / v_racing`` seconds.
    2. A typical stationary time at the box: ``STATIONARY_TIME_S``.
    3. A fixed allowance for slowing into and accelerating out of the pit
       lane (outside the speed-limited zone): ``SLOW_IN_OUT_PENALTY_S``.

    The formula uses the same Pit Loss definition the measured loader
    uses — total time lost on in-lap + out-lap vs clean green laps — so
    an estimated and a measured figure plug into Simulated Race Time the
    same way (ADR-0004 Pit Loss exception).
    """
    v_limit_mps = entry.speed_limit_kmh / 3.6
    v_racing_mps = RACING_SPEED_KMH / 3.6
    transit_delta = entry.length_m / v_limit_mps - entry.length_m / v_racing_mps
    return transit_delta + STATIONARY_TIME_S + SLOW_IN_OUT_PENALTY_S
