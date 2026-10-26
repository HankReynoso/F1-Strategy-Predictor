# 32: History warning for a cancelled past race is misleading

**What to build:** When a race's history scan skips a Cancelled Race (e.g. 2025 Imola reaching back to the called-off 2023 Imola), the data-quality warning says "2023 Imola: no usable past-race samples (fetch succeeded with no rows or no clean laps)". Nothing was fetched and the race never took place. The warning should say the past race was cancelled, so a reader of the Backtest Result's history warnings doesn't go looking for a data gap that isn't there.

**Blocked by:** None (can start immediately)

**Status:** needs-triage

**Category:** enhancement

## Comments

Found while doing ticket 29. `openf1_loader._load_past_race_rows` returns `None` for a cancelled meeting, and `data.measure_pit_loss_and_history` turns every empty `PastRaceSamples` into the generic warning, so the router can't tell a cancellation from a clean-laps shortfall. Needs the samples (or a sibling return) to carry a reason.

- [ ] A cancelled past race produces a warning saying it was cancelled
- [ ] A race that ran but gave no clean laps keeps the existing wording
- [ ] Fixture-based test through `data.load_weekend`, no network
