"""Cross-season ``Location`` aliases for the FastF1 loader (ticket 16).

FastF1 occasionally renames a race venue in its event schedule between
seasons even though the physical circuit is unchanged. Pit Loss history
(and Historical Degradation, when it happens to span the rename inside
one Regulation Era) is matched on the ``Location`` string, so without
knowing those renames the loader treats the venues as different and
drops measurable earlier races on the floor.

This module is the single source of truth for those equivalence groups.
Each group lists the FastF1 ``Location`` strings that refer to the same
physical venue; the loader looks up the group for a race's ``Location``
and widens its history search to every string in the group.

Scope: only renames observable in FastF1's 2018–2025 event schedules
(see the comments on each group for the schedule rows that make the
rename visible). Different physical venues in the same country (e.g.
Hockenheim and Nürburgring, Monza and Imola) are not aliases and are
not grouped here.
"""

from __future__ import annotations

# Each group holds every FastF1 ``Location`` string that refers to the
# same physical venue. One source of truth for the rename, so the loader
# needs no per-caller alias logic.
#
# Groups confirmed by iterating FastF1's event schedules for 2018–2025
# and grouping each country's events by ``Location`` (see ticket 16's
# "Rename survey" implementation notes).
LOCATION_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    # Marina Bay Street Circuit, Singapore. FastF1 schedules:
    # - 2018, 2019: Location="Singapore"   (Country=Singapore, Singapore GP)
    # - 2022–2025: Location="Marina Bay"   (Country=Singapore, Singapore GP)
    # (No 2020–2021 edition — COVID.) Same physical venue; the rename hides
    # 2018–2019 from a 2022 Marina Bay Pit Loss search.
    frozenset({"Marina Bay", "Singapore"}),
    # Circuit de Monaco, Monte Carlo. FastF1 schedules:
    # - 2018, 2019, 2021: Location="Monte Carlo"   (Monaco GP; 2020 cancelled)
    # - 2022–2025:        Location="Monaco"        (Monaco GP)
    # Same physical venue; the rename hides 2018–2021 from a 2022 Monaco
    # Pit Loss search.
    frozenset({"Monaco", "Monte Carlo"}),
    # Miami International Autodrome, Miami Gardens. FastF1 schedules:
    # - 2022, 2023, 2024: Location="Miami"           (Miami GP)
    # - 2025:             Location="Miami Gardens"   (Miami GP)
    # Same physical venue; the rename hides 2022–2024 Miami from a 2025
    # Miami Gardens search. This is the one rename that also affects
    # Historical Degradation (ADR-0004 same-era rule), because 2022–2024
    # and 2025 are all in the 2022–2025 Regulation Era.
    frozenset({"Miami", "Miami Gardens"}),
    # Yas Marina Circuit, Yas Island, Abu Dhabi. FastF1 schedules:
    # - 2018:       Country="United Arab Emirates", Location="Yas Marina"
    # - 2019–2025:  Country="Abu Dhabi",            Location="Yas Island"
    # Same physical venue; the rename hides 2018 from a 2022 Yas Island
    # Pit Loss search. (Yas Island 2019–2021 are already matched inside
    # the pre-era fallback for a 2022 Abu Dhabi race, so this alias just
    # widens the sample by one race rather than rescuing the circuit
    # from the estimate path.)
    frozenset({"Yas Island", "Yas Marina"}),
)


# `None` → single-member group (the circuit's own name only). Cached once
# for O(1) lookup from the hot path in `_past_races_at_circuit`.
_BY_LOCATION: dict[str, frozenset[str]] = {
    location: group for group in LOCATION_ALIAS_GROUPS for location in group
}


def location_group(location: str) -> frozenset[str]:
    """Every FastF1 ``Location`` string that refers to the same physical
    venue as ``location``.

    Returns the alias group when one exists, otherwise ``frozenset({location})``
    so the loader can filter on `schedule["Location"].isin(group)`
    unconditionally.
    """
    return _BY_LOCATION.get(location, frozenset({location}))
