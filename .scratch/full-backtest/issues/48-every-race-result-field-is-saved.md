# 48: Every `RaceResult` field is saved in the Backtest Result

**What to build:** `backtest_io` encodes and decodes each `RaceResult` field by hand. When ticket 28 added `history_warnings`, nothing noticed that the field was never saved, and ticket 39 had to fix it. Add a guard so the next new field can't be dropped silently: a test that saves a `RaceResult` with every field set to a non-default value and checks the reload equals it. The test should fail by naming the missing field when a new field isn't encoded.

**Blocked by:** None

**Status:** needs-triage

**Category:** enhancement

- [ ] A test fails, naming the field, when a `RaceResult` field isn't written to or read from the saved JSON
- [ ] The test goes through the public save and read calls

## Comments

Found during ticket 39 (review feedback). Could be folded into ticket 46 (small cleanups).
