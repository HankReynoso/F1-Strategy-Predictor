# 10: Lapped finishers are scored as retired

**What to build:** Score lapped finishers like any other finisher. Today the scorer infers retirement from the last Stint ending before the race distance, so a driver who finished a lap down is marked unscoreable. The loader should carry each driver's finishing status (FastF1's race results give `Status` and `ClassifiedPosition`) on `RaceOutcome`, and the scorer should use it: classified finishers are scoreable whether lapped or not, retirements are not.

**Blocked by:** None

**Status:** needs-triage

- [ ] The race weekend description carries each starter's finishing status, kept with the race outcome, not pre-race information
- [ ] A lapped finisher with at least one stop is scoreable
- [ ] A retired driver is still unscoreable
- [ ] Hand-built tests go through `compare`; one slow test checks Singapore 2024 scores 19 or 18 drivers, not 7

## Comments

**From ticket 08 (2026-10-20).** This is the biggest effect on the Singapore 2024 "before" number: 13 of 20 drivers unscoreable, of whom 11 were lapped classified finishers. Counting every classified finisher (diagnostic outside the code) gives top-1 6/19, top-3 12/19, Stop Window hits 4/22, against the official 2/7, 6/7, 1/7. First raised in ticket 06's notes. Decide how to treat a driver classified despite retiring late (Magnussen, classified 19th after retiring on lap 57).
