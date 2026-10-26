"""Slow tests for ticket 28: real OpenF1 past-race coverage.

These tests go through the real :class:`.openf1_client.OpenF1Client`
against the warm cache under ``.cache/openf1``. They pin two things the
fast tests can't:

- The OpenF1 ``/v1/pit`` coverage gap for the first seven 2023 races
  (Bahrain → Monaco, including Baku and Jeddah), and the fact that the
  ticket-28 stint-boundary fallback recovers a usable Pit Loss sample
  for the Baku 2023 and Jeddah 2023 past races.
- Every FastF1 ``Location`` string used for a 2023–2025 Grand Prix
  resolves through the OpenF1 matcher (:func:`._find_meeting`),
  including the shared ``location_group`` aliases from ticket 16. If
  OpenF1 ever renames a venue the way FastF1 did, this test catches it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1_strategy.location_aliases import location_group
from f1_strategy.openf1_client import OpenF1Client
from f1_strategy.openf1_loader import (
    _find_meeting,
    _is_race_meeting,
    load_past_race_samples,
)

pytestmark = pytest.mark.slow

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "openf1"


@pytest.fixture(scope="module")
def client() -> OpenF1Client:
    return OpenF1Client(cache_dir=CACHE_DIR)


# ---------------------------------------------------------------------------
# /v1/pit gap: Baku 2023 and Jeddah 2023 become measurable via stints.
# ---------------------------------------------------------------------------


def test_baku_2023_pit_losses_are_recovered_from_stint_boundaries(client):
    """OpenF1 returns ``404 "No results found."`` on
    ``/v1/pit?session_key=9070`` even though Baku 2023's ``/v1/stints``
    shows 19 of 20 drivers had multiple stints. The ticket-28 fallback
    derives one pit-in lap per stint boundary and feeds those into
    :func:`_pit_losses_in`; the result is a non-empty sample band in
    the usual 10–60 s range.
    """
    samples = load_past_race_samples(
        client, 2023, "Baku",
        fuel_effect_s_per_lap=0.03, history_min_stint_length=4,
    )
    assert samples.pit_losses, (
        "Baku 2023 pit losses should be recoverable from stint boundaries "
        "despite OpenF1's empty /v1/pit for session_key=9070"
    )
    # Every clipped sample is a plausible pit loss figure.
    for loss in samples.pit_losses:
        assert 10.0 < loss < 60.0


def test_jeddah_2023_pit_losses_are_recovered_from_stint_boundaries(client):
    """Same OpenF1 /v1/pit coverage gap as Baku 2023 (session_key=7779).
    Verified 2026-10-26 against the live API.
    """
    samples = load_past_race_samples(
        client, 2023, "Jeddah",
        fuel_effect_s_per_lap=0.03, history_min_stint_length=4,
    )
    assert samples.pit_losses, (
        "Jeddah 2023 pit losses should be recoverable from stint boundaries "
        "despite OpenF1's empty /v1/pit for session_key=7779"
    )
    for loss in samples.pit_losses:
        assert 10.0 < loss < 60.0


# ---------------------------------------------------------------------------
# Alias map coverage: every 2023/2024 FastF1 Location resolves in OpenF1.
# ---------------------------------------------------------------------------


# FastF1 ``Location`` strings per season for every 2023 and 2024 Grand
# Prix, read from the cached event schedules. If FastF1 ever renames a
# venue, add it to ``LOCATION_ALIAS_GROUPS`` in :mod:`.location_aliases`
# so the cross-source scan still matches. 2025 isn't included here
# because the test runs against the warm cache under ``.cache/openf1``;
# no 2025 meetings are cached in this session.
_FASTF1_LOCATIONS_BY_SEASON = {
    # 2023: no Chinese GP (COVID-era cancellation lingered).
    2023: (
        "Sakhir", "Jeddah", "Melbourne", "Baku", "Miami", "Imola", "Monaco",
        "Barcelona", "Montréal", "Spielberg", "Silverstone", "Budapest",
        "Spa-Francorchamps", "Zandvoort", "Monza", "Marina Bay", "Suzuka",
        "Lusail", "Austin", "Mexico City", "São Paulo", "Las Vegas",
        "Yas Island",
    ),
    2024: (
        "Sakhir", "Jeddah", "Melbourne", "Suzuka", "Shanghai", "Miami",
        "Imola", "Monaco", "Montréal", "Barcelona", "Spielberg",
        "Silverstone", "Budapest", "Spa-Francorchamps", "Zandvoort",
        "Monza", "Baku", "Marina Bay", "Austin", "Mexico City",
        "São Paulo", "Las Vegas", "Lusail", "Yas Island",
    ),
}


@pytest.mark.parametrize("season", [2023, 2024])
def test_every_fastf1_location_resolves_through_openf1_find_meeting(
    client: OpenF1Client, season: int,
):
    """For every FastF1 2023–2024 ``Location`` string, at least one
    alias in :func:`location_group` matches an OpenF1 race meeting in
    the same season. This confirms the router's cross-source past-race
    scan never silently misses a circuit under its real name.
    """
    meetings = [m for m in client.get("meetings", year=season) if _is_race_meeting(m)]
    unresolved: list[str] = []
    for location in _FASTF1_LOCATIONS_BY_SEASON[season]:
        resolved = False
        for alias in sorted(location_group(location)):
            try:
                _find_meeting(meetings, alias)
                resolved = True
                break
            except ValueError:
                continue
        if not resolved:
            unresolved.append(location)
    assert not unresolved, (
        f"{season}: FastF1 Locations with no OpenF1 match under their "
        f"alias group: {unresolved}"
    )
