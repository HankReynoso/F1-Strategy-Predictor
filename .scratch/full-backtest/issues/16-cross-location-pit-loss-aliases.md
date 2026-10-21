# 16: Cross-season `Location` aliases for Pit Loss history

**What to build:** Teach the loader to treat renamed FastF1 `Location` strings as the same circuit when matching previous seasons' races for Pit Loss. The three known cases in the 2022–2025 window are `Marina Bay` (same venue as pre-era `Singapore`), `Monaco` (same venue as pre-era `Monte Carlo`) and `Miami Gardens` (same venue as same-era `Miami` 2022–2024). Without this, those renamed circuits currently fall into ticket 07's estimated-Pit-Loss path even though measurable earlier races exist.

**Blocked by:** 07 (Estimated Pit Loss for first-time circuits — this ticket is a direct follow-up to 07's "Deviations" section)

**Status:** needs-triage

- [ ] Define a `Location` alias map alongside `pit_lane_table.py` or in `fastf1_loader.py`, so the loader can match `Marina Bay` to `Singapore`, `Monaco` to `Monte Carlo`, and `Miami Gardens` to `Miami` when scanning pre-era / same-era schedules.
- [ ] Historical Degradation respects the same alias map (ADR-0004 still restricts to same era, so this only matters if two same-era seasons used different `Location` strings for the same circuit).
- [ ] A slow test proves Monaco 2022 Pit Loss comes from `Monte Carlo` pre-era seasons, Marina Bay 2022 Pit Loss comes from `Singapore` pre-era seasons, and Miami Gardens 2025 Pit Loss comes from `Miami` 2022–2024.
- [ ] Ticket 07's estimated-Pit-Loss count on a 2022–2025 Backtest shrinks from "every renamed circuit's first-season race plus Miami 2022 plus Las Vegas 2023" down to only Miami 2022 and Las Vegas 2023.
- [ ] Each alias has a comment pointing to the FastF1 schedule rows that make the rename visible, so a future reader can tell why the two keys represent one circuit.
