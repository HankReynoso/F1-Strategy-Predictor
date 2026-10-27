# 63: Tune Degradation shrinkage and replace the clamp at zero with a floor

**What to build:** Two linked changes to team Degradation, tuned together on the Tuning Seasons after ticket 62's ordering lands:

- **Shrinkage:** tune `degradation_shrinkage_laps` (4 today).
- **Floor:** replace the clamp at zero with a floor, a new setting in s/lap. No Compound's Degradation is used below it.

Ticket 53 found that zero rates are mostly fitting artefacts: where a rate is clamped to zero, that same race still wore the Compound at a median 0.03–0.04 s/lap. A zero rate puts a Stop Window at the race's edge, or makes it span the whole race ("lap 5–57"). A floor removes every such window. Stronger shrinkage pulls short, noisy fits towards the field.

**Blocked by:** 62 (Compound ordering per team)

**Status:** ready-for-agent

**Category:** enhancement

**Evidence (ticket 53, offline Backtests against `2026-10-27_baseline-v3`, judged on the Tuning Seasons only).** The sweep was coarse; these are not tuned values.

| | Tuning top-1 | Tuning top-3 | Tuning hits /1,931 | Rates at zero | 2025 top-1 / top-3 / hits (reported only) |
|---|---|---|---|---|---|
| Ordering (62) | 12.09% | 28.82% | 375 | 30.2% | 12.98% / 29.42% / 104 |
| + shrinkage 16 | 13.04% | 30.82% | 364 | 28.7% | 13.41% / 29.00% / 99 |
| + floor 0.02 | 12.03% | 29.32% | 451 | 0% | 12.94% / 28.78% / 117 |
| + floor 0.04 | 11.65% | 28.43% | 410 | 0% | 12.33% / 27.14% / 130 |
| + shrinkage 16 + floor 0.02 | 13.05% | 31.41% | 439 | 0% | 13.01% / 28.19% / 122 |

- With the floor, 20-lap-plus edge windows go from 116 to 0 in the Tuning Seasons, and interior windows hit rise to 422/932.
- Neither change moves ticket 52's stop counts: the green top pick stays about 74% 1-stop.
- The 2025 top-3 dip of the combination (−1.3 pp against baseline-v3) is reported, not used to decide. It's a reason to tune rather than adopt 16 and 0.02 as found.

- [ ] A floor setting replaces the clamp at zero for every Degradation source. Tests go through `predict()`: a fit at or below the floor is used at the floor, and the source is kept
- [ ] Shrinkage and the floor are tuned together on the Tuning Seasons only, with a decision rule fixed before the runs (as ticket 51 did: Tuning top-3 first). Record the grid, every result, and which seasons each decision was judged on
- [ ] 2025 is reported alongside for the chosen values and never used to choose
- [ ] Settings defaults are updated to the chosen values, with their comments
- [ ] An offline full Backtest is compared with the post-62 result, with ticket 53's zero-rate, stop-count and edge-window tables recorded after

## Comments

Filed from ticket 53's findings (fixes B and C), approved by the maintainer on 2026-10-27. The prototype knobs are `k` and `floor` in `.scratch/full-backtest/notes/53-zero-degradation/t53.py`.
