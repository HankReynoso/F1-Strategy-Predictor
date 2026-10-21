# 08: Smoke Set and README

**What to build:** A Smoke Set mode on the command runs the Smoke Set: Singapore, Monza, Baku, Austin and Jeddah 2024, plus one conventional, green 2022 Dry Race chosen here and recorded in the spec and `CONTEXT.md`. A slow end-to-end test runs it and checks there are no unexpected Excluded Races. The README explains how to run a full Backtest (on the laptop), the Smoke Set (anywhere), and a comparison, including the measured download cost from ticket 02. See `../spec.md`.

**Blocked by:** 03 (Pit Loss from before the era), 04 (Backtest breakdowns), 06 (Comparing two Backtest Results)

**Status:** ready-for-agent

- [ ] The Smoke Set mode runs the six races and prints the Backtest Result without saving it
- [ ] The chosen 2022 race is recorded in the spec and `CONTEXT.md`
- [ ] A slow test runs the Smoke Set with no unexpected Excluded Races
- [ ] Singapore 2024 within the Smoke Set matches its known single-race scores (top-1 6.5/18, top-3 13.75/18, Stop Window hits 3/20)
- [ ] The README covers full Backtests, the Smoke Set and comparisons, with download cost
