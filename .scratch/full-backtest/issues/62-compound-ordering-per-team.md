# 62: A team's harder Compound never wears faster than its softer one

**What to build:** After shrinkage, each team's dry Compound rates are put in order: Soft ≥ Medium ≥ Hard. Where a team's rates are inverted, the inverted Compounds share their mean rate (pool-adjacent-violators on the Soft → Medium → Hard sequence), and each estimate keeps its own source. ADR-0003 already assumes a harder Compound wears no faster, but only in the next-softer bound at the end of the fallback chain. This extends the assumption to every team rate.

Ticket 53 found that zero or near-zero Soft rates, mostly from Push Laps or short Long Runs, make 1-stops that finish on Softs look free. In the Tuning Seasons, H → S and M → S are the top pick for 338 of 1,008 drivers, though drivers almost never run them. Ordering the rates removes those picks (338 → 11).

**Blocked by:** None (can start immediately)

**Status:** done

**Category:** enhancement

**Evidence (ticket 53, offline Backtests against `2026-10-27_baseline-v3`, judged on the Tuning Seasons only).**

| | Tuning top-1 | Tuning top-3 | Tuning Stop Window hits | 2025 top-1 / top-3 / hits (reported only) |
|---|---|---|---|---|
| Baseline-v3 | 10.88% | 26.35% | 219/1,931 | 12.88% / 29.48% / 74 of 626 |
| Ordering per team | 12.09% | 28.82% | 375/1,931 | 12.98% / 29.42% / 104 of 626 |

- Tickets 52 and 54, Tuning Seasons: the green top pick goes from 271 / 97 / 0 (1 / 2 / 3 stops) to 250 / 113 / 5. Interior windows hit go from 116/361 to 233/564, and 20-lap-plus edge windows from 83/87 to 121/130.
- The share of rates at zero barely moves (30.4% → 30.2%): a zero Hard is consistent with the ordering. Ticket 63 handles zeros.
- Ordering the field-level fallbacks as well scored worse (28.26% top-3), so apply it to team rates only.
- The prototype is `make_team_degradation(monotone=True)` in `.scratch/full-backtest/notes/53-zero-degradation/t53.py`.

- [x] For every team, the Soft rate ≥ the Medium rate ≥ the Hard rate after shrinkage. An inverted pair or run is replaced by its lap-weighted or plain mean (record which, and why), before the clamp at zero
- [x] Each Compound's `DegradationSource` is unchanged by the ordering
- [x] Tests go through `predict()` with hand-built weekends: an inverted Medium/Hard pair is pooled; already-ordered rates are untouched; a pooled Soft no longer makes an H → S 1-stop the top pick
- [x] ADR-0003 gets an amendment extending "a harder Compound wears no faster" from the fallback chain to every team rate, with ticket 53's measurements
- [x] An offline full Backtest is compared with `2026-10-27_baseline-v3`, judged on the Tuning Seasons, with 2025 reported alongside. Its Tuning top-3 matches the prototype's 28.82%, or the difference is explained
- [x] Ticket 53's zero-rate, stop-count and edge-window tables are recorded after the change

## Comments

Filed from ticket 53's findings (fix A), approved by the maintainer on 2026-10-27.

## Implementation notes

**Status: done (2026-10-27).** Every acceptance criterion is met. **Every comparison below was judged on the Tuning Seasons (2022–2024) only. 2025 is reported alongside and decided nothing.**

### What was built

- `degradation.team_degradation` now collects each team's unclamped (rate, source) per dry Compound, orders the three rates with `_in_compound_order`, and only then clamps at zero. `_in_compound_order` is pool-adjacent-violators on Soft → Medium → Hard. An inverted pair or run is replaced by its plain mean.
- The ordering covers a team's whole set of three rates, own fits and field-level fallbacks (field average, Circuit History, next-softer bound) alike, as in ticket 53's prototype. The field-level fallbacks themselves are not ordered before teams read them.
- Sources are untouched: a pooled estimate keeps the source of its own data.
- Seven new tests in `tests/test_pre_race_prediction.py` (ticket 62 section), all through `predict()` with hand-built one-team weekends, so each rate is exactly its own fit:
  - an inverted Medium/Hard pair shares its mean
  - a pooled Push Lap Medium and Long Run Hard keep their sources
  - already-ordered rates are untouched
  - an inverted run of three Compounds shares one mean
  - pooling uses raw rates, before the clamp (a −0.04 Soft gives a different answer from a clamped one)
  - a team's Circuit History Hard above its own Medium is pooled with it
  - a near-zero Soft no longer makes H → S the top pick (it was the top pick before the change; afterwards H → S only ties H → M, which wins the tie-break)
