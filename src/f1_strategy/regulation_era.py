"""Regulation Era boundaries, one source of truth (ADR-0004).

Historical inputs for a race (Historical Degradation now, and the inputs
Circuit Tendency will use) are drawn only from races in the same Regulation
Era as the race being predicted. The era boundaries live here, in one place,
so loaders and tests read them from a single source instead of each carrying
their own minimum-season number. Pit Loss has an exception that is handled
in the loader, not here (see ADR-0004 and ticket 03).
"""

from __future__ import annotations

# (first_season, last_season_or_None). None means the end of the era is not
# yet known. Oldest first; keep this list the single source of truth.
REGULATION_ERAS: tuple[tuple[int, int | None], ...] = (
    (2022, 2025),
    (2026, None),
)


def era_of(season: int) -> tuple[int, int | None]:
    """Return the (first_season, last_season_or_None) tuple of the era that
    contains ``season``. Raises ``ValueError`` for a season before every
    known era."""
    for start, end in REGULATION_ERAS:
        if start <= season and (end is None or season <= end):
            return (start, end)
    raise ValueError(
        f"season {season} is before the first known Regulation Era "
        f"(earliest era starts in {REGULATION_ERAS[0][0]})"
    )


def era_start(season: int) -> int:
    """Return the first season of ``season``'s Regulation Era. For a 2024
    race, that's 2022; for a 2026 race, 2026."""
    return era_of(season)[0]
