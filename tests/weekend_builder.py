"""Helpers for hand-building race weekend descriptions in tests."""

from f1_strategy import (
    Compound,
    Lap,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    Session,
    Stint,
)


def long_run(
    driver: str,
    tyre_set: str,
    compound: Compound,
    lap_times: list[float],
    first_lap: int = 1,
) -> list[Lap]:
    """Consecutive laps on one new Tyre Set, tyre age counting up from 1."""
    return [
        Lap(
            driver=driver,
            lap_number=first_lap + i,
            lap_time=t,
            tyre_set=tyre_set,
            compound=compound,
            tyre_age=i + 1,
            new_when_fitted=True,
        )
        for i, t in enumerate(lap_times)
    ]


def degrading_run(
    driver: str,
    tyre_set: str,
    compound: Compound,
    degradation: float,
    laps: int = 8,
    base: float = 90.0,
    first_lap: int = 1,
) -> list[Lap]:
    """A Long Run losing exactly `degradation` seconds per lap."""
    return long_run(
        driver,
        tyre_set,
        compound,
        [base + degradation * i for i in range(laps)],
        first_lap,
    )


def weekend(
    practice_laps: list[Lap],
    teams: dict[str, str],
    race_laps: int = 57,
    pit_loss: float = 22.0,
    race_stints: list[Stint] | None = None,
) -> RaceWeekend:
    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit="Test Circuit",
            season=2024,
            race_laps=race_laps,
            is_sprint_weekend=False,
            sessions=(Session(name="FP2", laps=tuple(practice_laps)),),
            teams=teams,
            pit_loss=pit_loss,
        ),
        race=RaceOutcome(stints=tuple(race_stints or ()), neutralisations=()),
    )


def standard_practice(
    soft: float = 0.12, medium: float = 0.07, hard: float = 0.04
) -> list[Lap]:
    """One driver's Long Runs on each dry Compound with the given Degradation."""
    return [
        *degrading_run("VER", "VER-S1", Compound.SOFT, soft),
        *degrading_run("VER", "VER-M1", Compound.MEDIUM, medium, first_lap=20),
        *degrading_run("VER", "VER-H1", Compound.HARD, hard, first_lap=40),
    ]


TEAMS = {"VER": "Red Bull Racing", "PER": "Red Bull Racing", "LEC": "Ferrari"}
