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
