# 04: Backtest breakdowns

**What to build:** The Backtest Result gains race-averaged versions of the headline scores; breakdowns by season, by circuit, by sprint vs conventional, and Tuning Seasons (2022–2024) vs Held-out Season (2025); counts of each Degradation source used; and the Excluded Race count. Tuning Seasons and Held-out Season are settings of the run, not hard-coded into scoring. Every figure shows its numerator and denominator, and breakdowns are derivable from the per-race records. The command prints them. See `../spec.md`.

**Blocked by:** 02 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Race-averaged scores are reported next to the pooled ones, and differ as expected when races have different numbers of scoreable drivers
- [ ] Season, circuit and sprint/conventional breakdowns add up to the totals
- [ ] Tuning Seasons and Held-out Season are reported side by side, and come from the run's settings
- [ ] Degradation source counts and the Excluded Race count are reported
- [ ] Tests go through the Backtest call with hand-built weekends
