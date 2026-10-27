# 59: Save a format-version-3 baseline

**What to build:** Run and save a full Backtest so a committed Backtest Result carries ticket 58's figures (Stop Window hits over Predicted-Strategy Stops, and average Stop Window width). Both committed results (`2026-10-26_first-openf1-run`, version 1; `2026-10-27_baseline`, version 2) predate format version 3, so they show both figures as "not recorded", and every compare against them warns that it can't compare them.

**Blocked by:** None. Consider running it after ticket 50 lands, so one rerun covers both changes.

**Status:** needs-triage

**Category:** enhancement

- [ ] A full Backtest is saved under `results/backtest/` at format version 3
- [ ] Its summary shows both figures for the green headline and every breakdown; the Tuning Seasons figures are recorded in this ticket, with the Held-out Season alongside
- [ ] Comparing it with `2026-10-27_baseline` shows the existing scores, plus the "can't be compared" warning for the new figures only

## Comments

Found during ticket 58: an old file can't be backfilled, because the figures need per-driver Candidate Strategies, which a Backtest Result never saves.

**Ticket 50 (2026-10-27).** Ticket 50's criterion 8 ran a full offline Backtest of the current code at format version 3 (`--offline --label ticket-50`, saved outside the repo). Compared with `2026-10-27_baseline`, it shows only the expected version-3 warning. Re-running it with `--results-dir results/backtest` and a baseline label would satisfy this ticket and cover ticket 50's change in the same run. Ticket 24's headline figures should be refreshed from that file at the same time. Run with `--offline` (ticket 36).
