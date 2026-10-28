# Degradation for an unrun Compound comes from circuit race history, then a next-softer bound

When no team has Long Runs or Push Laps on a dry Compound this weekend, its Degradation is estimated from previous seasons' race Stints at the same circuit (current regulations, recent seasons counting more, never the race being predicted). If that history is missing, the next-softer Compound's field-average Degradation is used as an upper bound, on the assumption that a harder Compound wears no faster. Each estimate keeps its source. This amends ticket 02's decision to refuse rather than invent a rate: teams routinely save the Hard for the race, so refusing made 3 of 7 recent 2024 races unpredictable (ticket 08), and race Stints are real race running on exactly that Compound.

## Considered Options

- **Keep refusing** (ticket 02): rejected because it rules out a large share of races, including Monza, Abu Dhabi and Las Vegas 2024.
- **Fit shorter practice runs for that Compound only**: rejected because the runs that exist are one or two laps, noisier than any fallback, and at Monza 2024 there is still almost nothing to fit.
- **Next-softer bound alone**: kept only as the last step, because it ignores real data that is usually available.

## Implementation note (2026-10-20)

The chain resolves softer→harder across dry Compounds. If the next-softer Compound was also unrun this weekend, its own fallback (likely history) is already resolved by the time the harder Compound reads it, so the bound chain propagates through intermediate gaps. SOFT has no softer bound; if Soft is unrun, no history exists for it and no softer Compound is available, the predictor raises a clear refusal and the command exits with code 2.

## Amendment (2026-10-27): every team rate is in Compound order

The assumption that a harder Compound wears no faster was only used at the end of the fallback chain, in the next-softer bound. It now applies to every team's rates. After shrinkage and before the clamp at zero, each team's three dry rates are put in order, Soft ≥ Medium ≥ Hard. An inverted pair or run is replaced by its plain mean (pool-adjacent-violators on Soft → Medium → Hard). This covers own fits and field-level fallbacks alike, and each estimate keeps its own source.

[Ticket 53](../../.scratch/full-backtest/issues/53-a-third-of-degradation-rates-are-zero.md) found that zero or near-zero Soft rates, mostly from Push Laps or short Long Runs, made 1-stops finishing on Softs look free. In the Tuning Seasons, H → S or M → S was the top pick for 338 of 1,008 drivers, though drivers almost never ran them. [Ticket 62](../../.scratch/full-backtest/issues/62-compound-ordering-per-team.md) built the ordering. Offline 2022–2025 Backtests against `2026-10-27_baseline-v3`, judged on the Tuning Seasons only:

| | Tuning top-1 | Tuning top-3 | Tuning Stop Window hits | 2025 top-1 / top-3 / hits (reported only) |
|---|---|---|---|---|
| Baseline-v3 | 10.88% | 26.35% | 219/1,931 | 12.88% / 29.48% / 74 of 626 |
| Ordering per team, plain mean (adopted) | 12.09% | 28.82% | 375/1,931 | 12.98% / 29.42% / 104 of 626 |
| Ordering per team, lap-weighted mean | 11.80% | 28.29% | 368/1,931 | 12.64% / 28.63% / 105 of 626 |
| Ordering on the field-level fallbacks as well | 11.81% | 28.26% | 357/1,931 | 13.08% / 29.72% / 105 of 626 |

The ordering works on which Compound looks free, not on how many rates are zero. The share of Tuning rates at zero barely moves (30.4% → 30.2%), because a zero Hard is consistent with the ordering. Zeros are [ticket 63](../../.scratch/full-backtest/issues/63-tune-shrinkage-and-a-degradation-floor.md)'s.

## Considered Options (ordering, 2026-10-27)

- **Plain mean of an inverted run** (adopted): one vote per Compound. It scored best on the Tuning Seasons.
- **Lap-weighted mean**: rejected. A field-level fallback has no laps of its own, so the weight is a convention (own laps plus shrinkage laps for an own fit, shrinkage laps for a fallback). It scored lower on the Tuning Seasons (above).
- **Ordering the field-level fallbacks as well as the team rates**: rejected. It scored lower on the Tuning Seasons (ticket 53).
- **Leave inverted rates alone**: rejected. It keeps the free-Soft 1-stops.
