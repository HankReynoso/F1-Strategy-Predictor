# 03: Pit Loss from before the era for first-season races

**What to build:** When a circuit has no same-era race before the one being predicted, Pit Loss falls back to earlier seasons at the circuit (2018–2021, recent seasons counting more), per the ADR-0004 exception. Circuits with same-era history keep today's Pit Loss. 2022 races stop failing for lack of Pit Loss history. See `../spec.md`.

**Blocked by:** 01 (Regulation Era as one source of truth)

**Status:** done

- [x] A 2022 race at a circuit raced in 2018–2021 gets a Pit Loss measured from those seasons (slow test)
- [x] A race with same-era history uses only same-era seasons for Pit Loss, as today
- [x] Singapore 2024's Pit Loss and results are unchanged
- [x] Which seasons a Pit Loss came from is visible in the single-race report

## Implementation notes

**What was built (2026-10-21), test-first.**

- `src/f1_strategy/regulation_era.py` — new constant
  `PIT_LOSS_PRE_ERA_MIN_SEASON = 2018`, the single source of truth for
  the earliest season Pit Loss may fall back to. 2018 is where FastF1's
  detailed-timing coverage begins; before that neither `_pit_losses_in`
  nor its reference lap-time source is reliable.
- `src/f1_strategy/weekend.py` — `PreRaceInfo` gains
  `pit_loss_seasons: tuple[int, ...] = ()`, the past seasons that
  contributed to this race's Pit Loss (oldest first). Default empty so
  hand-built test weekends keep working without edits.
- `src/f1_strategy/fastf1_loader.py` —
  - `load_weekend`'s `pit_loss_min_season` keyword now defaults to
    `None` meaning "apply ADR-0004's Pit Loss exception": try same-era
    seasons first, fall back to `[PIT_LOSS_PRE_ERA_MIN_SEASON,
    era_start)` only when the circuit has no same-era race before the
    one being predicted. An explicit integer still pins the lower
    bound, used by the back-compat `_pit_loss_at_circuit` shim and
    kept available for future tests.
  - New private orchestrator `_measure_pit_loss_and_history` makes the
    two-step attempt explicit, so the pre-era fallback is used only
    when the same-era pass finds no Pit Loss sample at all. Historical
    Degradation stays on the same-era range in every branch (ADR-0004
    main rule; the exception is Pit Loss only).
  - `_past_races_at_circuit` now returns the seasons it drew on and
    may return `pit_loss=None` under `pit_loss_required=False`, so the
    orchestrator can distinguish "no same-era data" from "same-era
    data exists but is unusable". The `_pit_losses_in` logic is
    unchanged.
- `src/f1_strategy/report.py` — `format_header` adds a one-line
  provenance note only when any contributing season is pre-era:
  `"Pit Loss from pre-era seasons 2019, 2020, 2021 (ADR-0004
  exception)"`. Same-era-only races stay byte-identical to today's
  output, so Singapore 2024 and Monza 2024 are unchanged.

**Decisions and alternatives rejected.**

- *Make the fallback a second attempt, not a widened search range.* An
  alternative was to widen the primary search range to `[2018,
  race_season)` whenever `pit_loss_min_season` is None, letting the
  season-decay weighting choose the mix. Rejected: that would let
  pre-era pit lanes influence 2023+ races, which ADR-0004 forbids
  except as a last-resort fallback. The two-step attempt makes "no
  same-era data" the only trigger, and keeps Monza 2024 reading only
  2022 and 2023.
- *Visibility: pre-era note only, not every race's seasons.* Showing
  every race's full `pit_loss_seasons` list would have changed
  Singapore 2024 and Monza 2024's reports, failing the "results
  unchanged" criterion the ticket inherits from ticket 01. The point
  of the acceptance criterion is to flag when the ADR-0004 exception
  kicked in, so a line that only appears in that case is the right
  signal. The seasons are always on `PreRaceInfo.pit_loss_seasons`
  for the Backtest Result (ticket 04) to count, independent of the
  report.
