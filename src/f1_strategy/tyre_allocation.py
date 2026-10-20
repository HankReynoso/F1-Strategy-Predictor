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
    new_sets, _ = _collect_fitted_sets(pre_race, allocation)
    return {
        driver: {
            compound: max(0, allocation[compound] - len(sets))
            for compound, sets in by_compound.items()
        }
        for driver, by_compound in new_sets.items()
    }


def remaining_sets_including_used(pre_race: PreRaceInfo) -> dict[str, dict[Compound, int]]:
    """Fallback count: new Remaining Sets plus distinct used sets fitted.

    Used for drivers whose new-only count leaves no runnable Strategy. The
    saved used sets a driver carried through practice are legitimately
    available for the race, and ignoring them (as the new-only rule does)
    can leave a driver with no legal Strategy at all (ticket 12; ADR-0002
    amendment).

    FastF1 has no persistent per-set identity across sessions (ADR-0002,
    ticket 07): the loader assigns one `tyre_set` id per stint. Distinct
    used-stint ids per Compound therefore over-count physical sets when
    one physical used set is fitted in more than one session. We cap each
    Compound at the Tyre Allocation to bound that over-count. The
    fallback is already an approximation flagged on the prediction, so
    being slightly over-permissive is preferable to the crash it
    replaces; the alternative — matching by Tyre Life — is ambiguous for
    about half of used stints (ticket 07) and is rejected in ADR-0002.
    """
    allocation = pre_race.tyre_allocation or default_allocation(
        pre_race.is_sprint_weekend
    )
    new_sets, used_sets = _collect_fitted_sets(pre_race, allocation)
    return {
        driver: {
            compound: max(
                0,
                min(
                    allocation[compound],
                    (allocation[compound] - len(new_sets[driver][compound]))
                    + len(used_sets[driver][compound]),
                ),
            )
            for compound in allocation
        }
        for driver in new_sets
    }


def _collect_fitted_sets(
    pre_race: PreRaceInfo, allocation: dict[Compound, int]
) -> tuple[dict[str, dict[Compound, set[str]]], dict[str, dict[Compound, set[str]]]]:
    """Distinct `tyre_set` ids per (driver, compound), split new vs used."""
    new_sets: dict[str, dict[Compound, set[str]]] = {
        driver: {c: set() for c in allocation} for driver in pre_race.teams
    }
    used_sets: dict[str, dict[Compound, set[str]]] = {
        driver: {c: set() for c in allocation} for driver in pre_race.teams
    }
    for session in pre_race.sessions:
        for lap in session.laps:
            if lap.driver not in new_sets:
                continue
            if lap.compound not in allocation:
                continue
            bucket = new_sets if lap.new_when_fitted else used_sets
            bucket[lap.driver][lap.compound].add(lap.tyre_set)
    return new_sets, used_sets


def can_run(strategy_compounds: tuple[Compound, ...], remaining: dict[Compound, int]) -> bool:
    """Whether a driver with these Remaining Sets can run the Strategy."""
    needs: dict[Compound, int] = {}
    for compound in strategy_compounds:
        needs[compound] = needs.get(compound, 0) + 1
    return all(remaining.get(c, 0) >= n for c, n in needs.items())
