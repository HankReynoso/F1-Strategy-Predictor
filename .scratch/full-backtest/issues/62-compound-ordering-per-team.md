# 62: A team's harder Compound never wears faster than its softer one

**What to build:** After shrinkage, each team's dry Compound rates are put in order: Soft ≥ Medium ≥ Hard. Where a team's rates are inverted, the inverted Compounds share their mean rate (pool-adjacent-violators on the Soft → Medium → Hard sequence), and each estimate keeps its own source. ADR-0003 already assumes a harder Compound wears no faster, but only in the next-softer bound at the end of the fallback chain. This extends the assumption to every team rate.

Ticket 53 found that zero or near-zero Soft rates, mostly from Push Laps or short Long Runs, make 1-stops that finish on Softs look free. In the Tuning Seasons, H → S and M → S are the top pick for 338 of 1,008 drivers, though drivers almost never run them. Ordering the rates removes those picks (338 → 11).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

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

- [ ] For every team, the Soft rate ≥ the Medium rate ≥ the Hard rate after shrinkage. An inverted pair or run is replaced by its lap-weighted or plain mean (record which, and why), before the clamp at zero
- [ ] Each Compound's `DegradationSource` is unchanged by the ordering
- [ ] Tests go through `predict()` with hand-built weekends: an inverted Medium/Hard pair is pooled; already-ordered rates are untouched; a pooled Soft no longer makes an H → S 1-stop the top pick
- [ ] ADR-0003 gets an amendment extending "a harder Compound wears no faster" from the fallback chain to every team rate, with ticket 53's measurements
- [ ] An offline full Backtest is compared with `2026-10-27_baseline-v3`, judged on the Tuning Seasons, with 2025 reported alongside. Its Tuning top-3 matches the prototype's 28.82%, or the difference is explained
- [ ] Ticket 53's zero-rate, stop-count and edge-window tables are recorded after the change

## Comments

Filed from ticket 53's findings (fix A), approved by the maintainer on 2026-10-27.
