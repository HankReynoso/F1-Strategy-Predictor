# 06: Comparing predictions with the actual race

**What to build:** A second public call takes the Strategy Predictions plus the race's actual Stints and neutralisation periods and reports how the predictions did. Actual Strategies are extracted from race Stints. Per driver: whether the actual Strategy was the top pick, whether it was in the top 3 (Strategy Match on stop count and Compound sequence only), and whether each actual stop fell inside its predicted Stop Window (scored separately). The race is flagged as a Neutralised Race if it had a Safety Car or VSC. Drivers who retired or never completed a stop are marked unscoreable. A race summary gives counts of top-1 matches, top-3 matches and Stop Window hits.

**Blocked by:** 05 (Plausible pruning and Stop Windows)

**Status:** ready-for-agent

- [ ] Each driver's actual Strategy is extracted correctly from their race Stints
- [ ] Top-1 and top-3 Strategy Match are reported per driver
- [ ] A stop two laps outside the window still counts as a Strategy Match if stop count and Compounds match
- [ ] Stop Window hits are reported per stop, independently of Strategy Match
- [ ] A race with any Safety Car or VSC period is flagged as a Neutralised Race
- [ ] Retired drivers and drivers who never stopped are unscoreable and excluded from the summary counts
- [ ] A race summary reports top-1, top-3 and Stop Window hit counts out of scoreable drivers
- [ ] Tests use hand-built predictions and actual Stints through the public calls

## Comments

**From ticket 01 (2026-10-19).** The race weekend description's `Stint` has driver, Compound, start lap and end lap, and `NeutralisationPeriod` has kind and laps. There is no finishing status, so "retired" can only be inferred from a last Stint ending before `PreRaceInfo.race_laps`. That misses lapped finishers (who end on fewer laps without retiring). Consider adding a finishing status to `RaceOutcome`, populated by the loader in 07.

**From ticket 05 (2026-10-19).** Each `PlannedStop` carries `first_lap`, `best_lap` and `last_lap`. Because the other stops are re-optimised when one stop moves, consecutive Stop Windows of a multi-stop Strategy can overlap (e.g. H → S → H: laps 19–29 and 28–38). Score the n-th actual stop against the n-th predicted Stop Window, not against whichever window contains the lap. Predictions now contain only Plausible Candidate Strategies, so a driver's actual Strategy may be absent from their prediction; that should count as neither top-1 nor top-3.