- *Default `pit_loss_min_season=None`, not drop the keyword.* Keeping
  the keyword leaves a seam for a future test that wants to pin or
  widen the Pit Loss range (e.g. a slow test proving a non-first-
  season race doesn't accidentally pull in pre-era seasons). An
  explicit integer wins over the two-step default, matching how
  `history_min_season` already behaves. The old explicit default
  `2022` is gone: nothing in-tree set it.
- *2018 as the pre-era floor.* FastF1's detailed-timing coverage
  starts in 2018. 2017 and earlier would need a separate `v1`
  endpoint and offer no useful pit-stop lap-time rows. Pit lane
  changes between 2018 and 2021 are rare and ignored for now, per
  ADR-0004's "Rare pit lane changes are ignored for now."
- *Pre-era fallback doesn't touch Historical Degradation.* ADR-0004's
  exception is Pit Loss only; the fallback leaves
  `historical_degradation` as whatever the same-era pass produced
  (empty for a 2022 race, which is what ticket 01 asserts).

**Tests.**

- New slow tests in `tests/test_fastf1_weekend_loader.py`:
  - `test_a_2022_races_pit_loss_falls_back_to_pre_era_seasons`: loads
    Monza 2022 with default settings (no override), asserts
    `pit_loss_seasons` lie in 2018–2021 and the measured number is a
    sane 10–40 s.
  - `test_a_2024_races_pit_loss_uses_only_same_era_seasons`: Monza
    2024's `pit_loss_seasons` are all in `[era_start(2024), 2024)` —
    i.e. 2022 and 2023 only.
  - `test_list_season_2024_marks_sprint_weekends`: ticket 02's
    outstanding slow test for the loader's `list_season` call. 2024
    lists 24 race weekends, exactly six of which are sprint weekends
    (China, Miami, Austria, Austin, São Paulo, Qatar).
- Updated: `test_a_2022_race_gets_no_historical_degradation` drops
  the ticket 01-era `pit_loss_min_season=2018` override — the new
  default behaviour makes the load succeed on its own, satisfying
  the "remove that need" review item.

**Baselines, not changing.** `uv run f1-strategy 2024 "Singapore
Grand Prix"` and `… 2024 "Italian Grand Prix"` produce byte-identical
output before and after this ticket (both `diff` empty). The 2022
Italian Grand Prix now loads under default settings and reports Pit
Loss 27.2 s from pre-era seasons 2019, 2020, 2021 (2018's Monza
produced no usable pit-stop samples through FastF1's lap data).

**Deviations.** None. The spec's "Loader: Pit Loss before the era"
bullet and the ADR-0004 exception line up with what was built.

**Known limitations and follow-ups.**

- *Pre-era years that FastF1 can't load.* 2018–2021 availability
  depends on FastF1's live-timing mirror and whether a given season
  is cached. A circuit with no reachable pre-era race either (e.g.
  Jeddah 2022 if 2018–2021 Saudi Arabian GPs are unavailable) still
  raises `ValueError` at load time. The Backtest will see this as a
  `DATA_UNAVAILABLE` Excluded Race (ticket 02's behaviour), which
  is the intended "no history anywhere" shape until ticket 07 lands.
- *First-time circuits.* A circuit raced for the first time in the
  Regulation Era (e.g. Miami 2022) has no pre-era history to fall
  back on and still raises. Ticket 07 adds the estimated-Pit-Loss
  path and the hand-maintained pit-lane table.
- *Report line visibility.* The pre-era note appears only when the
  exception applies. If a future ticket wants the Pit Loss seasons
  shown unconditionally, the data is already on
  `PreRaceInfo.pit_loss_seasons`.
- *Backtest Result provenance.* `BacktestResult.races` doesn't yet
  carry Pit Loss seasons; ticket 04's breakdowns are the natural
  place to surface them (and the Degradation-source counts the spec
  calls out alongside).

**Review feedback for the user.** None — the behaviour change is
confined to races with no same-era history (2022 under current era);
2023–2025 Pit Loss is byte-identical. The Backtest Result (ticket 04)
can now count how often Pit Loss rested on the pre-era fallback,
which is one of the "Degradation source counts" the spec mentions.
