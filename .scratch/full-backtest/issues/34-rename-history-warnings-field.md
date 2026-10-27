# 34: `RaceResult.history_warnings` holds more than history

**What to build:** Since ticket 30, `RaceResult.history_warnings` (copied from `PreRaceInfo.data_quality_warnings`) also carries the target weekend's own Data Quality Warnings, e.g. "Race /v1/stints: dropped 1 of 57 rows with empty lap_start/lap_end". The report section is now "Data quality warnings (tickets 28, 30)", but the field name in the code and in the saved Backtest Result JSON still says "history". Rename it to `data_quality_warnings` so a reader of the saved file isn't misled.

**Blocked by:** None. Consider doing it together with ticket 26, which adds race-control warnings and already proposes one place for all of them on `RaceResult`.

**Status:** needs-triage

**Category:** enhancement

## Comments

Found during ticket 30. Ticket 30 left the field name alone because renaming it changes the saved Backtest Result format (ADR-0005, `backtest_io`), and `results/backtest/2026-10-26_baseline.json` would need either a format bump or a read-side alias.

- [ ] One field name for all Data Quality Warnings on `RaceResult`
- [ ] Saved results from before the rename still load (alias or format bump per ADR-0005)
- [ ] `CONTEXT.md` **Data Quality Warning** entry still matches

**Ticket 39 (2026-10-26).** The saved Backtest Result now writes the warnings under `data_quality_warnings` (format version 2, ADR-0005). The rename here is code-only: `RaceResult.history_warnings` becomes `data_quality_warnings`, and `backtest_io._encode_race` / `_decode_race` and `backtest_compare._data_quality_warnings_diff` follow. There is no format bump and no read alias. The second criterion above is already met.