- Scratch: `.scratch/full-backtest/notes/62-compound-ordering/t62.py` reruns ticket 53's harness on the production function, the prototype, the pre-change copy and a lap-weighted alternative. It reads 53's pickled weekends and writes outside the repo.

### Backtest (offline, 2022–2025, saved outside the repo)

`uv run f1-strategy backtest 2022 2023 2024 2025 --offline --label ticket62 --results-dir <scratchpad>`, then `uv run f1-strategy compare results/backtest/2026-10-27_baseline-v3.json <scratchpad>/2026-10-27_ticket62.json`. The same 80 races are scored.

| | Tuning top-1 | Tuning top-3 | Tuning Stop Window hits | 2025 top-1 / top-3 / hits (reported only) |
|---|---|---|---|---|
| Baseline-v3 | 109.667/1,008 (10.88%) | 265.583 (26.35%) | 219/1,931 | 12.88% / 29.48% / 74 of 626 |
| Ticket 62 (production) | 121.869/1,008 (12.09%) | 290.524 (28.82%) | 375/1,931 | 48.029/370 (12.98%) / 108.836 (29.42%) / 104 of 626 |

**This reproduces ticket 53's candidate A exactly**: +2.47 pp Tuning top-3, +1.21 pp top-1, hits 219 → 375, and 2025 −0.06 pp top-3 with hits 74 → 104. Through the harness, the production function and `make_team_degradation(monotone=True)` give identical tables on every line. By season, top-3 rises in 2022 (+0.6 pp), 2023 (+3.0) and 2024 (+3.4). The largest circuit losers are Mexico City (−5.3 pp top-3), Austin (−3.8) and Barcelona (−2.8). The largest gainers are Imola (+18.9), Yas Island (+11.6), Baku (+8.5) and Las Vegas (+8.0).

### Ticket 53's tables after the change

**Zero rates, per driver** (Tuning / 2025 / all seasons):

| Source | Tuning before → after | 2025 before → after | All after |
|---|---|---|---|
| Long Runs | 372 → 386 /1,802 | 144 → 192 /685 | 578/2,487 (23%) |
| Push Laps | 354 → 302 /669 | 133 → 121 /251 | 423/920 (46%) |
| Field average | 298 → 329 /872 | 128 → 123 /281 | 452/1,153 (39%) |
| Circuit History | 39 → 39 /139 | 20 → 0 /40 | 39/179 (22%) |
| Next-softer bound | 0 → 0 /19 | – | 0/19 |
| All | 1,063 → 1,056 /3,501 (30.4% → 30.2%) | 425 → 436 /1,257 (33.8% → 34.7%) | 1,492/4,758 (31%) |

**Stop counts (ticket 52)**, Tuning Seasons. Actual green 1 / 2 / 3 / 4+: 115 / 202 / 48 / 3.

| | Green top pick 1 / 2 / 3 | Neutralised top pick 1 / 2 / 3 |
|---|---|---|
| Before | 271 / 97 / 0 | 520 / 108 / 12 |
| After | 250 / 113 / 5 | 499 / 108 / 33 |

2025 green top pick: 80 / 33 / 0 → 61 / 51 / 1, against actual 89 / 23 / 1 / 0.

**Stop Windows (ticket 54)**, edge = starts in the first 6 laps or ends in the last 6:

| | Interior hit | Edge, under 20 laps, hit | Edge, 20+ laps, hit | Mean width (laps) |
|---|---|---|---|---|
| Tuning before | 116/361 | 20/224 | 83/87 | 11.6 |
| Tuning after | 233/564 | 21/160 | 121/130 | 13.4 |
| 2025 before | 25/66 | 1/75 | 48/51 | 15.4 |
| 2025 after | 42/116 | 3/56 | 59/61 | 16.1 |

**Soft-ending 1-stops**, Tuning top picks: H → S 200 → 6 and M → S 138 → 5, so 338 → 11 of 1,008, as in ticket 53.

### Decisions and alternatives rejected

