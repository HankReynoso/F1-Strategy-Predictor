# 05: Saving Backtest Results

**What to build:** A full Backtest run is saved in the repo's results folder as a machine-readable data file plus a readable summary generated from it, both named by date and a short label. The Backtest Result records its label, run date and time, settings, code version (commit plus an uncommitted-changes flag), seasons in scope and Held-out Season. A saved result reads back identical. Smoke Set runs print but aren't saved unless asked. Results hold scores only, never raw timing data. See `../spec.md`.

**Blocked by:** 04 (Backtest breakdowns)

**Status:** ready-for-agent

- [ ] A full run writes a data file and a readable summary, named by date and label
- [ ] Label, date and time, settings, code version with uncommitted-changes flag, seasons in scope and Held-out Season are recorded
- [ ] Saving then reading a Backtest Result gives an identical result
- [ ] The readable summary shows the headline, breakdowns and Excluded Races
- [ ] Runs can opt out of saving, and Smoke Set runs don't save by default
- [ ] Tests go through the public save and read calls
