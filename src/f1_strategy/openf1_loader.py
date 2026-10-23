"""Load a 2023+ race weekend from OpenF1 into the race weekend description.

This is the only module that knows about OpenF1's JSON shapes. It turns
responses fetched through :class:`.openf1_client.OpenF1Client` into the
plain, project-owned :class:`.weekend.RaceWeekend` that the predictor
reads, mirroring :mod:`.fastf1_loader` field for field. Routing between
the two loaders by season lives in ticket 23.

Ticket 21 covers the pre-race side only: ``PreRaceInfo`` plus one
``Session`` per pre-race session (FP1--FP3 for a conventional weekend;
FP1, Sprint Qualifying, Sprint and Qualifying for a sprint weekend)
with its ``Lap`` tuple. The race outcome (``RaceOutcome.stints``,
``neutralisations``, ``finishing_status``), Pit Loss and Historical
Degradation are ticket 22. Pre-race information already needs
``race_laps`` (it is a ``PreRaceInfo`` field, read before the race),
so this module fetches it from ``/v1/session_result`` for the race
session; everything else about the race is left to ticket 22.

Field-by-field recipes verified against real OpenF1 responses in
``.scratch/full-backtest/openf1-findings.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol

from .openf1_client import OpenF1Client
from .weekend import (
    Compound,
    Lap,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    Session,
)


_COMPOUND = {
    "SOFT": Compound.SOFT,
    "MEDIUM": Compound.MEDIUM,
    "HARD": Compound.HARD,
    "INTERMEDIATE": Compound.INTERMEDIATE,
    "WET": Compound.WET,
}

# OpenF1's `session_name` → short identifiers used in `Session.name`,
# matching :mod:`.fastf1_loader._SESSION_SHORT_NAME` so a weekend
# description looks the same whichever loader built it. Both the 2023
# "Sprint Shootout" and the 2024 "Sprint Qualifying" names map to SQ,
# because the two labels name the same session (F1 renamed it, OpenF1
# follows the official name of the year).
_SESSION_SHORT_NAME = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint": "S",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
}

# Pre-race sessions in the order the predictor expects them. Both
# formats are read from the OpenF1 session list and filtered through
# this tuple so FP1 comes before FP2/SQ, SQ before S, S before Q, etc.
# This mirrors the FastF1 loader's `event["Session1"]..event["Session4"]`
# order.
_PRE_RACE_ORDER = ("FP1", "FP2", "FP3", "SQ", "S", "Q")


class _OpenF1Client(Protocol):
    """Narrow seam used by the loader.

    Any object with a ``get(endpoint, **params) -> list[dict]`` method
    works, so a fast test can pass a fixture-backed fake without a real
    cache dir or network stack.
    """

    def get(self, endpoint: str, **params: Any) -> list[dict]: ...


def load_weekend(
    season: int,
    event: str,
    *,
    client: _OpenF1Client | None = None,
    cache_dir: str | Path = ".cache/openf1",
) -> RaceWeekend:
    """Load an OpenF1 race weekend into the project's weekend description.

    ``season`` must be 2023 or later (OpenF1 only covers 2023 onward;
    [ADR-0006](docs/adr/0006-per-season-data-source.md) sends earlier
    seasons through :mod:`.fastf1_loader`). ``event`` is matched against
    the meeting's ``meeting_name``, ``location`` or ``country_name``,
    case-insensitively; the first match wins.

    ``client`` is the HTTP client (ticket 20). When ``None``, a default
    :class:`.openf1_client.OpenF1Client` pointing at ``cache_dir`` is
    built; tests inject a fixture-backed fake instead so no test touches
    the network.

    The returned ``RaceWeekend``'s ``race`` is an empty ``RaceOutcome``
    and its ``pre_race.pit_loss`` is 0.0 with empty ``pit_loss_seasons``
    — ticket 22 fills those in from past races, matching
    ``fastf1_loader``'s approach. ``PreRaceInfo.race_laps`` is populated
    now because it is pre-race information the predictor reads before
    the race.
    """
    if client is None:
        client = OpenF1Client(cache_dir=Path(cache_dir))

    meetings = client.get("meetings", year=season)
    meeting = _find_meeting(meetings, event)

    sessions_meta = client.get("sessions", meeting_key=meeting["meeting_key"])
    session_names = {s["session_name"] for s in sessions_meta}
    is_sprint = _is_sprint_weekend(session_names)

    race_meta = _session_named(sessions_meta, "Race")
    quali_meta = _session_named(sessions_meta, "Qualifying")

    race_drivers = client.get("drivers", session_key=race_meta["session_key"])
    tla_by_num = {int(d["driver_number"]): str(d["name_acronym"]) for d in race_drivers}

    teams = _teams(
        client,
        drivers=race_drivers,
        quali_session_key=quali_meta["session_key"],
    )

    pre_race_sessions = tuple(
        _load_pre_race_session(client, s, tla_by_num=tla_by_num)
        for s in _ordered_pre_race_sessions(sessions_meta)
    )

    race_laps = _race_laps_count(client, race_meta["session_key"])
    circuit = str(meeting["location"])

    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit=circuit,
            season=season,
            race_laps=race_laps,
            is_sprint_weekend=is_sprint,
            sessions=pre_race_sessions,
            teams=teams,
            # Ticket 22 computes real Pit Loss and Historical Degradation
            # from past races; a 0.0 placeholder keeps the type intact.
            pit_loss=0.0,
            pit_loss_seasons=(),
            estimated_pit_loss=False,
        ),
        race=RaceOutcome(),
    )


# ---------------------------------------------------------------------------
# Meeting selection and schedule derivation.
# ---------------------------------------------------------------------------


def _find_meeting(meetings: list[dict], event: str) -> dict:
    """First meeting whose ``meeting_name``, ``location`` or
    ``country_name`` matches ``event``, case-insensitively.

    Testing weekends are skipped: OpenF1 includes "Pre-Season Testing"
    in the yearly meeting list, which ``list_season`` (ticket 23) also
    needs to filter out. Matching is a lowercase substring test so a
    caller can pass "Monza", "Italian Grand Prix" or "Italy" and reach
    the same row.
    """
    needle = event.strip().lower()
    for row in meetings:
        if not _is_race_meeting(row):
            continue
        for field in ("meeting_name", "location", "country_name"):
            value = row.get(field)
            if value is None:
                continue
            if needle in str(value).lower():
                return row
    raise ValueError(
        f"no OpenF1 meeting matched event={event!r}; "
        f"searched {len(meetings)} rows"
    )


def _is_race_meeting(row: dict) -> bool:
    """True for a real Grand Prix meeting, False for pre-season testing.

    Testing rounds appear as a plain "Pre-Season Testing" row (no
    "Grand Prix" in the name); every championship round's
    ``meeting_name`` ends in "Grand Prix". Matching on the suffix is
    the simplest derivation the findings table supports.
    """
    name = str(row.get("meeting_name", "")).lower()
    return "grand prix" in name


def _round_number(meetings: list[dict], target: dict) -> int:
    """Round number from meeting date order, 1-indexed.

    OpenF1's ``/v1/meetings`` has no round-number field (see the
    findings table). The yearly listing's non-testing rows, sorted by
    ``date_start`` ascending, carry the championship round number
    implicitly. Exposed as a module-private helper so ticket 23's
    ``list_season`` can call it without re-deriving the rule.
    """
    races = sorted(
        (m for m in meetings if _is_race_meeting(m)),
        key=lambda m: m["date_start"],
    )
    for i, m in enumerate(races, start=1):
        if m.get("meeting_key") == target.get("meeting_key"):
            return i
    raise ValueError(
        f"target meeting {target.get('meeting_key')!r} is not in the race list"
    )


def _is_sprint_weekend(session_names: set[str]) -> bool:
    """A sprint weekend's session set contains a "Sprint" session.

    The two formats seen in 2023--2025:
    - Conventional: {Practice 1, Practice 2, Practice 3, Qualifying, Race}
    - Sprint: {Practice 1, Sprint Qualifying, Sprint, Qualifying, Race}

    Testing by the presence of "Sprint" alone catches both the 2023 and
    the 2024+ session labels, since the sprint race itself has kept the
    name "Sprint" through the rename of its qualifier (Sprint Shootout
    → Sprint Qualifying).
    """
    return "Sprint" in session_names


def _session_named(sessions: list[dict], name: str) -> dict:
    for s in sessions:
        if s.get("session_name") == name:
            return s
    raise ValueError(f"no {name!r} session in meeting")


def _ordered_pre_race_sessions(sessions: list[dict]) -> list[dict]:
    """Pre-race sessions in the FP1/FP2/FP3/SQ/S/Q order the predictor
    expects.

    OpenF1 returns sessions roughly in chronological order already, but
    the predictor reads them by short name, not by position, so we
    filter on the mapping in ``_SESSION_SHORT_NAME`` and reorder on the
    canonical pre-race sequence. The race itself is always excluded.
    """
    by_short: dict[str, dict] = {}
    for s in sessions:
        short = _SESSION_SHORT_NAME.get(s.get("session_name", ""))
        if short is None:
            continue
        # If a session name maps to the same short twice (shouldn't
        # happen in real OpenF1 data), the first one wins — matching
        # the "first match" rule used elsewhere in this module.
        by_short.setdefault(short, s)
    return [by_short[short] for short in _PRE_RACE_ORDER if short in by_short]


# ---------------------------------------------------------------------------
# Teams and starters.
# ---------------------------------------------------------------------------


def _teams(
    client: _OpenF1Client,
    *,
    drivers: list[dict],
    quali_session_key: int,
) -> dict[str, str]:
    """Driver TLA → team for every starter of the race.

    OpenF1 attaches the main race's starting grid to the **qualifying**
    session, not the race (`/v1/starting_grid?session_key=<race>`
    returns an empty body). Team names live on `/v1/drivers`; the
    passed-in list is the race session's drivers so a stand-in driver
    who did not appear in a pre-race session is still included.
    """
    drivers_by_num = {int(d["driver_number"]): d for d in drivers}

    grid = client.get("starting_grid", session_key=quali_session_key)
    teams: dict[str, str] = {}
    for row in grid:
        num = int(row["driver_number"])
        driver = drivers_by_num.get(num)
        if driver is None:
            # Starter the race's drivers list doesn't name — rare, but
            # dropping them silently matches the FastF1 loader, which
            # keys teams on race results.
            continue
        tla = str(driver["name_acronym"])
        teams[tla] = str(driver["team_name"])
    return teams


# ---------------------------------------------------------------------------
# Pre-race session laps.
# ---------------------------------------------------------------------------


def _load_pre_race_session(
    client: _OpenF1Client, session_meta: dict, *, tla_by_num: dict[int, str]
) -> Session:
    """Build one ``Session`` from OpenF1's lap/stint/pit endpoints.

    ``tla_by_num`` is read from the race session's ``/v1/drivers`` row
    set and passed in so each pre-race session doesn't re-fetch the
    same (weekend-stable) number→TLA mapping.
    """
    short = _SESSION_SHORT_NAME[session_meta["session_name"]]
    session_key = session_meta["session_key"]

    laps_rows = client.get("laps", session_key=session_key)
    stints_rows = client.get("stints", session_key=session_key)
    pit_rows = client.get("pit", session_key=session_key)

    # Stints indexed by driver → sorted list, so a lap can be matched
    # by its lap_number range in one pass per lap.
    stints_by_driver: dict[int, list[dict]] = {}
    for s in stints_rows:
        stints_by_driver.setdefault(int(s["driver_number"]), []).append(s)
    for driver_stints in stints_by_driver.values():
        driver_stints.sort(key=lambda s: int(s["lap_start"]))

    # Pit laps per driver as a set so pit_in membership is O(1) per lap.
    pit_laps_by_driver: dict[int, set[int]] = {}
    for p in pit_rows:
        pit_laps_by_driver.setdefault(int(p["driver_number"]), set()).add(
            int(p["lap_number"])
        )

    laps = tuple(
        _laps_from(
            laps_rows,
            session_short=short,
            tla_by_num=tla_by_num,
            stints_by_driver=stints_by_driver,
            pit_laps_by_driver=pit_laps_by_driver,
        )
    )
    return Session(name=short, laps=laps)


def _laps_from(
    laps_rows: list[dict],
    *,
    session_short: str,
    tla_by_num: dict[int, str],
    stints_by_driver: dict[int, list[dict]],
    pit_laps_by_driver: dict[int, set[int]],
) -> Iterable[Lap]:
    """One ``Lap`` per usable OpenF1 lap row.

    Skip rules match the FastF1 loader where possible:
    - lap_duration null (observed for in- and out-laps whose timing was
      not captured, and for invalidated laps);
    - no matching stint (observed when OpenF1 recorded a lap under a
      driver number that has no stint entry; the ticket 21 ambiguity
      decision below records this as "skip").

    The derivations themselves come straight from
    ``openf1-findings.md``:
    - ``compound`` from the stint whose range covers the lap;
    - ``tyre_age = (lap_number - stint.lap_start) + 1 + tyre_age_at_start``;
    - ``new_when_fitted = (stint.tyre_age_at_start == 0)``;
    - ``pit_in`` from set membership of the ``/v1/pit`` lap numbers;
    - ``pit_out`` from ``is_pit_out_lap``.
    """
    for row in laps_rows:
        duration = row.get("lap_duration")
        if duration is None:
            continue
        number = int(row["lap_number"])
        driver_num = int(row["driver_number"])
        driver = tla_by_num.get(driver_num)
        if driver is None:
            # Lap row for a driver who isn't in the drivers list for
            # this session — defensive; dropping it matches the FastF1
            # loader skipping rows with no useful tyre/driver info.
            continue
        stint = _stint_for_lap(stints_by_driver.get(driver_num, ()), number)
        if stint is None:
            continue
        compound = _COMPOUND.get(str(stint["compound"]).upper())
        if compound is None:
            continue
        age_at_start = int(stint.get("tyre_age_at_start", 0))
        tyre_age = (number - int(stint["lap_start"])) + 1 + age_at_start
        stint_number = int(stint.get("stint_number", 0))
        yield Lap(
            driver=driver,
            lap_number=number,
            lap_time=float(duration),
            # Matches the FastF1 loader's recipe
            # ``f"{driver}-{session}-stint{N}-{compound}"``, so a tyre_set
            # id built from either loader has the same shape.
            tyre_set=f"{driver}-{session_short}-stint{stint_number}-{compound.value}",
            compound=compound,
            tyre_age=tyre_age,
            new_when_fitted=age_at_start == 0,
            pit_in=number in pit_laps_by_driver.get(driver_num, set()),
            pit_out=bool(row.get("is_pit_out_lap", False)),
            # Pre-race sessions have no per-lap TrackStatus equivalent
            # in OpenF1, so neutralisation isn't reconstructed here.
            # ``_lap_neutralisation_kind`` in the FastF1 loader produces
            # the same answer for every lap of a green practice session
            # (False); the (rare) red-flag practice case diverges, and
            # is recorded as a known limitation in ticket 21.
            neutralised=False,
        )


def _stint_for_lap(driver_stints: Iterable[dict], lap_number: int) -> dict | None:
    """The stint whose ``[lap_start, lap_end]`` range contains ``lap_number``.

    OpenF1's stints are closed intervals (both ends inclusive) per the
    findings. A lap that falls outside every stint range gets ``None``
    and is skipped by ``_laps_from``.
    """
    for s in driver_stints:
        if int(s["lap_start"]) <= lap_number <= int(s["lap_end"]):
            return s
    return None


# ---------------------------------------------------------------------------
# Race laps count (pre-race info).
# ---------------------------------------------------------------------------


def _race_laps_count(client: _OpenF1Client, race_session_key: int) -> int:
    """The race's scheduled lap count, from the winner's ``number_of_laps``.

    OpenF1's ``/v1/session_result`` gives one row per driver with their
    completed lap count. Taking the max across the result set equals the
    winner's lap count (DNFs have fewer laps), which equals the race's
    scheduled lap count unless the race is red-flagged short — a case
    the FastF1 loader (reading ``race.total_laps``) also inherits
    whichever way F1 recorded the shortened length.
    """
    result = client.get("session_result", session_key=race_session_key)
    if not result:
        raise ValueError(
            f"OpenF1 /v1/session_result returned no rows for race session "
            f"{race_session_key!r}; cannot derive race_laps"
        )
    return max(int(row["number_of_laps"]) for row in result)
