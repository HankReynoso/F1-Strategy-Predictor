# 03: Long Run and Push Lap recognition

**What to build:** Make practice data classification realistic. A Long Run is a run of consistently timed consecutive laps on one Tyre Set, excluding out-laps, in-laps and abnormally slow laps (traffic, mistakes). Push Laps are recognised by their slow–fast–slow pattern, grouped per Tyre Set, and kept out of Long Runs. Push Lap fall-off becomes the middle step in the Degradation fallback: team Long Runs → team Push Laps → field average. On sprint weekends, sprint race Stints count as Long Runs. Minimum Long Run length and the consistency and slow-lap thresholds are settings.

**Blocked by:** 02 (Per-team Degradation)

**Status:** ready-for-agent

- [ ] A run of consistently timed laps on one Tyre Set is used as a Long Run
- [ ] Out-laps, in-laps and abnormally slow laps don't distort Degradation
- [ ] A slow–fast–slow sequence on a Tyre Set is recognised as Push Laps and never treated as a Long Run
- [ ] Several Push Laps on one Tyre Set are grouped so their fall-off can be measured
- [ ] A team with Push Laps but no Long Runs on a Compound uses Push Lap fall-off, and the reported source says so
- [ ] With neither, the field average is used
- [ ] On a sprint weekend, sprint race Stints contribute as Long Runs
- [ ] Thresholds are settings with defaults
- [ ] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** 01's rule is "any 2+ consecutive laps on one Tyre Set in any session", implemented in `long_runs()` in `src/f1_strategy/degradation.py`. Known problems this ticket should fix:

- It reads every session, including qualifying. Consecutive Push Laps on a set in Q (or FP3 quali runs) currently count as Long Runs. Decide which sessions feed Long Runs; qualifying probably shouldn't, except possibly as Push Lap evidence.
- Pit in/out laps and neutralised laps are not excluded yet.
- `base_lap_time()` (fastest Long Run lap in the field) will change once Long Runs are filtered; it only shifts every Simulated Race Time equally, so rankings are unaffected.
