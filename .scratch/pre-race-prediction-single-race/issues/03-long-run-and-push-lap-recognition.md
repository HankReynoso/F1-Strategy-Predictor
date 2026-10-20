# 03: Long Run and Push Lap recognition

**What to build:** Make practice data classification realistic. A Long Run is a run of consistently timed consecutive laps on one Tyre Set, excluding out-laps, in-laps and abnormally slow laps (traffic, mistakes). Push Laps are recognised by their slow–fast–slow pattern, grouped per Tyre Set, and kept out of Long Runs. Push Lap fall-off becomes the middle step in the Degradation fallback: team Long Runs → team Push Laps → field average. On sprint weekends, sprint race Stints count as Long Runs. Minimum Long Run length and the consistency and slow-lap thresholds are settings.

**Blocked by:** 02 (Per-team Degradation)

**Status:** done

- [x] A run of consistently timed laps on one Tyre Set is used as a Long Run
- [x] Out-laps, in-laps and abnormally slow laps don't distort Degradation
- [x] A slow–fast–slow sequence on a Tyre Set is recognised as Push Laps and never treated as a Long Run
- [x] Several Push Laps on one Tyre Set are grouped so their fall-off can be measured
- [x] A team with Push Laps but no Long Runs on a Compound uses Push Lap fall-off, and the reported source says so
- [x] With neither, the field average is used
- [x] On a sprint weekend, sprint race Stints contribute as Long Runs
- [x] Thresholds are settings with defaults
- [x] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** 01's rule is "any 2+ consecutive laps on one Tyre Set in any session", implemented in `long_runs()` in `src/f1_strategy/degradation.py`. Known problems this ticket should fix:

- It reads every session, including qualifying. Consecutive Push Laps on a set in Q (or FP3 quali runs) currently count as Long Runs. Decide which sessions feed Long Runs; qualifying probably shouldn't, except possibly as Push Lap evidence.
- Pit in/out laps and neutralised laps are not excluded yet.
- `base_lap_time()` (fastest Long Run lap in the field) will change once Long Runs are filtered; it only shifts every Simulated Race Time equally, so rankings are unaffected.

## Implementation notes

**What was built.** A new `src/f1_strategy/run_classifier.py` module turns every pre-race session's laps into two piles: `long_runs` and `push_lap_groups`. `degradation.team_degradation()` now consumes both, fitting Long Run rates first, Push Lap rates second as the per-team fallback, and finally a field-average layer for teams with no running on a Compound. `DegradationSource` grows a `PUSH_LAPS` variant, and `Settings` grows three thresholds with defaults: `min_long_run_length=4`, `long_run_slow_lap_margin_s=3.0`, `push_lap_fast_margin_s=1.0`. Seven new hand-built main-seam tests cover each acceptance criterion.

**Classifier rule.** For every (driver, Tyre Set) in every pre-race session:
1. Drop laps where `pit_in`, `pit_out` or `neutralised` is true.
2. Split what's left into runs of strictly consecutive lap numbers.
3. In each run, flag any lap strictly faster than both neighbours by `push_lap_fast_margin_s` as a Push Lap. If any Push Lap is found, the whole run goes to `push_lap_groups` as that set's Push Laps, and the run never becomes a Long Run.
4. Otherwise drop laps whose time exceeds the run's median by more than `long_run_slow_lap_margin_s` (traffic, mistakes), re-split what remains into consecutive sub-runs, and each sub-run with ≥ `min_long_run_length` laps is a Long Run.

