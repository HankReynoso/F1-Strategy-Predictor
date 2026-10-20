# 07: FastF1 weekend loader + Pit Loss from history

**What to build:** Load a real race weekend (season + event name) from FastF1, using its on-disk cache, into the race weekend description: practice, sprint and qualifying laps with Tyre Set identity, Compound, tyre age, new/used and pit flags; each driver's team; race length; the race's actual Stints and Safety Car/VSC periods. Pit Loss for the circuit is measured from previous seasons' races there (2022+, recent seasons weighted more), never from the race being predicted. This is the only module that knows about FastF1.

**Blocked by:** 01 (Tracer bullet)

**Status:** done

- [x] A chosen 2024 race weekend loads into the race weekend description
- [x] All race starters are present with their teams
- [x] Practice laps carry Tyre Set identity, Compound, tyre age and new/used
- [x] Race length matches the official distance in laps
- [x] The race's actual Stints and neutralisation periods are populated but kept separate from pre-race information
- [x] Sprint sessions are included on sprint weekends
- [x] Pit Loss is computed from previous seasons' races at the circuit and excludes the race itself
- [x] Repeat loads come from the local cache
- [x] A small number of tests check one cached real race; they can be marked as slower tests

## Comments

**From ticket 01 (2026-10-19).** - Tyre Set identity (`Lap.tyre_set`): as far as I know, FastF1 doesn't expose a Tyre Set ID that persists across sessions. Its laps give stint number, Compound, tyre life and fresh/used. Verify this first. If it holds, set identity has to be reconstructed (e.g. matching a used set's tyre life to an earlier set's last lap), which affects how far ticket 04 can trust Remaining Sets.
- `PreRaceInfo.pit_loss` is a single number in seconds. `PreRaceInfo.teams` should hold only drivers who started the race, since `predict()` produces a prediction for every key.
- The Dry Race guard reads `RaceOutcome.stints` Compounds, so Stints must carry the actual Compound (including Intermediate and Wet) for the refusal to work.

## Implementation notes

**Implemented (2026-10-20).** Loader lives at `src/f1_strategy/fastf1_loader.py` with one public call, `load_weekend(season, event, cache_dir=".cache/fastf1", pit_loss_min_season=2022) -> RaceWeekend`. Tests in `tests/test_fastf1_weekend_loader.py`, marked `@pytest.mark.slow` (new marker declared in `pyproject.toml`). Reference weekend: Italian Grand Prix 2024 (Monza, conventional, dry).

- **What was built.**
  - Session discovery: iterate the event's `Session1..Session4` names, map FastF1's long names ("Practice 1", "Sprint Qualifying", …) to short identifiers (FP1, FP2, FP3, SQ, SS, S, Q) and skip the race session. Sprint weekends therefore pick up Sprint Qualifying and the Sprint race automatically.
  - Teams: taken from the race `results` where `GridPosition > 0`. This matches the ticket-01 constraint that `PreRaceInfo.teams` holds only starters, so every `predict()` key is a real race entry.
  - Race outcome: Stints are grouped per driver by FastF1's `Stint` column, with the Compound coming from the first lap of each stint; neutralisation periods are reconstructed from the per-lap `TrackStatus` codes (4 → SC, 6/7 → VSC) and emitted as contiguous SC/VSC spans.
  - Pit Loss: per past race, gather `(pit_in_lap_time − driver_clean_median) + (pit_out_lap_time − driver_clean_median)` across every pit stop whose in and out laps were under green (`TrackStatus == "1"`), bounded 10–60 s to drop clearly broken rows (DNFs on the pit-in lap, extended red-flag laps). Each race contributes its median; races are then combined as a season-weighted mean with weight `0.5 ** (race_season − season − 1)` so more recent seasons count more. Current race is excluded by construction: the search range is `[pit_loss_min_season, race_season)`.
  - Caching: `fastf1.Cache.enable_cache` is called at every entry point. Repeat loads hit the on-disk cache; the slow-tests marker guards against treating these as fast unit tests.

