# 07: Estimated Pit Loss for first-time circuits

**What to build:** A circuit with no previous race at all gets a Pit Loss estimated from its pit lane length and speed limit, plus a typical stationary time and an allowance for slowing into and accelerating out of the pit lane. FastF1 doesn't provide pit lane lengths, so they come from a small hand-maintained table covering only circuits that need it (e.g. Miami 2022, plus any others found), filled from published figures with each source noted. An estimated Pit Loss is flagged in the race weekend description, the single-race report and the Backtest Result. A circuit with no history and no table entry becomes an Excluded Race with that reason. See `../spec.md`.

**Blocked by:** 02 (Tracer bullet), 03 (Pit Loss from before the era)

**Status:** ready-for-agent

- [ ] Every 2022–2025 circuit with no previous race is identified and listed in this ticket
- [ ] Each has a table entry with pit lane length, speed limit and source
- [ ] Miami 2022 can be predicted, with its Pit Loss flagged as estimated
- [ ] The flag appears in the single-race report and in the Backtest Result
- [ ] A circuit with neither history nor a table entry becomes an Excluded Race with that reason
- [ ] Circuits with history never use the estimate
