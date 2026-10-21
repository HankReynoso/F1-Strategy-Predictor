# 03: Pit Loss from before the era for first-season races

**What to build:** When a circuit has no same-era race before the one being predicted, Pit Loss falls back to earlier seasons at the circuit (2018–2021, recent seasons counting more), per the ADR-0004 exception. Circuits with same-era history keep today's Pit Loss. 2022 races stop failing for lack of Pit Loss history. See `../spec.md`.

**Blocked by:** 01 (Regulation Era as one source of truth)

**Status:** ready-for-agent

- [ ] A 2022 race at a circuit raced in 2018–2021 gets a Pit Loss measured from those seasons (slow test)
- [ ] A race with same-era history uses only same-era seasons for Pit Loss, as today
- [ ] Singapore 2024's Pit Loss and results are unchanged
- [ ] Which seasons a Pit Loss came from is visible in the single-race report
