# 07: FastF1 weekend loader + Pit Loss from history

**What to build:** Load a real race weekend (season + event name) from FastF1, using its on-disk cache, into the race weekend description: practice, sprint and qualifying laps with Tyre Set identity, Compound, tyre age, new/used and pit flags; each driver's team; race length; the race's actual Stints and Safety Car/VSC periods. Pit Loss for the circuit is measured from previous seasons' races there (2022+, recent seasons weighted more), never from the race being predicted. This is the only module that knows about FastF1.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] A chosen 2024 race weekend loads into the race weekend description
- [ ] All race starters are present with their teams
- [ ] Practice laps carry Tyre Set identity, Compound, tyre age and new/used
- [ ] Race length matches the official distance in laps
- [ ] The race's actual Stints and neutralisation periods are populated but kept separate from pre-race information
- [ ] Sprint sessions are included on sprint weekends
- [ ] Pit Loss is computed from previous seasons' races at the circuit and excludes the race itself
- [ ] Repeat loads come from the local cache
- [ ] A small number of tests check one cached real race; they can be marked as slower tests
