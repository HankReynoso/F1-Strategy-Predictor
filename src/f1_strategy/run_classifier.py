"""Split practice laps into Long Runs and Push Laps per driver and Tyre Set.

A **Long Run** is a run of consistently timed consecutive laps on one Tyre
Set, excluding out-laps, in-laps, laps under a Safety Car or VSC, and laps
that are abnormally slow compared with their neighbours (traffic, a
mistake, or a slow return to the pits). Minimum length and the slow-lap
margin are settings.

A **Push Lap** is a lap on a Tyre Set that is strictly faster than both of
its neighbours on that set by at least the push-lap margin: the slow–fast
part of the slow-fast-slow pattern. A Tyre Set with any Push Lap is
classified as Push Laps and never as a Long Run; the Push Laps on it are
grouped together so their fall-off can be measured.

Sprint race Stints come through the same path because the FastF1 loader
publishes the Sprint as session name ``"S"`` with consecutive race laps:
with no slow-fast-slow pattern and a consistent lap length, every Sprint
Stint classifies as a Long Run.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from .settings import Settings
from .weekend import Lap, PreRaceInfo


@dataclass(frozen=True)
class ClassifiedRuns:
    """Classified practice running for one race weekend.

    `long_runs` is a list of lap sequences, each a Long Run. `push_lap_groups`
    is a list of lap sequences, each the Push Laps found on one Tyre Set.
    """

    long_runs: list[list[Lap]]
    push_lap_groups: list[list[Lap]]


def classify(pre_race: PreRaceInfo, settings: Settings) -> ClassifiedRuns:
    long_runs: list[list[Lap]] = []
    push_lap_groups: list[list[Lap]] = []
    for session in pre_race.sessions:
        by_set: dict[tuple[str, str], list[Lap]] = defaultdict(list)
        for lap in session.laps:
            by_set[(lap.driver, lap.tyre_set)].append(lap)
        for laps in by_set.values():
            laps.sort(key=lambda lap: lap.lap_number)
            for sub_run in _consecutive_runs(_racing_only(laps)):
                _classify_one(sub_run, settings, long_runs, push_lap_groups)
    return ClassifiedRuns(long_runs=long_runs, push_lap_groups=push_lap_groups)


def _racing_only(laps: list[Lap]) -> list[Lap]:
    """Drop out-laps, in-laps and neutralised laps before classification."""
    return [lap for lap in laps if not (lap.pit_in or lap.pit_out or lap.neutralised)]


def _consecutive_runs(laps: list[Lap]) -> list[list[Lap]]:
    """Split by gaps in `lap_number`; each run is strictly consecutive."""
    if not laps:
        return []
    runs: list[list[Lap]] = [[laps[0]]]
    for lap in laps[1:]:
        if lap.lap_number == runs[-1][-1].lap_number + 1:
            runs[-1].append(lap)
        else:
            runs.append([lap])
    return runs


def _classify_one(
    sub_run: list[Lap],
    settings: Settings,
    long_runs: list[list[Lap]],
    push_lap_groups: list[list[Lap]],
) -> None:
    if len(sub_run) < 2:
        return
    push_laps = _push_laps(sub_run, settings.push_lap_fast_margin_s)
    if push_laps:
        push_lap_groups.append(push_laps)
        return
    cutoff = median(lap.lap_time for lap in sub_run) + settings.long_run_slow_lap_margin_s
    kept = [lap for lap in sub_run if lap.lap_time <= cutoff]
    for consistent in _consecutive_runs(kept):
        if len(consistent) >= settings.min_long_run_length:
            long_runs.append(consistent)


def _push_laps(laps: list[Lap], fast_margin: float) -> list[Lap]:
    """Interior laps strictly faster than both neighbours by `fast_margin`."""
    found = []
    for i in range(1, len(laps) - 1):
        before, lap, after = laps[i - 1], laps[i], laps[i + 1]
        if (
            before.lap_time - lap.lap_time >= fast_margin
            and after.lap_time - lap.lap_time >= fast_margin
        ):
            found.append(lap)
    return found
