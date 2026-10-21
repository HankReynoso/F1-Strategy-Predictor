"""Save a Backtest Result to disk and read it back identical.

A full Backtest run writes a JSON data file plus a Markdown summary, both
named `<date>_<label>.<ext>` under a results folder. The JSON file carries
every per-race record, every Excluded Race, and the run's metadata (label,
run time, code commit and uncommitted-changes flag, seasons in scope, and
the full `Settings`). Aggregates on `BacktestResult` are derivable from
the per-race records plus `Settings`, so they're not stored; a reload
recomputes them with the same code path `run_backtest` used, which also
means an aggregation change benefits an old file without migrating it.

See `docs/adr/0005-saved-backtest-result-format.md` for why JSON, why
scores-only, and the versioning rule.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path

from .backtest import (
    BacktestResult,
    ExcludedRace,
    ExclusionReason,
    RaceResult,
    _group_totals,
    _race_averaged,
    _sum_degradation_sources,
    _totals,
    format_backtest,
)
from .degradation import DegradationSource
from .scorer import RaceSummary
from .settings import Settings

FORMAT_VERSION = 1


@dataclass(frozen=True)
class RunMetadata:
    """Everything that identifies which run produced a Backtest Result.

    `code_commit` + `uncommitted_changes` traces a Result back to the code
    that made it; `seasons_in_scope` lets the compare command warn when
    two runs don't cover the same races; `settings` is carried whole so a
    tuned run reads back with the same thresholds and the same
    tuning/held-out partition.
    """

    label: str
    run_at: str
    code_commit: str
    uncommitted_changes: bool
    seasons_in_scope: tuple[int, ...]
    settings: Settings


@dataclass(frozen=True)
class SavedPaths:
    data: Path
    summary: Path


def save_backtest_result(
    result: BacktestResult,
    directory: Path | str,
    *,
    metadata: RunMetadata,
) -> SavedPaths:
    """Write the data and summary files under `directory` and return both paths.

    Filenames are `<date>_<label>.json` and `<date>_<label>.md`, with the
    date taken from `metadata.run_at` (YYYY-MM-DD) and the label slugified
    so a label with spaces or slashes can't smuggle a path separator in.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{_date_from(metadata.run_at)}_{_slug(metadata.label)}"
    data_path = directory / f"{stem}.json"
    summary_path = directory / f"{stem}.md"

    payload = _encode(result, metadata)
    data_path.write_text(json.dumps(payload, indent=2) + "\n")
    summary_path.write_text(_summary_text(result, metadata))
    return SavedPaths(data=data_path, summary=summary_path)


def load_backtest_result(path: Path | str) -> tuple[BacktestResult, RunMetadata]:
    """Read a saved Backtest Result's data file; recompute aggregates.

    An unknown `format_version` is refused with a clear error rather than
    guessed at. Unknown keys at version 1 are ignored, so an older file
    with fields a later version added still loads.
    """
    path = Path(path)
    payload = json.loads(path.read_text())
    version = payload.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported format_version {version!r} in {path} "
            f"(this build reads version {FORMAT_VERSION})"
        )
    metadata = _decode_metadata(payload["metadata"])
    races = tuple(_decode_race(entry) for entry in payload["races"])
    excluded = tuple(_decode_excluded(entry) for entry in payload["excluded"])
    return _rebuild_result(races, excluded, metadata.settings), metadata


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def _encode(result: BacktestResult, metadata: RunMetadata) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "metadata": {
            "label": metadata.label,
            "run_at": metadata.run_at,
            "code_commit": metadata.code_commit,
            "uncommitted_changes": metadata.uncommitted_changes,
            "seasons_in_scope": list(metadata.seasons_in_scope),
            "settings": _encode_settings(metadata.settings),
        },
        "races": [_encode_race(r) for r in result.races],
        "excluded": [_encode_excluded(e) for e in result.excluded],
    }


def _encode_settings(settings: Settings) -> dict:
    data = asdict(settings)
    # tuple -> list for JSON; held_out_season may be None, keep as-is.
    data["tuning_seasons"] = list(settings.tuning_seasons)
    return data


def _encode_race(race: RaceResult) -> dict:
    return {
        "season": race.season,
        "event": race.event,
        "circuit": race.circuit,
        "is_sprint_weekend": race.is_sprint_weekend,
        "neutralised_race": race.neutralised_race,
        "pit_loss": race.pit_loss,
        "pit_loss_seasons": list(race.pit_loss_seasons),
        "estimated_pit_loss": race.estimated_pit_loss,
        "actual_stops": race.actual_stops,
        "summary": {
            "scoreable_drivers": race.summary.scoreable_drivers,
            "top_1_credit": race.summary.top_1_credit,
            "top_3_credit": race.summary.top_3_credit,
            "stop_window_hits": race.summary.stop_window_hits,
        },
        # DegradationSource -> its .value string; see ADR-0005.
        "degradation_sources": {
            source.value: count for source, count in race.degradation_sources.items()
        },
    }


