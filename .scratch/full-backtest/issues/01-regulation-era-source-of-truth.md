# 01: Regulation Era as one source of truth

**What to build:** Define the Regulation Era boundaries (2022–2025, then 2026 onward) in one place, and make every historical input read from it. Historical Degradation draws only on earlier seasons in the same Regulation Era as the race being predicted (ADR-0004), replacing today's scattered minimum-season numbers. Pit Loss keeps today's behaviour in this ticket; its pre-era fallback is ticket 03. This is a prefactor: no result for a 2023–2025 race changes. See `../spec.md`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The Regulation Era boundaries are defined once, and the loader reads them instead of a hard-coded minimum season
- [ ] Historical Degradation for a race uses only earlier seasons in the same Regulation Era
- [ ] A 2022 race gets no Historical Degradation (slow test)
- [ ] A 2023 race's Historical Degradation uses 2022 only (slow test)
- [ ] Singapore 2024 and Monza 2024 single-race results are unchanged
- [ ] Tests go through the existing public calls; fast tests need no internet
