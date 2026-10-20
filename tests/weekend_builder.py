"""Helpers for hand-building race weekend descriptions in tests."""

from f1_strategy import (
    Compound,
    HistoricalDegradation,
    Lap,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    Session,
    Stint,
)


def push_lap_set(
    driver: str,
    tyre_set: str,
    compound: Compound,
    lap_times: list[float],
    first_lap: int = 1,
) -> list[Lap]:
    """A Tyre Set of consecutive laps simulating slow-fast-slow Push Lap running.

    Unlike `long_run`, the caller passes a hand-picked pattern (e.g.
    `[slow, fast, slow, fast, slow]`) so the classifier can be exercised
    directly.
    """
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


DEFAULT_FUEL_BURN = 0.03  # matches Settings.fuel_effect_s_per_lap default


def degrading_run(
    driver: str,
    tyre_set: str,
    compound: Compound,
    degradation: float,
    laps: int = 8,
    base: float = 90.0,
    first_lap: int = 1,
    fuel_burn: float = DEFAULT_FUEL_BURN,
) -> list[Lap]:
    """A Long Run whose fitted Degradation (after fuel correction with the same
    `fuel_burn`) is exactly `degradation` seconds per lap. Raw lap times fall by
    `fuel_burn` per lap and rise by `degradation` per lap of tyre age, so the
    observed slope is `degradation - fuel_burn`.
    """
    return long_run(
        driver,
        tyre_set,
        compound,
        [base + (degradation - fuel_burn) * i for i in range(laps)],
        first_lap,
    )


def weekend(
    practice_laps: list[Lap],
    teams: dict[str, str],
    race_laps: int = 57,
    pit_loss: float = 22.0,
    race_stints: list[Stint] | None = None,
    finishing_status: dict[str, bool] | None = None,
    historical_degradation: dict[Compound, HistoricalDegradation] | None = None,
) -> RaceWeekend:
    stints = tuple(race_stints or ())
    if finishing_status is None:
        # Convenience default: every driver with any Stint whose last Stint
        # reaches the race distance took the chequered flag. Tests that need
        # a lapped finisher or a late-retiring classified driver pass an
        # explicit `finishing_status`.
        last_by_driver: dict[str, int] = {}
        for stint in stints:
            last_by_driver[stint.driver] = max(
                last_by_driver.get(stint.driver, 0), stint.end_lap
            )
        finishing_status = {
            driver: last_lap >= race_laps for driver, last_lap in last_by_driver.items()
        }
    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit="Test Circuit",
            season=2024,
            race_laps=race_laps,
            is_sprint_weekend=False,
            sessions=(Session(name="FP2", laps=tuple(practice_laps)),),
            teams=teams,
            pit_loss=pit_loss,
            historical_degradation=dict(historical_degradation or {}),
        ),
        race=RaceOutcome(
            stints=stints, neutralisations=(), finishing_status=dict(finishing_status)
        ),
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