def _encode_excluded(excluded: ExcludedRace) -> dict:
    return {
        "season": excluded.season,
        "event": excluded.event,
        "reason": excluded.reason.value,
        "detail": excluded.detail,
    }


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def _decode_metadata(data: dict) -> RunMetadata:
    return RunMetadata(
        label=data["label"],
        run_at=data["run_at"],
        code_commit=data["code_commit"],
        uncommitted_changes=bool(data["uncommitted_changes"]),
        seasons_in_scope=tuple(data["seasons_in_scope"]),
        settings=_decode_settings(data["settings"]),
    )


def _decode_settings(data: dict) -> Settings:
    # Only pass keys Settings knows; ignore extras so an older file still
    # loads when a new Settings field has a default.
    known = {f.name for f in fields(Settings)}
    kwargs = {k: v for k, v in data.items() if k in known}
    if "tuning_seasons" in kwargs:
        kwargs["tuning_seasons"] = tuple(kwargs["tuning_seasons"])
    return Settings(**kwargs)


_REASON_BY_VALUE = {r.value: r for r in ExclusionReason}
_SOURCE_BY_VALUE = {s.value: s for s in DegradationSource}


def _decode_race(data: dict) -> RaceResult:
    summary = data["summary"]
    return RaceResult(
        season=data["season"],
        event=data["event"],
        circuit=data["circuit"],
        is_sprint_weekend=bool(data["is_sprint_weekend"]),
        neutralised_race=bool(data["neutralised_race"]),
        summary=RaceSummary(
            scoreable_drivers=summary["scoreable_drivers"],
            top_1_credit=summary["top_1_credit"],
            top_3_credit=summary["top_3_credit"],
            stop_window_hits=summary["stop_window_hits"],
        ),
        actual_stops=data["actual_stops"],
        pit_loss=float(data.get("pit_loss", 0.0)),
        pit_loss_seasons=tuple(data.get("pit_loss_seasons", ())),
        degradation_sources={
            _SOURCE_BY_VALUE[key]: count
            for key, count in data["degradation_sources"].items()
        },
        estimated_pit_loss=bool(data.get("estimated_pit_loss", False)),
    )


def _decode_excluded(data: dict) -> ExcludedRace:
    return ExcludedRace(
        season=data["season"],
        event=data["event"],
        reason=_REASON_BY_VALUE[data["reason"]],
        detail=data["detail"],
    )


# ---------------------------------------------------------------------------
# Rebuilding aggregates
# ---------------------------------------------------------------------------


def _rebuild_result(
    races: tuple[RaceResult, ...],
    excluded: tuple[ExcludedRace, ...],
    settings: Settings,
) -> BacktestResult:
    return BacktestResult(
        races=races,
        excluded=excluded,
        green_headline=_totals(r for r in races if not r.neutralised_race),
        neutralised=_totals(r for r in races if r.neutralised_race),
        all_races=_totals(races),
        green_headline_averaged=_race_averaged(
            r for r in races if not r.neutralised_race
        ),
        neutralised_averaged=_race_averaged(
            r for r in races if r.neutralised_race
        ),
        all_races_averaged=_race_averaged(races),
        by_season=_group_totals(races, key=lambda r: r.season),
        by_circuit=_group_totals(races, key=lambda r: r.circuit),
        by_sprint_weekend=_group_totals(races, key=lambda r: r.is_sprint_weekend),
        tuning=_totals(r for r in races if r.season in settings.tuning_seasons),
        held_out=_totals(
            r for r in races if r.season == settings.held_out_season
        ),
        tuning_seasons=tuple(settings.tuning_seasons),
        held_out_season=settings.held_out_season,
        degradation_source_counts=_sum_degradation_sources(races),
    )


# ---------------------------------------------------------------------------
# Readable summary and metadata helpers
# ---------------------------------------------------------------------------


def _summary_text(result: BacktestResult, metadata: RunMetadata) -> str:
    header = [
        f"# Backtest Result — {metadata.label}",
        "",
        f"- Run at: {metadata.run_at}",
        f"- Code commit: {metadata.code_commit}"
        + (" (uncommitted changes)" if metadata.uncommitted_changes else ""),
        f"- Seasons in scope: "
        + ", ".join(str(s) for s in metadata.seasons_in_scope),
        "",
        "```",
    ]
    footer = ["```", ""]
    return "\n".join(header + [format_backtest(result)] + footer)


def _date_from(run_at: str) -> str:
    # run_at is ISO 8601; the date prefix is YYYY-MM-DD at offset-0.
    try:
        return datetime.fromisoformat(run_at).date().isoformat()
    except ValueError:
        return run_at[:10]


_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(label: str) -> str:
    """Turn a free-form label into a safe filename component.

    Any run of characters that isn't a letter, digit, dot, underscore or
    dash becomes a single dash. Collapses leading and trailing dashes so
    a label like `"circuit tendency/v2"` reads as `circuit-tendency-v2`.
    """
    cleaned = _SLUG_RE.sub("-", label).strip("-")
    return cleaned or "unlabeled"


def detect_code_version(repo: Path | str = ".") -> tuple[str, bool]:
    """Return `(commit_sha, uncommitted_changes)` from `git` in `repo`.

    Falls back to `("unknown", True)` if git isn't available or `repo`
    isn't a repository — the user can still save a result, with the
    uncertainty recorded.
    """
    repo = Path(repo)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ("unknown", True)
    return (commit, bool(status.strip()))


def default_run_at() -> str:
    """Current time in ISO 8601 UTC, suitable for `RunMetadata.run_at`."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
