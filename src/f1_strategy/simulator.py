"""Race simulator: Simulated Race Time and best stop laps for one Strategy.

A Stint of L laps on a Compound losing d seconds per lap costs d*L*(L-1)/2
over fresh-tyre pace. Each stop costs the circuit's Pit Loss. Stint lengths are
chosen to minimise total time: the cost is separable and convex, so handing
out laps one at a time to the Stint with the cheapest next lap is optimal.
"""

from dataclasses import dataclass

from .weekend import Compound


@dataclass(frozen=True)
class SimulatedRace:
    race_time: float
    stint_lengths: tuple[int, ...]

    @property
    def best_stop_laps(self) -> tuple[int, ...]:
        laps, total = [], 0
        for length in self.stint_lengths[:-1]:
            total += length
            laps.append(total)
        return tuple(laps)


def simulate(
    compounds: tuple[Compound, ...],
    degradation: dict[Compound, float],
    race_laps: int,
    pit_loss: float,
    base_lap_time: float,
) -> SimulatedRace:
    rates = [degradation[c] for c in compounds]
    lengths = [1] * len(compounds)
    for _ in range(race_laps - len(compounds)):
        cheapest = min(range(len(lengths)), key=lambda i: rates[i] * lengths[i])
        lengths[cheapest] += 1

    tyre_cost = sum(d * n * (n - 1) / 2 for d, n in zip(rates, lengths))
    race_time = race_laps * base_lap_time + tyre_cost + pit_loss * (len(compounds) - 1)
    return SimulatedRace(race_time, tuple(lengths))