- **Decisions and rejected alternatives.**
  - *Tyre Set identity.* Confirmed the ticket-01 note: FastF1 exposes `Stint`, `Compound`, `TyreLife` and `FreshTyre` but no persistent set id. The loader produces a per-stint identity `"{driver}-{session}-stint{N}-{compound}"`. Alternative: reconstruct cross-session identity by matching used sets' starting `TyreLife` against earlier sets' ending life. Rejected for this ticket because (a) nothing downstream yet consumes cross-session identity and (b) ticket 04 (Remaining Sets) is the right place to decide the matching rules, now that the FastF1 fields have been checked.
  - *Pit Loss formula.* Chose the "pit-in extra + pit-out extra over driver's clean median" because it needs only lap-level data and generalises across circuits. Alternatives: stationary pit-stop time (FastF1 exposes no reliable field for this), lap-time delta to a nominated reference driver (sensitive to that driver's own race pace). Clipped losses to 10–60 s to drop obvious outliers; wider bounds admit red-flag laps and shorter would clip real stops at longer pit lanes.
  - *Season weighting.* Half-life of one year on prior seasons' per-race medians. Alternative: uniform weighting. Rejected to honour the spec's "recent seasons weighted more"; the exact decay can be tuned later.
  - *Session names.* Used FastF1's short identifiers (FP1, FP2, FP3, SQ, SS, S, Q) rather than fuller names so `Session.name` strings match the ones hand-built tests already use in `tests/test_pre_race_prediction.py`.
  - *Starters filter.* `GridPosition > 0` only. This drops drivers who were in the entry list but did not take the start (reserve drivers, withdrawn entries); the spec is clear that `teams` is "every driver who starts the race".
  - *Lap filtering.* Rows with no `LapTime`, no `TyreLife` or an unrecognised Compound are dropped from `Session.laps`. The downstream run classifier (ticket 03) still has to decide what counts as a Long Run; this is strictly cleanup of FastF1 artefacts.

- **Deviations from the spec/ticket.** None material. The spec says Pit Loss "should draw on recent previous seasons (2022+, current regulations)". In this environment the FastF1 live-timing endpoint returns 403 for 2022-season data and the FastF1 fallback mirror (`livetiming-mirror.fastf1.dev`) is not on the proxy allowlist, so 2022 races are silently skipped and only 2023+ contributes for a 2024 race. For Monza 2024 this means Pit Loss is drawn from the single 2023 Monza race; the loader will still work when 2022 data becomes available without any code change (`pit_loss_min_season` already defaults to 2022). This is flagged as a known limitation below rather than worked around.

- **Known limitations and follow-ups.**
  - *2022 FastF1 data unavailable in this environment.* See the deviation above. If broader historical Pit Loss coverage becomes important before 2022 data unblocks, options are: swap in an Ergast or local-mirror backend; or let `pit_loss_min_season` fall back to a hand-tabled per-circuit figure. New follow-up ticket not filed yet because the fix is environmental, not code.
  - *Cross-session Tyre Set identity.* Not reconstructed; see the rejected alternative above. Ticket 04 should settle how far Remaining Sets can trust practice/qualifying history when a used set reappears.
  - *Pit stops under SC/VSC.* Dropped from the Pit Loss sample because clean-reference lap times are only taken from green laps. This loses the stops that are the easiest for teams to take, but keeping them would bias Pit Loss downward (SC pit stops lose much less time); the simulator in later tickets models SC pits separately if needed.
  - *FastF1 deprecation warnings.* Loading sessions emits ~300 pandas/NumPy `DeprecationWarning`s. They originate in FastF1 itself and will clear when FastF1 updates; not silenced here.

- **Review feedback for the user.**
  - 2022 data is blocked in this sandbox (livetiming.formula1.com → 403 for 2022; the FastF1 fallback mirror is proxy-denied). Monza 2024's Pit Loss is therefore drawn only from Monza 2023. The acceptance criterion still holds — Pit Loss excludes the race being predicted — but the sample size for a 2024 race is one past race, which is thinner than the spec's "weighted across 2022+". The loader is ready to use more years as soon as the environment can reach them.
  - Branch rebased onto latest `main` before pushing to accommodate ticket 05 landing in parallel.