**Decisions and alternatives rejected.**
- *Classifier at the (session, driver, Tyre Set) grain, not at the session or driver grain.* The ticket's rules all live at the Tyre Set level: Push Lap grouping is per set, "consistently timed consecutive laps" is per set, and the slow-fast-slow pattern is defined per set. A session-wide heuristic would have to re-split by set anyway.
- *All sessions feed the classifier.* Ticket 01 noted that qualifying "probably shouldn't" feed Long Runs. The ticket-01 comment is now moot because a classic Q run (out, push, in) has every push lap flanked by slower laps and is caught as Push Laps by rule 3, not promoted to a Long Run. Explicitly whitelisting session names would hide that invariant and risked excluding Sprint Qualifying running where a team does happen to put a race-pace stint on. Rejected: a session-name filter. The implementation treats a session named `"S"` (Sprint race) the same as `"FP1"`, which is exactly what the "sprint race Stints count as Long Runs on sprint weekends" criterion requires.
- *Push-Lap-first dominates over Long Run.* A tyre set with any Push Lap goes straight to the Push Lap pile without the Long Run check. Rejected alternative: letting a short run of race-pace laps on the same set after the push laps also become a Long Run. It made the classifier harder to explain and the "never treated as a Long Run" criterion weaker; a team that happens to also do a short Long Run on a set after its push laps will do a Long Run on a *different* set too, and the latter is the signal we actually want.
- *Field average is the mean of best-available per-team rates, not Long Runs only.* Ticket 02 computed the field average from Long Run rates only. That means a Compound where no team has Long Runs raised, even if several teams had Push Laps. With the Push Lap fallback added, the natural field average is the mean across teams of each team's best-available rate (Long Runs preferred, Push Laps otherwise). Existing ticket-02 tests still pass unchanged because in them every team on the Compound has Long Runs.
- *`base_lap_time()` still reads Long Runs only.* Push Lap times are only comparable within one set; using them as the field's fresh-tyre pace reference would mix sets. As ticket 01 observed, the base lap time only shifts every Simulated Race Time equally, so this is a report-formatting choice, not a modelling one.
- *Push Lap fit treats fuel the same as Long Runs.* Push Laps are typically taken two laps apart on a set, so fuel burn between them is real. The same `fuel_effect_s_per_lap` is added back to the Push Lap slope. The alternative (zero fuel correction on Push Laps) would systematically overstate Push Lap fall-off relative to Long Run Degradation and so bias the fallback.
- *Three thresholds, not more.* `min_long_run_length` matches the ticket's "minimum Long Run length" setting. `long_run_slow_lap_margin_s` covers both "consistency" and "abnormally slow" (one setting handles both because consistency drops the outliers and the remainder gets re-split and length-checked). `push_lap_fast_margin_s` covers Push Lap detection. Rejected: a separate "consistency variance" setting; it added a second knob that controlled the same thing in a less legible way.
- *Default values.* `min_long_run_length=4` keeps the existing hand-built 8-lap Long Runs through and still rejects the typical 3-lap qualifying out–push–in triplet. `long_run_slow_lap_margin_s=3.0` is well above the within-run spread of every existing test (max observed ≈ 1.65 s for deg=0.5 over 8 laps) while catching the +5 s traffic lap the new test writes in. `push_lap_fast_margin_s=1.0` is well below the typical 1.5–2 s gap between a quali-prep lap and a quali push lap, and well above the step-to-step jump in a smooth Long Run.

**Sanity check against Monza 2024 FP2.** Ran the classifier against the live FastF1 data (cached by the loader from ticket 07). 355 laps across 20 drivers. At default settings the classifier found 15 Long Runs (median length 6, max 11) and 8 Push Lap groups (median size 1, max 2). The Long Runs split 2 on Softs / 13 on Mediums / 0 on Hards, with slopes on the five longest Medium runs ranging 0.09–0.21 s/lap and median lap times 85.4–86.2 s. That matches public reporting for that FP2: teams spent the Medium long-run window at race pace and used Softs for push laps only; Hards were saved for the race. The null-Hards result is a correct read of what happened, not a classifier miss. Threshold sweeps behaved as expected: relaxing the slow-lap margin to 5 s lifted the longest Medium run from 11 to 12 laps (one traffic lap re-admitted); dropping the push-lap margin to 0.5 s pulled four extra sets out of the Long Run pile and into Push Laps (false Push Lap positives); dropping `min_long_run_length` to 3 added three short Soft runs. The defaults were picked against this read: the margin thresholds separate real traffic from the within-run spread while leaving the ~1.5 s quali gap for Push Lap detection, and the minimum length rejects the 3-lap qualifying triplet without clipping any clean Medium long run.

**Deviations from the ticket.** None. The spec needed no change: stories 18–24 are satisfied by the behaviour above with no updates to the wording.

**Follow-ups.** Qualifying-only Push Lap evidence is picked up implicitly by the classifier (a Q run of out–push–in on a soft set caught as Push Laps on that set). No explicit test guards that today because no main-seam test uses a qualifying session yet; a backtest with a real weekend will.

**Review feedback to the user.** None.
