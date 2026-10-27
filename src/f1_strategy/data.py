"""Season router (ticket 23): one ``load_weekend`` / ``list_season`` facade.

Top-level callers (``cli``, Backtest, Smoke Set) go through this module
instead of importing :mod:`.fastf1_loader` or :mod:`.openf1_loader`
directly. The facade:

- Dispatches each ``(season, event)`` to the right source — OpenF1 for
  2023+ (ADR-0006) and FastF1 for 2022 and earlier.
- Does the past-race history scan per past season across both sources,
  so a 2024 race combines its 2022 FastF1 sample with its 2023 OpenF1
  sample under one shared weighting (ADR-0004 + ADR-0006).
- Enforces the pit-loss guard: a race whose cross-source Pit Loss comes
  back empty either reaches the pre-era FastF1 fallback (ADR-0004
  exception for 2022 first-season circuits), falls back to the
  pit-lane-table estimate (ticket 07 / ticket 25), or raises so the
  Backtest records a ``DATA_UNAVAILABLE`` Excluded Race. ``pit_loss =
  0.0`` with empty ``pit_loss_seasons`` never reaches ``predict()``, so
  :mod:`.simulator`'s ``pit_loss * (len(compounds) - 1)`` term can't
  silently zero out multi-stop Candidate Strategies (ticket 22's open
  question).

The alias group from :mod:`.location_aliases` (ticket 16) is honoured
in both branches, so a venue renamed between seasons still gets its
earlier races picked up. Each past race counts once per season however
many alias names reach it, by the source's own race identity
(:attr:`PastRaceSamples.race_id`, ticket 38).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import fastf1_loader, openf1_loader
from .backtest import RaceSpec
from .location_aliases import location_group
from .offline import NotDownloadedError
from .openf1_client import OpenF1Client, OpenF1FetchError
from .openf1_loader import OPENF1_FIRST_SEASON, PastRaceSamples
from .pit_lane_table import estimated_pit_loss as _estimate_from_table
from .pit_lane_table import pit_lane_entry
from .regulation_era import PIT_LOSS_PRE_ERA_MIN_SEASON, era_start
from .weekend import (
    DRY_COMPOUNDS,
    Compound,
    HistoricalDegradation,
    RaceWeekend,
)

try:
    from fastf1.exceptions import FastF1CriticalError
except Exception:  # pragma: no cover - defensive if FastF1 isn't installed
    class FastF1CriticalError(Exception):  # type: ignore[no-redef]
        """Stand-in used only when FastF1 isn't importable; never in production."""


FastF1PastSamplesLoader = Callable[..., PastRaceSamples]
OpenF1PastSamplesLoader = Callable[..., PastRaceSamples]


def load_weekend(
    season: int,
    event: str,
    *,
    fastf1_cache_dir: str | Path = ".cache/fastf1",
    openf1_cache_dir: str | Path = ".cache/openf1",
    openf1_client: openf1_loader._OpenF1Client | None = None,
    fuel_effect_s_per_lap: float = 0.03,
    history_min_stint_length: int = 4,
    fastf1_load_past_race_samples: FastF1PastSamplesLoader | None = None,
    openf1_load_past_race_samples: OpenF1PastSamplesLoader | None = None,
) -> RaceWeekend:
    """Load one race weekend through the right source, with cross-source history.

    ``season`` picks the target-weekend source: OpenF1 for 2023+,
    FastF1 for 2022 and earlier. ``event`` has the same meaning as in
    each loader (an official event name or location string).

    The two ``*_load_past_race_samples`` hooks let tests inject fake
    per-source past-race fetchers so the cross-source combination can be
    exercised without hitting disk or the network. In production both
    default to the real :func:`fastf1_loader.load_past_race_samples` and
    :func:`openf1_loader.load_past_race_samples`.
    """
    if openf1_client is None and season >= OPENF1_FIRST_SEASON:
        openf1_client = OpenF1Client(cache_dir=Path(openf1_cache_dir))

    if season >= OPENF1_FIRST_SEASON:
        def _measure(circuit: str, race_season: int) -> tuple[
            float,
            tuple[int, ...],
            bool,
            dict[Compound, HistoricalDegradation],
            tuple[str, ...],
        ]:
            return measure_pit_loss_and_history(
                circuit=circuit,
                race_season=race_season,
                openf1_client=openf1_client,
                fastf1_cache_dir=fastf1_cache_dir,
                fuel_effect_s_per_lap=fuel_effect_s_per_lap,
                history_min_stint_length=history_min_stint_length,
                fastf1_load_past_race_samples=fastf1_load_past_race_samples,
                openf1_load_past_race_samples=openf1_load_past_race_samples,
                return_warnings=True,
            )

        return openf1_loader.load_weekend(
            season,
            event,
            client=openf1_client,
            cache_dir=openf1_cache_dir,
            fuel_effect_s_per_lap=fuel_effect_s_per_lap,
            history_min_stint_length=history_min_stint_length,
            measure_history=_measure,
        )

    # 2022 and earlier: the FastF1 loader's own fallback chain already
    # handles the ADR-0004 pre-era pit-loss exception and the ticket-07
    # pit-lane-table estimate. Nothing cross-source to add because
    # 2022's history budget never reaches 2023+.
    return fastf1_loader.load_weekend(
        season,
        event,
        cache_dir=fastf1_cache_dir,
        fuel_effect_s_per_lap=fuel_effect_s_per_lap,
        history_min_stint_length=history_min_stint_length,
    )


