# 22: OpenF1 race loader (race outcome, pit loss, historical degradation)

**What to build:** Finish `openf1_loader` by adding the race side:
- `_race_stints` from `/v1/stints?session_key=<race>`.
- `_neutralisation_periods` from `/v1/race_control`, with explicit end-event handling: VSC starts on "VIRTUAL SAFETY CAR DEPLOYED" and ends on "VIRTUAL SAFETY CAR ENDING" (same `lap_number`); SC starts on "SAFETY CAR DEPLOYED" and ends on "SAFETY CAR IN THIS LAP" (same `lap_number`). Red flag is not a neutralisation (matches current loader). If an "end" event is missing, cap the period at the race lap count and log a quality warning.
- `_finishing_status` from `/v1/session_result`: `took_flag = not dnf and not dns and not dsq`.
- `_pit_losses_in` and `_historical_stint_rates` using lap times from `/v1/laps` with the neutralisation ranges above as the green-flag filter. **Do not** use `/v1/pit.pit_duration` for Pit Loss — at São Paulo R 2024 the mean `pit_duration` was 661 s because the red-flag parking time was counted as a pit stop.

**Blocked by:** 21.

**Status:** needs-triage

**Category:** enhancement

Field-by-field recipes, data-quality notes (`pit_duration` pollution, `stop_duration` null rate, missing per-lap TrackStatus) and the three sampled weekends in [`openf1-findings.md`](../openf1-findings.md). Follow-up from [ticket 18](18-check-openf1-as-second-data-source.md).
