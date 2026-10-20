"""Remaining Sets: each driver's unused new Tyre Sets per Compound.

The weekend description describes only the sets drivers used, not the
sets the FIA allocated to each driver. Allocation is uniform across
drivers (fixed by regulation) and defaulted here; a weekend can override
it via `PreRaceInfo.tyre_allocation`. Remaining Sets is then the
allocation minus new-set usage drawn from pre-race sessions.

See ticket 04 for the decision to count new sets only; the ticket's
Implementation notes explain the trade-off.
"""

from .weekend import Compound, PreRaceInfo

# FIA Tyre Allocation of NEW sets per driver per weekend (dry Compounds).
# A conventional weekend gives 13 sets, a sprint weekend 12.
DEFAULT_DRY_ALLOCATION: dict[Compound, int] = {
    Compound.SOFT: 8,
    Compound.MEDIUM: 3,
    Compound.HARD: 2,
}
DEFAULT_SPRINT_ALLOCATION: dict[Compound, int] = {
    Compound.SOFT: 6,
    Compound.MEDIUM: 4,
    Compound.HARD: 2,
}


def default_allocation(is_sprint_weekend: bool) -> dict[Compound, int]:
    return dict(
        DEFAULT_SPRINT_ALLOCATION if is_sprint_weekend else DEFAULT_DRY_ALLOCATION
    )


def remaining_sets(pre_race: PreRaceInfo) -> dict[str, dict[Compound, int]]:
    """Each driver's Remaining Sets per dry Compound (new only).

    A set is counted as "used" when a driver fits it fresh in any pre-race
    session: one distinct `tyre_set` with `new_when_fitted=True` is one
    new set consumed. Used-set stints do not subtract from the allocation.
    """
    allocation = pre_race.tyre_allocation or default_allocation(
        pre_race.is_sprint_weekend
    )

    # Collect distinct new sets per (driver, compound).
    new_sets: dict[str, dict[Compound, set[str]]] = {
        driver: {c: set() for c in allocation} for driver in pre_race.teams
    }
    for session in pre_race.sessions:
        for lap in session.laps:
            if lap.driver not in new_sets:
                continue
            if not lap.new_when_fitted:
                continue
            if lap.compound not in allocation:
                continue
            new_sets[lap.driver][lap.compound].add(lap.tyre_set)

    return {
        driver: {
            compound: max(0, allocation[compound] - len(sets))
            for compound, sets in by_compound.items()
        }
        for driver, by_compound in new_sets.items()
    }


def can_run(strategy_compounds: tuple[Compound, ...], remaining: dict[Compound, int]) -> bool:
    """Whether a driver with these Remaining Sets can run the Strategy."""
    needs: dict[Compound, int] = {}
    for compound in strategy_compounds:
        needs[compound] = needs.get(compound, 0) + 1
    return all(remaining.get(c, 0) >= n for c, n in needs.items())