def list_season(
    season: int,
    *,
    fastf1_cache_dir: str | Path = ".cache/fastf1",
    openf1_cache_dir: str | Path = ".cache/openf1",
    openf1_client: openf1_loader._OpenF1Client | None = None,
) -> list[RaceSpec]:
    """Every race weekend of ``season``, in round order, sprints marked.

    Dispatches to :func:`openf1_loader.list_season` for 2023+ and
    :func:`fastf1_loader.list_season` otherwise. The returned
    ``RaceSpec`` shape is identical whichever source answered.
    """
    if season >= OPENF1_FIRST_SEASON:
        return openf1_loader.list_season(
            season, client=openf1_client, cache_dir=openf1_cache_dir
        )
    return fastf1_loader.list_season(season, cache_dir=fastf1_cache_dir)


def measure_pit_loss_and_history(
    *,
    circuit: str,
    race_season: int,
    openf1_client: openf1_loader._OpenF1Client | None,
    fastf1_cache_dir: str | Path = ".cache/fastf1",
    fuel_effect_s_per_lap: float = 0.03,
    history_min_stint_length: int = 4,
    fastf1_load_past_race_samples: FastF1PastSamplesLoader | None = None,
    openf1_load_past_race_samples: OpenF1PastSamplesLoader | None = None,
    return_warnings: bool = False,
):
    """Cross-source Pit Loss and Historical Degradation for one race.

    Walks the same-era past seasons ``[era_start(race_season), race_season)``
    at the circuit (plus every alias in :func:`location_group`), picks
    the source per past season (OpenF1 for ``>= OPENF1_FIRST_SEASON``,
    FastF1 otherwise), collects :class:`PastRaceSamples` from each, then
    applies the same weighting both single-source helpers already use:

    - Pit Loss weight: ``0.5 ** (race_season - season - 1)``, weighted
      mean of each past race's per-stop median loss.
    - Historical Degradation weight: lap-count × season-weight weighted
      mean of per-Stint rates per Compound.

    Fallbacks when the same-era scan returns no Pit Loss sample (ADR-0004
    Pit Loss exception, then ticket 07):

    1. **Pre-era FastF1 seasons** ``[PIT_LOSS_PRE_ERA_MIN_SEASON,
       era_start(race_season))`` for the circuit (ADR-0004 exception —
       2022's "no same-era history" case). Mid-October-2026 the archive
       returns 401 for 2018–2020, so this pass finds nothing for the
       five circuits listed in ADR-0006's "Pre-era Pit Loss hole".
    2. **Pit-lane-table estimate** (ticket 07, ticket 25), flagged as
       ``estimated_pit_loss=True`` so the Backtest Result records it.
    3. **Raise** ``ValueError`` so the Backtest records a
       ``DATA_UNAVAILABLE`` Excluded Race. The error message says which
       circuit and season range came up empty.

    Historical Degradation stays measured-only — the pre-era and
    pit-lane-table paths are Pit Loss only (ADR-0004's main rule).

    When ``return_warnings`` is ``True`` the return value is extended by a
    ``tuple[str, ...]`` of data-quality notes (ticket 28): one entry per
    past season/alias whose fetch returned no usable samples. Fetch
    failures (FastF1 rate limit, :class:`OpenF1FetchError`) are **not**
    recorded here — they propagate so the Backtest can retry or exclude
    the race.
    """
    if fastf1_load_past_race_samples is None:
        fastf1_load_past_race_samples = fastf1_loader.load_past_race_samples
    if openf1_load_past_race_samples is None:
        openf1_load_past_race_samples = openf1_loader.load_past_race_samples

    circuit_aliases = sorted(location_group(circuit))
    era_min_season = era_start(race_season)

    pit_weighted: list[tuple[float, float, int]] = []
    hist_samples: dict[Compound, list[tuple[float, int, float, int]]] = {
        c: [] for c in DRY_COMPOUNDS
    }
    warnings: list[str] = []

    for season in range(era_min_season, race_season):
        pit_contributed = False
        hist_contributed = False
        counted: set[str] = set()
        notes: list[str] = []
        for alias in circuit_aliases:
            samples = _fetch_past_samples(
                season=season,
                event=alias,
                openf1_client=openf1_client,
                fastf1_cache_dir=fastf1_cache_dir,
                fuel_effect_s_per_lap=fuel_effect_s_per_lap,
                history_min_stint_length=history_min_stint_length,
                fastf1_load_past_race_samples=fastf1_load_past_race_samples,
                openf1_load_past_race_samples=openf1_load_past_race_samples,
            )
            if not samples.pit_losses and not samples.stint_rates:
                if samples.note:
                    notes.append(samples.note)
                continue
            # Ticket 38: two alias names can reach the same race; count it
            # once, by the source's own race identity.
            if samples.race_id in counted:
                continue
            if samples.race_id is not None:
                counted.add(samples.race_id)
            weight = 0.5 ** (race_season - season - 1)
            losses = sorted(samples.pit_losses)
            if losses:
                pit_weighted.append(
                    (losses[len(losses) // 2], weight, season)
                )
                pit_contributed = True
            for compound, rate, lap_count in samples.stint_rates:
                hist_samples[compound].append(
                    (rate, lap_count, weight, season)
                )
                hist_contributed = True
        if not pit_contributed and not hist_contributed:
            # Ticket 40: say why when the source knows (e.g. FastF1's archive
            # had no data for the race); the generic text is only true when
            # the fetch really did succeed.
            reason = "; ".join(notes) or "fetch succeeded with no rows or no clean laps"
            warnings.append(
                f"{season} {'/'.join(circuit_aliases)}: no usable past-race "
                f"samples ({reason})"
            )
        elif not pit_contributed:
            warnings.append(
                f"{season} {'/'.join(circuit_aliases)}: no Pit Loss sample "
                f"(stint data available but /v1/pit returned no rows)"
            )

    historical_degradation = _aggregate_history(hist_samples)

    def _ret(pit_loss: float, pit_seasons: tuple[int, ...], estimated: bool):
        if return_warnings:
            return pit_loss, pit_seasons, estimated, historical_degradation, tuple(warnings)
        return pit_loss, pit_seasons, estimated, historical_degradation

    if pit_weighted:
        total_weight = sum(w for _, w, _ in pit_weighted)
        pit_loss = sum(m * w for m, w, _ in pit_weighted) / total_weight
        pit_loss_seasons = tuple(sorted({s for _, _, s in pit_weighted}))
        return _ret(pit_loss, pit_loss_seasons, False)

    # Fallback 1: pre-era FastF1 (ADR-0004 Pit Loss exception). Only fires
    # when the same-era pass found no measurable sample — mostly 2022
    # first-season-of-era circuits.
    pre_era_pit = _measure_pre_era_pit_loss(
        circuit_aliases=circuit_aliases,
        race_season=race_season,
        era_min_season=era_min_season,
        fastf1_cache_dir=fastf1_cache_dir,
        fuel_effect_s_per_lap=fuel_effect_s_per_lap,
        history_min_stint_length=history_min_stint_length,
        fastf1_load_past_race_samples=fastf1_load_past_race_samples,
    )
    if pre_era_pit is not None:
        pit_loss, pit_loss_seasons = pre_era_pit
        return _ret(pit_loss, pit_loss_seasons, False)

    # Fallback 2: pit-lane-table estimate (ticket 07, ticket 25).
    entry = pit_lane_entry(circuit)
    if entry is not None:
        return _ret(_estimate_from_table(entry), (), True)

    raise ValueError(
        f"no previous seasons' races at {circuit!r} were available to measure "
        f"Pit Loss from (looked at {era_min_season}..{race_season - 1} and "
        f"the pre-era FastF1 range {PIT_LOSS_PRE_ERA_MIN_SEASON}.."
        f"{era_min_season - 1}), and {circuit!r} has no entry in the pit lane "
        f"table (ticket 07)"
    )


def _fetch_past_samples(
    *,
    season: int,
    event: str,
    openf1_client,
    fastf1_cache_dir: str | Path,
    fuel_effect_s_per_lap: float,
    history_min_stint_length: int,
    fastf1_load_past_race_samples: FastF1PastSamplesLoader,
    openf1_load_past_race_samples: OpenF1PastSamplesLoader,
) -> PastRaceSamples:
    """Dispatch one past season to its source. Fetch failures propagate so
    the Backtest can wait and retry (FastF1 rate limit, ticket 17) or
    exclude the race as ``FETCH_FAILED`` (OpenF1 outage).

    Ticket 28: this used to wrap every call in ``except Exception`` to
    keep "one bad past race must not sink the whole scan", but
    :class:`fastf1.exceptions.RateLimitExceededError` is a ``RuntimeError``
    and :class:`OpenF1FetchError` is also an ``Exception`` — both got
    silently turned into "this past season has no history", undoing
    ticket 17's wait-and-retry for every past race loaded through the
    router. The two loaders already distinguish fetch failures from
    genuine missing data (both re-raise :class:`FastF1CriticalError` and
    neither catches :class:`OpenF1FetchError`), so trust them: let the
    error through, and only catch genuine "no match / no clean laps"
    cases that the loader turns into an empty :class:`PastRaceSamples`.
    """
    if season >= OPENF1_FIRST_SEASON:
        # OpenF1 branch: load_past_race_samples returns empty samples when
        # the meeting isn't found or the race session is missing (a 2022
        # alias passed by mistake would land here); OpenF1FetchError and
        # unexpected RuntimeErrors propagate.
        try:
            return openf1_load_past_race_samples(
                openf1_client,
                season,
                event,
                fuel_effect_s_per_lap=fuel_effect_s_per_lap,
                history_min_stint_length=history_min_stint_length,
            )
        except NotDownloadedError as error:
            # Ticket 36: offline, a past race that was never downloaded is a
            # Data Quality Warning saying so, as FastF1's past races are.
            return PastRaceSamples(pit_losses=(), stint_rates=(), note=str(error))
    # FastF1 branch: load_past_race_samples re-raises FastF1CriticalError
    # (rate limit) and returns empty samples for every other load failure.
    return fastf1_load_past_race_samples(
        season,
        event,
        cache_dir=fastf1_cache_dir,
        fuel_effect_s_per_lap=fuel_effect_s_per_lap,
        history_min_stint_length=history_min_stint_length,
    )


def _aggregate_history(
    hist_samples: dict[Compound, list[tuple[float, int, float, int]]],
) -> dict[Compound, HistoricalDegradation]:
    """Lap-count × season-weight weighted mean per Compound; same formula
    the single-source loaders use."""
    out: dict[Compound, HistoricalDegradation] = {}
    for compound, samples in hist_samples.items():
        if not samples:
            continue
        weights = [n * w for _, n, w, _ in samples]
        total = sum(weights)
        rate = sum(r * x for (r, _, _, _), x in zip(samples, weights)) / total
        seasons_used = tuple(sorted({s for _, _, _, s in samples}))
        out[compound] = HistoricalDegradation(
            rate=rate,
            seasons=seasons_used,
            stint_count=len(samples),
        )
    return out


def _measure_pre_era_pit_loss(
    *,
    circuit_aliases: list[str],
    race_season: int,
    era_min_season: int,
    fastf1_cache_dir: str | Path,
    fuel_effect_s_per_lap: float,
    history_min_stint_length: int,
    fastf1_load_past_race_samples: FastF1PastSamplesLoader,
) -> tuple[float, tuple[int, ...]] | None:
    """ADR-0004's Pit Loss pre-era exception, FastF1 only.

    Only called when the same-era scan found nothing. Scans
    ``[PIT_LOSS_PRE_ERA_MIN_SEASON, era_min_season)`` through FastF1 at
    the circuit, applying the same recent-seasons weight and median-
    across-the-race formula. ``None`` when the pre-era pass also comes
    back empty.
    """
    if PIT_LOSS_PRE_ERA_MIN_SEASON >= era_min_season:
        return None
    pit_weighted: list[tuple[float, float, int]] = []
    for season in range(PIT_LOSS_PRE_ERA_MIN_SEASON, era_min_season):
        counted: set[str] = set()
        for alias in circuit_aliases:
            # FastF1CriticalError propagates (rate limit → Backtest retry).
            # fastf1_loader.load_past_race_samples already returns empty
            # samples for a missing schedule row or a 401-refused load, so
            # there is nothing else to catch here (ticket 28).
            samples = fastf1_load_past_race_samples(
                season,
                alias,
                cache_dir=fastf1_cache_dir,
                fuel_effect_s_per_lap=fuel_effect_s_per_lap,
                history_min_stint_length=history_min_stint_length,
            )
            losses = sorted(samples.pit_losses)
            if not losses or samples.race_id in counted:
                continue
            if samples.race_id is not None:
                counted.add(samples.race_id)
            weight = 0.5 ** (race_season - season - 1)
            pit_weighted.append((losses[len(losses) // 2], weight, season))
    if not pit_weighted:
        return None
    total_weight = sum(w for _, w, _ in pit_weighted)
    pit_loss = sum(m * w for m, w, _ in pit_weighted) / total_weight
    pit_loss_seasons = tuple(sorted({s for _, _, s in pit_weighted}))
    return pit_loss, pit_loss_seasons
