"""Race simulator: Simulated Race Time, best stop laps and Stop Windows for one Strategy.

A Stint of L laps on a Compound losing d seconds per lap costs d*L*(L-1)/2
over fresh-tyre pace. Each stop costs the circuit's Pit Loss. Stint lengths are
chosen to minimise total time: the cost is separable and convex, so handing
out laps one at a time to the Stint with the cheapest next lap is optimal,
starting from the minimum Stint length.

Stop Windows: to score stop k on lap p, the race is split at p and the Stints
on either side are re-optimised (the other stops move to suit). That time is
convex in p, so the laps within the Stop Window margin of the best form one
unbroken range. Stop laps are only considered when every resulting Stint on
either side is at least the minimum Stint length (ticket 13).
"""

from dataclasses import dataclass

from .weekend import Compound


@dataclass(frozen=True)
class StopWindow:
    first_lap: int
    best_lap: int
    last_lap: int


@dataclass(frozen=True)
class SimulatedRace:
    race_time: float
    stint_lengths: tuple[int, ...]


def simulate(
    compounds: tuple[Compound, ...],
    degradation: dict[Compound, float],
    race_laps: int,
    pit_loss: float,
    base_lap_time: float,
    min_stint_length: int = 1,
) -> SimulatedRace:
    lengths, tyre_cost = _allocate(
        [degradation[c] for c in compounds], race_laps, min_stint_length
    )
    race_time = race_laps * base_lap_time + tyre_cost + pit_loss * (len(compounds) - 1)
    return SimulatedRace(race_time, tuple(lengths))


def stop_windows(
    compounds: tuple[Compound, ...],
    degradation: dict[Compound, float],
    race_laps: int,
    stop_window_margin: float,
    min_stint_length: int = 1,
) -> tuple[StopWindow, ...]:
    """One Stop Window per stop, with the other stops re-optimised as it moves."""
    rates = [degradation[c] for c in compounds]
    lengths, best_cost = _allocate(rates, race_laps, min_stint_length)
    windows = []
    best_lap = 0
    for k in range(1, len(compounds)):
        best_lap += lengths[k - 1]
        before, after = rates[:k], rates[k:]
        # Each Stint on either side must be at least `min_stint_length` long.
        laps = range(
            min_stint_length * len(before),
            race_laps - min_stint_length * len(after) + 1,
        )
        within = [
            p
            for p in laps
            if _allocate(before, p, min_stint_length)[1]
            + _allocate(after, race_laps - p, min_stint_length)[1]
            <= best_cost + stop_window_margin + 1e-9
        ]
        windows.append(StopWindow(min(within), best_lap, max(within)))
    return tuple(windows)


def _allocate(
    rates: list[float], laps: int, min_stint_length: int = 1
) -> tuple[list[int], float]:
    """Cheapest Stint lengths for `laps` laps over Stints with these rates,
    with every Stint at least `min_stint_length` long.
    """
    lengths = [min_stint_length] * len(rates)
    for _ in range(laps - min_stint_length * len(rates)):
        cheapest = min(range(len(lengths)), key=lambda i: rates[i] * lengths[i])
        lengths[cheapest] += 1
    cost = sum(d * n * (n - 1) / 2 for d, n in zip(rates, lengths))
    return lengths, cost
