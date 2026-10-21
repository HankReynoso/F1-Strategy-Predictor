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

**Implemented (2026-10-20).** Loader lives at `src/f1_strategy/fastf1_loader.py` with one public call, `load_weekend(season, event, cache_dir=".cache/fastf1", pit_loss_min_season=2022) -> RaceWeekend`. Tests in `tests/test_fastf1_weekend_loader.py`, marked `@pytest.mark.slow` (new marker declared in `pyproject.toml`). Reference weekend: Italian Grand Prix 2024 (Monza, conventional, dry). The follow-up fixes added Saudi Arabian GP 2024 (Jeddah, Safety Car) and United States GP 2024 (Austin, sprint). The spec's Seam 2 bullet was updated from "one real race" to cover all three.

- **What was built.**
  - Session discovery: iterate the event's `Session1..Session4` names, map FastF1's long names ("Practice 1", "Sprint Qualifying", …) to short identifiers (FP1, FP2, FP3, SQ, SS, S, Q) and skip the race session. Sprint weekends therefore pick up Sprint Qualifying and the Sprint race automatically.
  - Teams: taken from the race `results` where `GridPosition > 0`. This matches the ticket-01 constraint that `PreRaceInfo.teams` holds only starters, so every `predict()` key is a real race entry.
  - Race outcome: Stints are grouped per driver by FastF1's `Stint` column, with the Compound coming from the first lap of each stint. Neutralisation periods come from the per-lap `TrackStatus` codes (4 → SC, 6/7 → VSC; SC wins if both appear), read from the **leader's lap only** (the first car to complete each lap number), and grouped into contiguous SC/VSC spans.
  - `Lap.neutralised` (pre-race sessions) is true only when the lap's codes include SC or VSC. Yellow (2) and red flag (5) laps are not neutralised.
  - Pit Loss: per past race, gather `(pit_in_lap_time − driver_clean_median) + (pit_out_lap_time − driver_clean_median)` across every pit stop whose in and out laps were under green (`TrackStatus == "1"`), bounded 10–60 s to drop clearly broken rows (DNFs on the pit-in lap, extended red-flag laps). Each race contributes its median; races are then combined as a season-weighted mean with weight `0.5 ** (race_season − season − 1)` so more recent seasons count more. Current race is excluded by construction: the search range is `[pit_loss_min_season, race_season)`.
  - Caching: `fastf1.Cache.enable_cache` is called at every entry point. Repeat loads hit the on-disk cache; the slow-tests marker guards against treating these as fast unit tests.

