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


# The hand-maintained table. One entry per circuit whose FastF1 ``Location``
# has no earlier race the loader can measure Pit Loss from under default
# settings. Two sources of entries:
#
# - *First-time circuits* (ticket 07's survey): a 2022–2025 race whose
#   FastF1 ``Location`` had no earlier race at any time — Miami 2022 and
#   Las Vegas 2023.
# - *2022 circuits whose only pre-era history is 2018–2019* (ticket 25):
#   Melbourne, Montréal, Spa-Francorchamps, Marina Bay and Suzuka. Those
#   seasons stopped being downloadable through FastF1's live-timing API,
#   so the ADR-0004 Pit Loss exception's pre-era pass comes back empty
#   and the loader needs this table as its last fallback. Confirmed from
#   the 2026-10-23 baseline attempt's Excluded Races (commit e5e9699).
#
# A circuit with no entry here and no history becomes an Excluded Race
# (ticket 02's ``DATA_UNAVAILABLE`` path), which is the ticket's intended
# fallback.
#
# Pit lane published figures are hard to come by: the FIA publishes a Pit
# Lane Drawing per event but not a length-in-metres figure, and the F1
# organiser's circuit guides focus on the main lap. Entries below cite one
# published source per figure; where a length couldn't be confirmed against
# a second source, the ``note`` field says so. Speed limits are
# cross-confirmed against an FIA stewards' pit-lane-speeding decision for
# the event, which prints the limit set for that Event verbatim.
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
    PitLane(
        circuit="Melbourne",
        length_m=281.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: TracingInsights 2024 Australian Grand Prix preview "
            "(\"the Melbourne circuit has the second shortest pit lane on "
            "the calendar at just 281 meters\"); corroborated by McLaren's "
            "circuit notes (280 m / 0.714 mi) and the 2014 Mercedes stat "
            "sheet (289 m under speed-limit control, pre-2022 widening). "
            "Speed limit: FIA 2022 Australian Grand Prix stewards' "
            "decision — Car 5 pit lane speeding, Doc 42 (limit set at "
            "80 km/h for this Event, raised from 60 km/h after the 2022 "
            "pit lane widening)."
        ),
    ),
    PitLane(
        circuit="Montréal",
        length_m=400.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: McLaren 2015 Canadian Grand Prix preview on "
            "Racecar.com (\"Pitlane length: 400m/0.249 miles, estimated "
            "time loss 22s\"); corroborated by Mercedes-AMG F1's 2024 "
            "Canadian Grand Prix preview (405 m, ranked 8th on the "
            "calendar) and Sportskeeda's circuit stats (400 m). "
            "Speed limit: FIA 2022 Canadian Grand Prix stewards' decision "
            "— Car 4 pit lane speeding, Doc 67 (limit set at 80 km/h "
            "for this Event)."
        ),
        note=(
            "Oversteer48's circuit guide gives 741 m measured from where "
            "the lane leaves the track to where it rejoins — this includes "
            "the slow-in and slow-out zones outside the speed-limited "
            "section, and the formula already accounts for those in its "
            "fixed slow-in/slow-out penalty, so the 400 m speed-limited "
            "length is the right input."
        ),
    ),
    PitLane(
        circuit="Spa-Francorchamps",
        length_m=653.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: Oversteer48 Spa-Francorchamps circuit guide (\"The "
            "Formula 1 pit lane at Spa Francorchamps is 653 metres / "
            "2144 ft long\"). "
            "Speed limit: FIA 2022 Belgian Grand Prix stewards' decision "
            "— Car 16 pit lane speeding (Leclerc, limit set at 80 km/h "
            "for this Event, exceeded by 1.0 km/h)."
        ),
        note=(
            "Length is single-source; the 994 m figure that appears in "
            "the GT4 European Series' Spa briefing applies to the "
            "endurance pit-lane configuration (which uses the old pit "
            "lane alongside the F1 one) and does not fit here."
        ),
    ),
    PitLane(
        circuit="Marina Bay",
        length_m=404.0,
        speed_limit_kmh=60.0,
        source=(
            "Length: The Star 2019 (\"offers one of the longest pit "
            "lanes on the F1 calendar, all 404 metres\"); corroborated "
            "by the 2014 Mercedes Singapore GP stat sheet (411 m under "
            "speed-limit control, same physical pit lane). "
            "Speed limit: FIA 2022 Singapore Grand Prix stewards' "
            "decision — Car 63 pit lane speeding (Russell, limit set at "
            "60 km/h for this Event, exceeded by 0.6 km/h). The limit "
            "was raised to 80 km/h for 2025 after a Friday-practice "
            "safety trial — a 2023+ change outside the 2022 scope of "
            "this entry."
        ),
    ),
    PitLane(
        circuit="Suzuka",
        length_m=413.0,
        speed_limit_kmh=80.0,
        source=(
            "Length: McLaren 2016 Japanese Grand Prix preview on "
            "Racecar.com (\"Pitlane length 413m/0.257 miles, estimated "
            "time loss 23s\"). "
            "Speed limit: FIA 2022 Japanese Grand Prix stewards' decision "
            "— Car 77 pit lane speeding (Bottas, limit set at 80 km/h "
            "for this Event, exceeded by 4.2 km/h)."
        ),
        note=(
            "Length is single-source and dated 2016; the Suzuka pit lane "
            "has not been rebuilt since, so the figure still applies."
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
