"""Load a 2023+ race weekend from OpenF1 into the race weekend description.

This is the only module that knows about OpenF1's JSON shapes. It turns
responses fetched through :class:`.openf1_client.OpenF1Client` into the
plain, project-owned :class:`.weekend.RaceWeekend` that the predictor
reads, mirroring :mod:`.fastf1_loader` field for field. Routing between
the two loaders by season lives in ticket 23.

Ticket 21 covers the pre-race side: ``PreRaceInfo`` plus one ``Session``
per pre-race session, with ``Lap`` tuples. Ticket 22 adds the race
outcome (``RaceOutcome.stints``, ``neutralisations``,
``finishing_status``), measured Pit Loss and Historical Degradation.

Pit Loss and Historical Degradation here read **only** OpenF1 seasons
(2023 and later). A 2024 race finds Monza 2023 by itself; a 2023 race
has no OpenF1 history at all. Combining a 2022 FastF1 sample with the
OpenF1 samples for a 2024 race is ticket 23's job: :func:`load_past_race_samples`
is the public seam ticket 23 calls per past OpenF1 season to collect raw
pit-loss and stint-rate samples, then merges them with the FastF1
loader's parallel helper under one season-weighted aggregation.

Field-by-field recipes verified against real OpenF1 responses in
``.scratch/full-backtest/openf1-findings.md``. Pit Loss never uses
``/v1/pit.pit_duration`` because that field counts red-flag parking as
a pit stop (observed mean 661 s at São Paulo 2024); the lap-time
algorithm from :mod:`.fastf1_loader._pit_losses_in` is ported here on
top of the race-control-reconstructed neutralisation ranges.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .backtest import RaceSpec
from .location_aliases import location_group
from .openf1_client import OpenF1Client
from .regulation_era import era_start
from .weekend import (
    DRY_COMPOUNDS,
    Compound,
    HistoricalDegradation,
    Lap,
    NeutralisationPeriod,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    Session,
    Stint,
)


_LOGGER = logging.getLogger(__name__)

# OpenF1's historical coverage begins in 2023 (ADR-0006; `/v1/meetings`
# returns zero rows for 2018-2022). A past-race scan from this loader
# will not even try to fetch earlier seasons; crossing the boundary is
# ticket 23's job.
OPENF1_FIRST_SEASON = 2023


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
    fuel_effect_s_per_lap: float = 0.03,
    history_min_stint_length: int = 4,
    measure_history: Callable[
        [str, int],
        tuple[float, tuple[int, ...], bool, dict[Compound, HistoricalDegradation]],
    ]
    | None = None,
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

    ``measure_history`` is the ticket-23 cross-source hook: when provided,
    it is called as ``measure_history(circuit, race_season)`` to produce
    ``(pit_loss, pit_loss_seasons, estimated_pit_loss,
    historical_degradation)`` from past races across both data sources
    plus the pit-lane-table fallback. When ``None`` (the direct-loader
    path kept for the fast tests and for callers that only want OpenF1),
    the past-race scan is OpenF1-only and ``estimated_pit_loss`` is
    always ``False``; ticket 22's open question still applies on that
    path, so top-level callers should go through :mod:`.data` instead of
    calling this function directly for 2023+ races.

    ``fuel_effect_s_per_lap`` and ``history_min_stint_length`` match the
    FastF1 loader's defaults so rates are directly comparable across
    sources.
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

    race_session_key = int(race_meta["session_key"])
    race_rows = _load_race_rows(client, race_session_key)
    race_laps = _race_laps_count(race_rows["session_result"], race_session_key)
    neutralisations, _warnings = _neutralisation_periods(
        race_rows["race_control"], race_laps
    )
    neutralised_laps = _neutralised_lap_set(neutralisations)
    stints = _race_stints(
        race_rows["stints"], tla_by_num=tla_by_num, drivers=set(teams)
    )
    finishing_status = _finishing_status(
        race_rows["session_result"], tla_by_num=tla_by_num, drivers=set(teams)
    )

    circuit = str(meeting["location"])
    if measure_history is None:
        pit_loss, pit_loss_seasons, historical_degradation = _past_races_at_circuit(
            circuit=circuit,
            race_season=season,
            client=client,
            fuel_effect_s_per_lap=fuel_effect_s_per_lap,
            history_min_stint_length=history_min_stint_length,
        )
        estimated_pit_loss = False
    else:
        (
            pit_loss,
            pit_loss_seasons,
            estimated_pit_loss,
            historical_degradation,
        ) = measure_history(circuit, season)

    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit=circuit,
            season=season,
            race_laps=race_laps,
            is_sprint_weekend=is_sprint,
            sessions=pre_race_sessions,
            teams=teams,
            pit_loss=pit_loss,
            pit_loss_seasons=pit_loss_seasons,
            estimated_pit_loss=estimated_pit_loss,
            historical_degradation=historical_degradation,
        ),
        race=RaceOutcome(
            stints=stints,
            neutralisations=neutralisations,
            finishing_status=finishing_status,
        ),
    )


# ---------------------------------------------------------------------------
# Meeting selection and schedule derivation.
# ---------------------------------------------------------------------------


def list_season(
    season: int,
    *,
    client: _OpenF1Client | None = None,
    cache_dir: str | Path = ".cache/openf1",
) -> list[RaceSpec]:
    """Every race weekend in a 2023+ season, in round order, with sprints marked.

    Parallel to :func:`.fastf1_loader.list_season` so both return the
    same ``RaceSpec`` list shape (``event`` is the full "<Country> Grand
    Prix" meeting name, matching FastF1's ``EventName`` column). Round
    order is :func:`_round_number`'s derivation (meetings sorted by
    ``date_start``, 1-indexed). Pre-season testing meetings are filtered
    out by :func:`_is_race_meeting`, same rule :func:`_find_meeting`
    uses so a season listing never contains anything a load call could
    not resolve.

    Sprint detection reads each meeting's ``/v1/sessions`` endpoint: the
    presence of a "Sprint" session marks the weekend as sprint. One
    extra request per meeting on a cold cache; the OpenF1 client caches
    them on disk so a re-run is zero requests.
    """
    if client is None:
        client = OpenF1Client(cache_dir=Path(cache_dir))
    meetings = client.get("meetings", year=season)
    races = sorted(
        (m for m in meetings if _is_race_meeting(m)),
        key=lambda m: m["date_start"],
    )
    specs: list[RaceSpec] = []
    for meeting in races:
        sessions_meta = client.get(
            "sessions", meeting_key=meeting["meeting_key"]
        )
        session_names = {s.get("session_name", "") for s in sessions_meta}
        specs.append(
            RaceSpec(
                season=season,
                event=str(meeting["meeting_name"]),
                is_sprint_weekend=_is_sprint_weekend(session_names),
            )
        )
    return specs


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


def _race_laps_count(result: list[dict], race_session_key: int) -> int:
    """The race's scheduled lap count, from the winner's ``number_of_laps``.

    Reads ``/v1/session_result`` rows (one per driver), taking the max
    ``number_of_laps``. Equals the winner's lap count (DNFs have fewer),
    which equals the race's scheduled lap count unless the race is
    red-flagged short — a case the FastF1 loader (reading
    ``race.total_laps``) also inherits whichever way F1 recorded the
    shortened length.
    """
    if not result:
        raise ValueError(
            f"OpenF1 /v1/session_result returned no rows for race session "
            f"{race_session_key!r}; cannot derive race_laps"
        )
    laps = [row.get("number_of_laps") for row in result]
    valid = [int(x) for x in laps if x is not None]
    if not valid:
        raise ValueError(
            f"OpenF1 /v1/session_result rows for race session "
            f"{race_session_key!r} carry no number_of_laps"
        )
    return max(valid)


# ---------------------------------------------------------------------------
# Race-side loader (ticket 22).
# ---------------------------------------------------------------------------


def _load_race_rows(
    client: _OpenF1Client, race_session_key: int
) -> dict[str, list[dict]]:
    """Fetch the four race-session endpoints the race-side builders read.

    One shared fetch keeps request budgeting predictable: four endpoints
    per weekend's race session, cached by the client. Kept separate from
    ``_load_past_race_rows`` so the target weekend fetch and the past-
    season scan have independent request shapes.
    """
    return {
        "laps": client.get("laps", session_key=race_session_key),
        "stints": client.get("stints", session_key=race_session_key),
        "pit": client.get("pit", session_key=race_session_key),
        "race_control": client.get("race_control", session_key=race_session_key),
        "session_result": client.get(
            "session_result", session_key=race_session_key
        ),
    }


def _race_stints(
    stints_rows: list[dict], *, tla_by_num: dict[int, str], drivers: set[str]
) -> tuple[Stint, ...]:
    """Group OpenF1 stint rows into ``Stint`` tuples, keyed on TLA.

    Mirrors :func:`.fastf1_loader._race_stints`: one ``Stint`` per
    ``/v1/stints`` row whose compound is a known value, keyed on TLA
    rather than driver number so the race outcome's shape matches the
    FastF1 loader exactly. Non-dry compounds (INTERMEDIATE, WET) are
    kept — the FastF1 loader keeps them too; downstream code (``predict``,
    the Dry Race filter) rejects a wet race based on the stint list.
    Rows for drivers not in ``drivers`` (DNS, dropped from the starter
    set) are skipped so a stint for a driver who did not start the race
    doesn't surface.
    """
    out: list[Stint] = []
    for row in stints_rows:
        driver_num = int(row["driver_number"])
        tla = tla_by_num.get(driver_num)
        if tla is None or tla not in drivers:
            continue
        compound = _COMPOUND.get(str(row.get("compound", "")).upper())
        if compound is None:
            continue
        # Real OpenF1 returns some ``/v1/stints`` rows with ``lap_start``
        # or ``lap_end`` set to ``null`` — observed for a driver whose
        # stint never completed its first flying lap (e.g. a lap-1 crash)
        # or whose compound was never actually mounted (DNS allocation
        # row). Those rows carry no information the predictor can use, so
        # skip them rather than crash on ``int(None)``.
        start = row.get("lap_start")
        end = row.get("lap_end")
        if start is None or end is None:
            continue
        out.append(
            Stint(
                driver=tla,
                compound=compound,
                start_lap=int(start),
                end_lap=int(end),
            )
        )
    out.sort(key=lambda s: (s.driver, s.start_lap))
    return tuple(out)


def _finishing_status(
    result_rows: list[dict],
    *,
    tla_by_num: dict[int, str],
    drivers: set[str],
) -> dict[str, bool]:
    """``took_flag = not dnf and not dns and not dsq`` per starter.

    OpenF1 flags DNFs, DNSs and DSQs with explicit booleans on
    ``/v1/session_result``, so finishing status is the negation of the
    disjunction. Matches :func:`.fastf1_loader._finishing_status`'s
    "lapped finishers took the flag" semantics (lapped finishers have
    ``dnf=False`` on OpenF1 too). Rows for drivers not in ``drivers``
    are ignored so a reserve driver who appears only on
    ``/v1/session_result`` isn't added to the starter-indexed dict.
    """
    out: dict[str, bool] = {}
    for row in result_rows:
        driver_num = int(row["driver_number"])
        tla = tla_by_num.get(driver_num)
        if tla is None or tla not in drivers:
            continue
        dnf = bool(row.get("dnf", False))
        dns = bool(row.get("dns", False))
        dsq = bool(row.get("dsq", False))
        out[tla] = not (dnf or dns or dsq)
    return out


# -- Neutralisation reconstruction -----------------------------------------


# `/v1/race_control.message` substrings that start or end a VSC or SC
# period. Matched case-insensitively. Red flag is deliberately not here:
# the FastF1 loader's `_lap_neutralisation_kind` ignores red flag (code
# 5) too, and ADR-0004 doesn't class red-flag laps as neutralised.
_VSC_START = "VIRTUAL SAFETY CAR DEPLOYED"
_VSC_END = "VIRTUAL SAFETY CAR ENDING"
_SC_START = "SAFETY CAR DEPLOYED"
_SC_END = "SAFETY CAR IN THIS LAP"


def _neutralisation_periods(
    race_control_rows: list[dict], race_laps: int
) -> tuple[tuple[NeutralisationPeriod, ...], tuple[str, ...]]:
    """Reconstruct SC/VSC periods from ``/v1/race_control`` events.

    OpenF1 has no per-lap TrackStatus, so neutralisation ranges are
    rebuilt from the start / end messages the findings table pins:
    ``VIRTUAL SAFETY CAR DEPLOYED`` opens a VSC that
    ``VIRTUAL SAFETY CAR ENDING`` closes on the same ``lap_number``;
    ``SAFETY CAR DEPLOYED`` opens an SC that ``SAFETY CAR IN THIS LAP``
    closes on its own ``lap_number`` (the "in this lap" message fires
    on the lap the SC comes in, which is the last lap of the period).

    If an "end" event is missing (a known gap in OpenF1's feed), the
    period is capped at the race lap count and a quality warning is
    returned. Returned warnings are also logged at WARNING level so the
    Backtest's output carries them without needing to pass the tuple
    through to the caller.

    Returns ``(periods, warnings)``. Both are tuples in event order,
    merged into the shape ``RaceOutcome.neutralisations`` already
    carries (``NeutralisationPeriod(kind, start_lap, end_lap)``).
    """
    periods: list[NeutralisationPeriod] = []
    warnings: list[str] = []
    open_vsc_lap: int | None = None
    open_sc_lap: int | None = None

    for row in race_control_rows:
        message = str(row.get("message", "")).upper()
        lap = row.get("lap_number")
        if lap is None:
            continue
        lap_num = int(lap)
        if _VSC_START in message:
            open_vsc_lap = lap_num
        elif _VSC_END in message:
            if open_vsc_lap is not None:
                periods.append(
                    NeutralisationPeriod("VSC", open_vsc_lap, lap_num)
                )
                open_vsc_lap = None
        elif _SC_START in message:
            open_sc_lap = lap_num
        elif _SC_END in message:
            if open_sc_lap is not None:
                periods.append(NeutralisationPeriod("SC", open_sc_lap, lap_num))
                open_sc_lap = None

    if open_vsc_lap is not None:
        warning = (
            f"VSC deployed on lap {open_vsc_lap} has no ending event; "
            f"capped at race lap count {race_laps}"
        )
        _LOGGER.warning(warning)
        warnings.append(warning)
        periods.append(NeutralisationPeriod("VSC", open_vsc_lap, race_laps))
    if open_sc_lap is not None:
        warning = (
            f"SC deployed on lap {open_sc_lap} has no ending event; "
            f"capped at race lap count {race_laps}"
        )
        _LOGGER.warning(warning)
        warnings.append(warning)
        periods.append(NeutralisationPeriod("SC", open_sc_lap, race_laps))

    periods.sort(key=lambda p: (p.start_lap, p.end_lap))
    return tuple(periods), tuple(warnings)


def _neutralised_lap_set(
    periods: Iterable[NeutralisationPeriod],
) -> set[int]:
    """Lap numbers inside any SC or VSC period, as a set for O(1) tests."""
    out: set[int] = set()
    for period in periods:
        out.update(range(period.start_lap, period.end_lap + 1))
    return out


# -- Pit Loss and Historical Degradation samples ----------------------------


@dataclass(frozen=True)
class PastRaceSamples:
    """Raw samples from one past OpenF1 race.

    The seam ticket 23 reads to merge FastF1 and OpenF1 past-race data
    under one season-weighted aggregation. Each entry is a single
    sample: a per-stop pit-loss in seconds, or a (compound, fuel-
    corrected rate, lap count) tuple. The samples are already filtered
    for green-flag running and the clip ranges from the FastF1 loader;
    the merger only has to apply the recent-seasons weight
    ``0.5 ** (gap - 1)`` and the lap-count × season-weight weighted
    mean (same formulas as :func:`.fastf1_loader._past_races_at_circuit`).
    """

    pit_losses: tuple[float, ...]
    stint_rates: tuple[tuple[Compound, float, int], ...]


def _pit_losses_in(
    laps_rows: list[dict],
    pit_rows: list[dict],
    neutralised_laps: set[int],
) -> Iterable[float]:
    """Per-pit-stop time loss from one race's OpenF1 rows, in seconds.

    Ports :func:`.fastf1_loader._pit_losses_in`:

    - Reference pace per driver is the median ``lap_duration`` of green
      racing laps that aren't pit-in, pit-out, lap 1 or neutralised.
    - At least 5 clean reference laps are required (same as FastF1).
    - For each ``/v1/pit`` row, pair the in-lap (that ``lap_number``)
      with the next lap as the out-lap. Both must be non-neutralised and
      have non-null ``lap_duration``. ``is_pit_out_lap`` on the out-lap
      is a free sanity check.
    - Loss is ``(in_lap - ref) + (out_lap - ref)``, clipped to
      ``10 < loss < 60`` (the FastF1 loader's clip).

    Deliberately **never** reads ``/v1/pit.pit_duration``: that field
    counts red-flag parking as a pit stop (findings, mean 661 s at
    São Paulo 2024). The lap-time algorithm doesn't need it.
    """
    laps_by_driver: dict[int, list[dict]] = {}
    for row in laps_rows:
        laps_by_driver.setdefault(int(row["driver_number"]), []).append(row)
    pits_by_driver: dict[int, list[int]] = {}
    for row in pit_rows:
        pits_by_driver.setdefault(int(row["driver_number"]), []).append(
            int(row["lap_number"])
        )

    for driver_num, laps in laps_by_driver.items():
        laps_sorted = sorted(laps, key=lambda r: int(r["lap_number"]))
        pit_in_laps = set(pits_by_driver.get(driver_num, []))
        by_lap: dict[int, dict] = {int(r["lap_number"]): r for r in laps_sorted}

        clean_times: list[float] = []
        for row in laps_sorted:
            lap_num = int(row["lap_number"])
            if lap_num <= 1:
                continue
            if lap_num in pit_in_laps:
                continue
            if bool(row.get("is_pit_out_lap", False)):
                continue
            if lap_num in neutralised_laps:
                continue
            duration = row.get("lap_duration")
            if duration is None:
                continue
            clean_times.append(float(duration))
        if len(clean_times) < 5:
            continue
        ref = statistics.median(clean_times)
        if not math.isfinite(ref):
            continue

        for pit_lap in sorted(pit_in_laps):
            in_row = by_lap.get(pit_lap)
            out_row = by_lap.get(pit_lap + 1)
            if in_row is None or out_row is None:
                continue
            if pit_lap in neutralised_laps or (pit_lap + 1) in neutralised_laps:
                continue
            in_time = in_row.get("lap_duration")
            out_time = out_row.get("lap_duration")
            if in_time is None or out_time is None:
                continue
            loss = (float(in_time) - ref) + (float(out_time) - ref)
            if 10.0 < loss < 60.0:
                yield loss


def _historical_stint_rates(
    laps_rows: list[dict],
    stints_rows: list[dict],
    pit_rows: list[dict],
    neutralised_laps: set[int],
    fuel_effect_s_per_lap: float,
    min_stint_length: int,
) -> Iterable[tuple[Compound, float, int]]:
    """Per-Stint fuel-corrected Degradation rates from one OpenF1 race.

    Ports :func:`.fastf1_loader._historical_stint_rates`. For each stint
    whose compound is dry, pick out the laps in its range from
    ``laps_rows``, drop any that are pit-in (``lap_number`` in
    ``/v1/pit``), pit-out (``is_pit_out_lap``), neutralised, or missing
    ``lap_duration``. Keep the longest run of strictly consecutive
    tyre-age values and fit a least-squares slope; add the fuel effect
    and yield ``(compound, rate, lap_count)``. Non-dry compounds
    (INTERMEDIATE, WET) are skipped: the FastF1 helper only yields dry
    rates too, since Historical Degradation is a dry-Compound concept.
    """
    laps_by_driver: dict[int, dict[int, dict]] = {}
    for row in laps_rows:
        laps_by_driver.setdefault(int(row["driver_number"]), {})[
            int(row["lap_number"])
        ] = row
    pits_by_driver: dict[int, set[int]] = {}
    for row in pit_rows:
        pits_by_driver.setdefault(int(row["driver_number"]), set()).add(
            int(row["lap_number"])
        )

    for stint in stints_rows:
        driver_num = int(stint["driver_number"])
        compound = _COMPOUND.get(str(stint.get("compound", "")).upper())
        if compound is None or compound not in DRY_COMPOUNDS:
            continue
        # Null lap_start / lap_end rows are DNS / unused-allocation rows
        # (see ``_race_stints``); they can't produce a Degradation sample.
        lap_start = stint.get("lap_start")
        lap_end = stint.get("lap_end")
        if lap_start is None or lap_end is None:
            continue
        start = int(lap_start)
        end = int(lap_end)
        age_at_start = int(stint.get("tyre_age_at_start") or 0)
        driver_laps = laps_by_driver.get(driver_num, {})
        pit_in_laps = pits_by_driver.get(driver_num, set())

        clean: list[tuple[int, float]] = []
        for lap_num in range(start, end + 1):
            row = driver_laps.get(lap_num)
            if row is None:
                continue
            if lap_num in pit_in_laps:
                continue
            if bool(row.get("is_pit_out_lap", False)):
                continue
            if lap_num in neutralised_laps:
                continue
            duration = row.get("lap_duration")
            if duration is None:
                continue
            tyre_age = (lap_num - start) + 1 + age_at_start
            clean.append((tyre_age, float(duration)))
        if len(clean) < min_stint_length:
            continue
        consecutive = _longest_consecutive(clean)
        if len(consecutive) < min_stint_length:
            continue
        rate = _slope(consecutive)
        if rate is None:
            continue
        yield compound, rate + fuel_effect_s_per_lap, len(consecutive)


def _longest_consecutive(
    points: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """Longest sub-sequence of ``(tyre_age, lap_time)`` whose tyre_age
    increases by exactly 1 each step. Ties keep the first.

    Same shape as :func:`.fastf1_loader._longest_consecutive`.
    """
    best: list[tuple[int, float]] = []
    current: list[tuple[int, float]] = []
    last_age: int | None = None
    for age, time in points:
        if last_age is not None and age == last_age + 1:
            current.append((age, time))
        else:
            current = [(age, time)]
        if len(current) > len(best):
            best = list(current)
        last_age = age
    return best


def _slope(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope of lap time against tyre age. ``None`` if the
    ages don't vary. Same shape as :func:`.fastf1_loader._slope`."""
    mean_x = statistics.fmean(x for x, _ in points)
    mean_y = statistics.fmean(y for _, y in points)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx <= 0:
        return None
    return sxy / sxx


# -- Past-race aggregation -------------------------------------------------


def load_past_race_samples(
    client: _OpenF1Client,
    season: int,
    event: str,
    *,
    fuel_effect_s_per_lap: float = 0.03,
    history_min_stint_length: int = 4,
) -> PastRaceSamples:
    """Collect raw Pit Loss and Historical Degradation samples from one
    past OpenF1 race, ready for the ticket 23 cross-source merger.

    Resolves the past race's meeting the same way :func:`load_weekend`
    does (``_find_meeting`` on ``event``, race session on the matched
    meeting), fetches the three endpoints the sample functions read
    (``/v1/laps``, ``/v1/stints``, ``/v1/pit``) plus ``/v1/race_control``
    for green-flag filtering, and returns a :class:`PastRaceSamples`.

    This is the public seam ticket 23 pairs with a parallel FastF1
    helper: the router iterates over past seasons, calls this for the
    OpenF1 branch and the FastF1 equivalent for the FastF1 branch, then
    applies the same per-season weighting
    (``0.5 ** (race_season - season - 1)``) and lap-count × season-
    weight weighted mean already used in
    :func:`.fastf1_loader._past_races_at_circuit`.
    """
    rows = _load_past_race_rows(client, season, event)
    if rows is None:
        return PastRaceSamples(pit_losses=(), stint_rates=())
    race_laps_count = _race_laps_count(
        rows["session_result"], rows["session_key"]
    )
    periods, _warnings = _neutralisation_periods(
        rows["race_control"], race_laps_count
    )
    neutralised = _neutralised_lap_set(periods)
    losses = tuple(
        _pit_losses_in(rows["laps"], rows["pit"], neutralised)
    )
    rates = tuple(
        _historical_stint_rates(
            rows["laps"],
            rows["stints"],
            rows["pit"],
            neutralised,
            fuel_effect_s_per_lap,
            history_min_stint_length,
        )
    )
    return PastRaceSamples(pit_losses=losses, stint_rates=rates)


def _load_past_race_rows(
    client: _OpenF1Client, season: int, event: str
) -> dict[str, Any] | None:
    """Fetch the row sets needed to measure Pit Loss and Historical
    Degradation from one past OpenF1 race. ``None`` when no OpenF1
    meeting matches (e.g. a 2022 race, outside OpenF1's coverage, which
    ticket 23 will route to FastF1 instead).

    The past-race scan reads the same four race-session endpoints as
    the target weekend, plus ``/v1/session_result`` for the race lap
    count that caps a missing SC/VSC "end" event.
    """
    try:
        meetings = client.get("meetings", year=season)
    except Exception:
        return None
    try:
        meeting = _find_meeting(meetings, event)
    except ValueError:
        return None
    sessions_meta = client.get("sessions", meeting_key=meeting["meeting_key"])
    try:
        race_meta = _session_named(sessions_meta, "Race")
    except ValueError:
        return None
    race_session_key = int(race_meta["session_key"])
    return {
        "session_key": race_session_key,
        "laps": client.get("laps", session_key=race_session_key),
        "stints": client.get("stints", session_key=race_session_key),
        "pit": client.get("pit", session_key=race_session_key),
        "race_control": client.get(
            "race_control", session_key=race_session_key
        ),
        "session_result": client.get(
            "session_result", session_key=race_session_key
        ),
    }


def _past_races_at_circuit(
    *,
    circuit: str,
    race_season: int,
    client: _OpenF1Client,
    fuel_effect_s_per_lap: float,
    history_min_stint_length: int,
) -> tuple[float, tuple[int, ...], dict[Compound, HistoricalDegradation]]:
    """Load each previous OpenF1 season's race at the circuit and read
    both Pit Loss and Historical Degradation from it.

    Mirrors :func:`.fastf1_loader._past_races_at_circuit`'s shape: the
    same ``0.5 ** (gap - 1)`` recent-seasons weight for Pit Loss, the
    same lap-count × season-weight weighted mean for Historical
    Degradation, same alias group for cross-year venue renames (ticket
    16). The one difference is the season range: OpenF1 starts at 2023,
    and seasons < 2023 are not scanned here (ticket 23 adds the FastF1
    branch for them).

    An empty past-season range (a 2023 race, where
    ``[max(era_start, 2023), 2023) == []``) returns
    ``(0.0, (), {})``. Not an error: ticket 23's merger will add the
    2022 FastF1 samples for that case.
    """
    min_season = max(era_start(race_season), OPENF1_FIRST_SEASON)
    circuit_aliases = location_group(circuit)
    pit_weighted: list[tuple[float, float, int]] = []
    hist_samples: dict[Compound, list[tuple[float, int, float, int]]] = {
        c: [] for c in DRY_COMPOUNDS
    }
    for season in range(min_season, race_season):
        for alias in sorted(circuit_aliases):
            try:
                samples = load_past_race_samples(
                    client,
                    season,
                    alias,
                    fuel_effect_s_per_lap=fuel_effect_s_per_lap,
                    history_min_stint_length=history_min_stint_length,
                )
            except Exception:
                continue
            if not samples.pit_losses and not samples.stint_rates:
                continue
            weight = 0.5 ** (race_season - season - 1)
            losses = sorted(samples.pit_losses)
            if losses:
                pit_weighted.append(
                    (losses[len(losses) // 2], weight, season)
                )
            for compound, rate, lap_count in samples.stint_rates:
                hist_samples[compound].append(
                    (rate, lap_count, weight, season)
                )

    if not pit_weighted:
        pit_loss: float = 0.0
        pit_loss_seasons: tuple[int, ...] = ()
    else:
        total_weight = sum(w for _, w, _ in pit_weighted)
        pit_loss = sum(m * w for m, w, _ in pit_weighted) / total_weight
        pit_loss_seasons = tuple(sorted({s for _, _, s in pit_weighted}))

    historical_degradation: dict[Compound, HistoricalDegradation] = {}
    for compound, samples_list in hist_samples.items():
        if not samples_list:
            continue
        weights = [n * w for _, n, w, _ in samples_list]
        total = sum(weights)
        rate = sum(r * x for (r, _, _, _), x in zip(samples_list, weights)) / total
        seasons_used = tuple(sorted({s for _, _, _, s in samples_list}))
        historical_degradation[compound] = HistoricalDegradation(
            rate=rate,
            seasons=seasons_used,
            stint_count=len(samples_list),
        )
    return pit_loss, pit_loss_seasons, historical_degradation