- **Plain mean, not lap-weighted** (the ticket asked which, and why). Judged on the Tuning Seasons:
  - plain: 28.82% top-3, 12.09% top-1, 375 hits
  - lap-weighted: 28.29%, 11.80%, 368 hits
  - The lap-weighted variant weighted a team's own fit by its laps plus the shrinkage laps, and a field-level fallback by the shrinkage laps alone. A fallback has no laps of its own, so any weight is a convention. Shrinkage has already pulled a thin fit towards the field, so weighting it by laps again counts that evidence twice.
  - 2025, reported only: plain 29.42%, lap-weighted 28.63% top-3.
- **Team rates only, not the field-level fallbacks.** Ordering the fallbacks too scored 28.26% Tuning top-3 in ticket 53. Not re-measured here.
- **Order before the clamp.** This follows the ticket and the prototype. A negative raw Soft then pulls a pooled run lower than a clamped zero would. That is the intent: the clamp is only there so Simulated Race Time never sees a negative rate.
- **A team's fallback Compounds are ordered with its own fits.** The prototype did this. It is what "every team rate" means in the ADR amendment. It is why a Circuit History Hard above a team's own Medium now pools with that Medium.

### Deviations from the ticket and spec

- **Five existing tests had inverted fixtures and were changed so they still test what they were written for.** None of them was testing ordering:
  - `test_end_to_end_report.py`'s Circuit History header test: the history Hard went from 0.08 to 0.03 against a 0.05 Medium
  - ticket 13's short-negative-fit test: Alpha's Medium and Hard went from 0.07/0.04 to 0.03/0.02, below its shrunk Soft
  - three ticket 11 history tests: the Circuit History Hard went from 0.08 to 0.03 against a 0.05 Medium, and from 0.11 to 0.06 against a 0.08 Medium
  - Each assertion still checks that the history rate flows through unchanged.
- **Spec:** `.scratch/pre-race-prediction-single-race/spec.md`, the Degradation model module description, now says each team's rates are ordered, with a pointer to this ticket and ADR-0003.
- **`CONTEXT.md`:** the Degradation entry now states that a harder Compound wears no faster, so each team's Degradation is ordered Soft ≥ Medium ≥ Hard.
- **ADR-0003:** amended with the rule, the measurements above and the options considered.
- No new baseline was saved. Saving `baseline-v4` is the maintainer's call (ticket 59's process).

### Open questions, limitations and follow-ups

- The zero share is unchanged, as ticket 53 predicted. Zero Hards are consistent with the ordering, and 20-lap-plus edge windows *rise* in count (87 → 130 Tuning) because more stops now land on predicted Strategies. Ticket 63 (shrinkage and a floor) is the fix for both. It should now be tuned on top of this change.
- 2025 Circuit History zeros fall from 20 to 0, but 2025 Long Run zeros rise from 144 to 192. The likely cause, not yet checked per driver, is that pooling an inverted Medium with a negative raw Hard pulls the Medium to zero as well.
- Ties between Soft and Medium are now common where a Soft was pooled. They are broken by the Candidate sort key (alphabetical on Compound letters), which favours Medium over Soft. Compound Pace (ticket 64) is what should separate them. No new ticket: 64 already covers it.
- **Test suite.** All non-real-data tests were run, except the slow `*_real_data` files, which weren't. These fail identically on a clean checkout of `e626cea`, so the change didn't cause them:
  - `test_fastf1_weekend_loader.py`: 7 failures and 13 errors, the live-timing archive returning no lap data for 2024 Monza
  - `test_singapore_scoreability.py` and `test_example_notebook.py`: they load live data
  - `test_committed_results_load_with_the_figures_not_recorded[baseline-v3]`: ticket 61
- Ticket 52 is not closed: the green top pick stays 1-stop for 68% of Tuning drivers against an actual 31%.

### Review feedback to the user

- The adopted rule matches the prototype exactly, so ticket 53's evidence carries over unchanged. The lap-weighted alternative was measured rather than assumed worse.
- Changing four old fixtures was necessary: each had a Hard rate above its Medium, which the new rule forbids. Check you're comfortable that those tests still say what they meant to.
- The Mexico City and Austin top-3 drops are worth a look once Compound Pace lands. Both are circuits where Softs are raced, and the Medium-over-Soft tie-break may be hurting there.