- **Decisions and rejected alternatives.**
  - *Tyre Set identity.* Confirmed the ticket-01 note: FastF1 exposes `Stint`, `Compound`, `TyreLife` and `FreshTyre` but no persistent set id. The loader produces a per-stint identity `"{driver}-{session}-stint{N}-{compound}"`. Alternative: reconstruct cross-session identity by matching used sets' starting `TyreLife` against earlier sets' ending life. Rejected for this ticket because (a) nothing downstream yet consumes cross-session identity and (b) ticket 04 (Remaining Sets) is the right place to decide the matching rules, now that the FastF1 fields have been checked.
  - *Pit Loss formula.* Chose the "pit-in extra + pit-out extra over driver's clean median" because it needs only lap-level data and generalises across circuits. Alternatives: stationary pit-stop time (FastF1 exposes no reliable field for this), lap-time delta to a nominated reference driver (sensitive to that driver's own race pace). Clipped losses to 10–60 s to drop obvious outliers; wider bounds admit red-flag laps and shorter would clip real stops at longer pit lanes.
  - *Season weighting.* Half-life of one year on prior seasons' per-race medians. Alternative: uniform weighting. Rejected to honour the spec's "recent seasons weighted more"; the exact decay can be tuned later.
  - *Session names.* Used FastF1's short identifiers (FP1, FP2, FP3, SQ, SS, S, Q) rather than fuller names so `Session.name` strings match the ones hand-built tests already use in `tests/test_pre_race_prediction.py`.
  - *Starters filter.* `GridPosition > 0` only. This drops drivers who were in the entry list but did not take the start (reserve drivers, withdrawn entries); the spec is clear that `teams` is "every driver who starts the race".
  - *Neutralisation laps are read from the leader.* Race control numbers laps by the leader. The first version marked a lap as SC if *any* car saw code 4 during it. In Jeddah 2024 that started the Safety Car on lap 6, because Stroll's unfinished lap 6 (he crashed) carried the code, while race control says deployed on lap 7 and in on lap 9. Lapped cars straddle the leader's laps in the same way. Rejected alternative: a majority vote across cars per lap. It happens to give 7–9 here, but has no principled tie-break and depends on field size.
  - *Combined TrackStatus codes.* FastF1 joins every code seen on a lap (`"12"`, `"124"`, `"41"`). The first version compared the whole string to `"1"`/`"2"`, so laps that were green-then-yellow were marked neutralised: 40 laps with yellows and 16 with a red flag in Monza 2024 FP1 alone. That would have made ticket 03 drop valid Long Run laps. Now both the lap flag and the race periods use the same per-code check.
  - *Lap filtering.* Rows with no `LapTime`, no `TyreLife` or an unrecognised Compound are dropped from `Session.laps`. The downstream run classifier (ticket 03) still has to decide what counts as a Long Run; this is strictly cleanup of FastF1 artefacts.

- **Deviations from the spec/ticket.** None in the code. The spec says Pit Loss "should draw on recent previous seasons (2022+, current regulations)". In this cloud environment the FastF1 live-timing endpoint returns 403 for 2022-season data, and the FastF1 fallback mirror (`livetiming-mirror.fastf1.dev`) is not on the proxy allowlist, so a cold cache skips 2022 races and only 2023+ contributes. The user worked around this outside the code: they downloaded Monza 2022 with FastF1 3.8.3 on their own machine and pushed the cache files to a never-merge branch, `fastf1-cache-2022`. Its `.cache/fastf1/2022/` was copied into this session's local cache (their `fastf1_http_cache.sqlite` was not copied). With it, Monza 2022 loads 971 laps and 19 usable pit stops (median 25.72 s); Monza 2023 gives 25 stops (median 25.45 s). Monza 2024 Pit Loss is (25.45 × 1 + 25.72 × 0.5) / 1.5 = **25.54 s**, against 25.45 s from 2023 alone.

- **Known limitations and follow-ups.**
  - *2022 FastF1 data unavailable in cloud sessions.* See the deviation above. The `.cache/` folder is gitignored and the container is temporary, so a fresh session is missing 2022 again unless it copies `.cache/fastf1/2022/` from the `fastf1-cache-2022` branch (`git archive origin/fastf1-cache-2022 .cache/fastf1/2022 | tar -x`). Without it, the loader quietly falls back to 2023+ and the slow tests still pass, because they don't assert which seasons contributed. That is deliberate: a test that needs 2022 would fail in every fresh container. Sideloading through git doesn't scale to a whole season for the Backtest. The lasting fix is environmental: add `livetiming-mirror.fastf1.dev` to the environment's allowed hosts.
  - *Cross-session Tyre Set identity.* Not reconstructed; see the rejected alternative above. The FastF1 findings and measured matchability (about half of used stints in Monza 2024 match exactly one earlier stint) are written up on ticket 04, with a suggestion to count new sets rather than track individual sets.
  - *Pit Loss ignores yellow-flag laps.* Clean reference laps and usable stops require `TrackStatus == "1"` exactly, so a stop whose in- or out-lap saw a local yellow is dropped. This loses some samples but never biases the number; left as is.
  - *Leader-based periods and lap 1.* A neutralisation that starts on the opening lap before the leader completes it is still caught, because it shows in the leader's lap-1 codes. A red flag is not reported as a period at all, since `NeutralisationPeriod.kind` only allows SC/VSC.
  - *Pit stops under SC/VSC.* Dropped from the Pit Loss sample because clean-reference lap times are only taken from green laps. This loses the stops that are the easiest for teams to take, but keeping them would bias Pit Loss downward (SC pit stops lose much less time); the simulator in later tickets models SC pits separately if needed.
  - *FastF1 deprecation warnings.* Loading sessions emits ~300 pandas/NumPy `DeprecationWarning`s. They originate in FastF1 itself and will clear when FastF1 updates; not silenced here.

- **Review feedback for the user.**
  - 2022 data is blocked in this sandbox (livetiming.formula1.com → 403 for 2022; the FastF1 fallback mirror is proxy-denied). The user supplied Monza 2022 from their own machine through the `fastf1-cache-2022` branch, so Monza 2024's Pit Loss now uses both 2022 and 2023 as the spec intends. Advised: keep that branch unmerged, and allowlist the FastF1 mirror before the full-season Backtest.
  - Branch rebased onto latest `main` before pushing to accommodate ticket 05 landing in parallel.
  - Self-review after first marking this done (given to the user when asked what was left): two criteria were ticked without real-data evidence (sprint sessions, and neutralisation periods, since Monza 2024 had none); the cache test only checked that files existed; the lap neutralisation flag had a bug; the Tyre Set finding hadn't been passed to ticket 04; and the first round wasn't strictly test-first, because the tests were never run red before the code was written.

**Follow-up fixes (2026-10-20), done test-first.** Four tests were added and run before any code change. Two failed for the expected reasons: practice laps under yellows were marked neutralised, and Jeddah's SC came out as laps 6–9 instead of 7–9. Both now pass after the fixes above. Two passed straight away, which means that code was already right and is now proven:
  - *Sprint weekend:* Austin 2024 loads sessions `FP1, SQ, S, Q`. The Sprint ran 19 laps (100 km at COTA) with 18+ drivers, and the race is 56 laps.
  - *Repeat loads:* a second Monza load with every HTTP request refused returns a weekend equal to the first. Also checked that the test can fail: the same blocked load against an empty cache raises (`Failed to load any schedule data`).
  - Expected values come from outside the loader: race-control messages for the SC laps, and the official distances for the race and sprint lengths.

**Cache removed from main (2026-10-20).** The `fastf1-cache-2022` branch had been merged into main, putting 6.7 MB of binary FastF1 cache files (including `fastf1_http_cache.sqlite`) under version control despite `.cache/` being gitignored. They were untracked from main at the user's request; the `fastf1-cache-2022` branch is kept as the source of Monza 2022 data. `livetiming-mirror.fastf1.dev` was still proxy-denied at the time, so cloud sessions that need 2022 data should restore it with `git fetch origin fastf1-cache-2022 && git archive origin/fastf1-cache-2022 .cache/fastf1/2022 | tar -x` until the mirror is allowlisted.

**From ticket 08 (2026-10-20).** `livetiming-mirror.fastf1.dev` is now reachable from cloud sessions. `livetiming.formula1.com` still returns 403 for 2022, but FastF1 falls back to the mirror on its own and loads 2022 races normally (checked with a cold cache on Singapore 2022: 7 × 403 from the primary, then 200s from the mirror). The `fastf1-cache-2022` sideload is no longer needed.

**Branches deleted (2026-10-21).** The `fastf1-cache-2022` and `ticket-07-fastf1-weekend-loader` branches were deleted from GitHub at the user's request; both were already merged into main. The `git archive origin/fastf1-cache-2022 …` restore command above no longer works and isn't needed: FastF1 downloads 2022 data from `livetiming-mirror.fastf1.dev` on its own (ticket 08). The Monza 2022 cache files are still in main's history (commit `bc5e912`) if ever needed.
