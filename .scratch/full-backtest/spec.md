# Spec: Full Backtest across the 2022–2025 Regulation Era

Status: ready-for-agent

## Problem Statement

I can predict and score one race at a time, but one race says very little about whether the model is any good. Singapore 2024 swung from 2/7 to 6.5/18 top-1 as scoring bugs were fixed, and Las Vegas scores zero for reasons only visible there. Before I tune settings or add Circuit Tendency, I need a single, trustworthy number for how well Pre-race Predictions match what drivers actually ran across every race the model can handle, broken down so I can see where it's strong and where it fails. I also need that number saved, so that every later change can be judged against it instead of against my memory.

## Solution

A Backtest that runs Pre-race Predictions with default settings on every Dry Race of the 2022–2025 Regulation Era, scores each one against the actual race with the existing comparison, and produces a Backtest Result. The headline score is pooled over scoreable drivers in green races only (top-1 and top-3 Strategy Match, Stop Window hits), shown next to a race-averaged figure, a Neutralised Race figure, an all-races figure, and breakdowns by season, circuit, and sprint vs conventional. Tuning Seasons (2022–2024) and the Held-out Season (2025) are reported side by side from day one. Races the model refuses, that crash, or that can't be loaded become Excluded Races, listed with their reasons, and the run carries on.

Each run saves its Backtest Result in the repo as a data file plus a readable summary. A compare command shows how every score moved between two Backtest Results, and which races moved most.

Full runs happen on the user's laptop, where the FastF1 cache persists. Cloud sessions run the Smoke Set, a small fixed set of races covering every path through the model.

The loader changes this needs: history (Historical Degradation, and the inputs for later Tendencies) comes only from the same Regulation Era (ADR-0004); Pit Loss may use seasons from before the era, so 2022 races can be predicted; and a circuit with no previous race at all gets a Pit Loss estimated from its pit lane length and speed limit, flagged in the output.

## User Stories

### Running a Backtest

1. As an F1 fan, I want one command that runs a Backtest over the whole 2022–2025 Regulation Era, so that I get a single answer to "how good is the model?".
2. As an F1 fan, I want to run a Backtest over chosen seasons only, so that I can check one season quickly.
3. As an F1 fan, I want to run the Smoke Set with one command, so that I can check nothing broke without waiting for a full run.
4. As an F1 fan, I want every Dry Race in scope included, sprint weekends and Neutralised Races too, so that the score reflects every race the model is meant to handle.
5. As an F1 fan, I want the Backtest to use default settings unless I say otherwise, so that the first full run is an honest, untuned baseline.
6. As an F1 fan, I want to see progress while a Backtest runs, so that I know a long run is still working.
7. As an F1 fan, I want a re-run to reuse the local FastF1 cache, so that only the first run is slow.
8. As an F1 fan, I want each race predicted using only information available before it, including history from previous seasons only, so that the Backtest can't cheat.

### Excluded Races

9. As an F1 fan, I want a race that isn't a Dry Race to become an Excluded Race instead of stopping the run, so that wet races don't block everything else.
10. As an F1 fan, I want a race whose prediction fails with an error to become an Excluded Race with the error recorded, so that one model gap doesn't stop the run.
11. As an F1 fan, I want a race whose data can't be loaded to become an Excluded Race, so that a download failure doesn't stop the run.
12. As an F1 fan, I want every Excluded Race listed with a clear reason category and detail, so that I can turn them into tickets.
13. As an F1 fan, I want the count of Excluded Races shown next to the scores, so that I know how much of the Regulation Era the score covers.

### Scores

14. As an F1 fan, I want a headline top-1 Strategy Match, pooled over scoreable drivers in green races, so that the main number measures what the model is trying to do rather than Safety Car luck.
15. As an F1 fan, I want a headline top-3 Strategy Match on the same basis, so that I can tell near misses from complete misses.
16. As an F1 fan, I want a headline Stop Window hit rate over actual stops in green races, so that I can judge Stop Windows separately from Strategies.
17. As an F1 fan, I want tied Candidate Strategies to keep their split credit in every total, so that the Backtest is fair in the same way the single-race comparison is.
18. As an F1 fan, I want a race-averaged version of each headline score, so that I can see whether a few big races dominate the pooled number.
19. As an F1 fan, I want the same scores for Neutralised Races on their own, so that I can see how much Safety Cars hurt.
20. As an F1 fan, I want an all-races figure combining green and Neutralised Races, so that I have an end-to-end view too.
21. As an F1 fan, I want the scores broken down by season, so that I can see whether the model is better in some years.
22. As an F1 fan, I want the scores broken down by circuit, so that I can find circuits the model handles badly (like Las Vegas).
23. As an F1 fan, I want the scores broken down by sprint vs conventional weekends, so that I can see whether the thinner practice data on sprint weekends costs accuracy.
24. As an F1 fan, I want the Tuning Seasons and the Held-out Season reported side by side, so that once tuning exists I can see whether it generalises.
25. As an F1 fan, I want every score shown with its numerator and denominator as well as a percentage, so that small samples are obvious.
26. As an F1 fan, I want each race's own summary kept in the Backtest Result, so that I can see which races drove the totals.

### Degradation and Pit Loss sources

27. As an F1 fan, I want Historical Degradation drawn only from races in the same Regulation Era, so that pre-2022 cars and tyres never feed predictions (ADR-0004).
28. As an F1 fan, I want 2022 races to be predicted even though they have no same-era history, so that the first season of the era is part of the Backtest.
29. As an F1 fan, I want Pit Loss for a race to be allowed to use seasons from before the Regulation Era, so that 2022 races have a measured Pit Loss (ADR-0004 exception).
30. As an F1 fan, I want a circuit with no previous race at all to get a Pit Loss estimated from its pit lane length and speed limit, so that new circuits aren't Excluded Races.
31. As an F1 fan, I want an estimated Pit Loss flagged in that race's output and in the Backtest Result, so that I know which races rest on an estimate.
32. As an F1 fan, I want the Backtest Result to count how often each Degradation source was used, so that I can see how much the model leans on fallbacks.

### Saving and comparing results

33. As an F1 fan, I want each full run saved as a Backtest Result in the repo, so that later changes can be compared against it.
34. As an F1 fan, I want to give each run a short label, so that I can tell runs apart ("baseline", "circuit-tendency").
35. As an F1 fan, I want the Backtest Result to record the settings used, so that I know exactly what produced the numbers.
36. As an F1 fan, I want the Backtest Result to record the code version, and whether there were uncommitted changes, so that a result can be traced back to the code that made it.
37. As an F1 fan, I want the Backtest Result to record which races were in scope and when the run happened, so that two results can be checked for like-for-like scope.
38. As an F1 fan, I want a readable summary file next to the data file, so that I can read the result on GitHub without running anything.
39. As an F1 fan, I want a command that compares two Backtest Results, so that I can see whether a change helped.
40. As an F1 fan, I want the comparison to show the change in every headline score and every breakdown, so that I can see where a change helped and where it hurt.
41. As an F1 fan, I want the comparison to list the races that moved most in each direction, so that I can explain the change.
42. As an F1 fan, I want the comparison to warn when the two results cover different races or Excluded Races, so that I don't mistake a scope change for a model change.
43. As an F1 fan, I want Smoke Set runs not saved as Backtest Results by default, so that the results folder only holds full runs worth comparing against.

### Running where the data is

44. As an F1 fan, I want full Backtests to run on my laptop, where the FastF1 cache persists, so that repeat runs are fast.
45. As a developer, I want the Smoke Set to run in a cloud session, so that every session can check the whole pipeline end to end.
46. As a developer, I want to know how long a cold download of one race weekend takes, so that I know what a first full run costs.
47. As a developer, I want the README to explain how to run a full Backtest, the Smoke Set, and a comparison, so that I don't have to remember the commands.

## Implementation Decisions

- **Scope.** Every race weekend in the 2022–2025 seasons. A round that was called off (2023 Emilia Romagna) never took place, so it is not a race weekend: season listings leave it out and loading it directly raises a clear "cancelled" error (ticket 29). Wet and mixed-condition races are refused by the existing predictor and become Excluded Races; handling them is a later version. 2026 races join once there is enough same-era history (ADR-0004); this spec does not add them.
- **No leakage.** Each race is predicted exactly as a single race is today: `predict()` reads only pre-race information, and every historical input comes from earlier seasons. The Backtest never passes one race's outcome into another race's prediction.
- **Backtest module (new, deep).** One public call takes: the list of race weekends to run (season + event), a loader function that turns one of them into a race weekend description, and settings. It returns a Backtest Result. For each race it loads, predicts and compares using the existing `predict()` and `compare()` unchanged. Any refusal, error during prediction, or failure to load becomes an Excluded Race and the loop continues. The loader is passed in, as the command already does with its injectable `load`, so tests run on hand-built weekends.
- **Backtest Result (new data shape).** Holds:
  - run metadata: label, date and time, settings used, code version (commit plus an uncommitted-changes flag), seasons in scope, Held-out Season
  - per race: season, event, circuit, sprint or conventional, Neutralised Race or green, Pit Loss and whether it was estimated, Degradation sources used, and that race's summary (scoreable drivers, top-1 and top-3 credit, Stop Window hits and actual stops)
  - Excluded Races: season, event, a reason category (not a Dry Race / prediction failed / data unavailable), and the detail message
  - aggregates computed from the per-race records:
    - the green-race headline, pooled over scoreable drivers: top-1, top-3 and Stop Window hits
    - the race-averaged versions of those
    - Neutralised-only and all-races figures
    - breakdowns by season, by circuit, by sprint vs conventional, and Tuning Seasons vs Held-out Season
    - Degradation source counts and the Excluded Race count

  Aggregates should be derivable from the per-race records, so a comparison or a future report can recompute them.
- **Headline basis.** Pooled credit over scoreable drivers in green races. Top-1 and top-3 use ticket 14's split tie credit. Stop Window hits are counted over actual stops, matching the single-race summary. Percentages always come with their numerator and denominator.
- **Tuning Seasons and Held-out Season.** 2022–2024 are the Tuning Seasons and 2025 is the Held-out Season. They are recorded in the Backtest Result as settings of the run, not hard-coded into the scoring, so the tuning spec can reuse them.
- **Saving.** A full run writes its Backtest Result to a results folder in the repo: a machine-readable data file, plus a readable summary generated from it, both named by date and label. Smoke Set runs print their result but don't save unless asked. Results hold scores only, never raw timing data, so they stay small enough to commit.
- **Comparison.** A second public call takes two Backtest Results and returns their differences: every headline score and breakdown (before, after, change), the races whose credit moved most in each direction, and warnings when the in-scope races, Excluded Races or Held-out Season differ, or when a race scored in both has different Data Quality Warnings.
- **Commands.** The existing command gains a Backtest mode (all four seasons by default; chosen seasons; the Smoke Set; an optional label) and a compare mode (two saved Backtest Results). The single-race mode is unchanged. Formatting lives in the package, as the single-race report does, so the commands and any notebook print the same thing.
- **Smoke Set.** Singapore 2024 (reference), Monza 2024 (Historical Degradation), Baku 2024 (used-set fallback), Austin 2024 (sprint), Jeddah 2024 (Neutralised Race), plus Spain 2022 (first season of the era, no same-era history). Spain 2022 was picked because Barcelona (`Catalunya`) has clean 2018–2021 pre-era history under one FastF1 `Location` string (so no alias is needed) and the 2022 race was green and dry under FastF1's TrackStatus, so it exercises the pre-era Pit Loss path (ADR-0004 exception, ticket 03) without becoming an Excluded Race or landing in the Neutralised bucket. Hungary 2022 was tried first but ran as a Neutralised Race under FastF1's TrackStatus.
- **Loader: listing a season.** The FastF1 adapter gains a way to list a season's race weekends (conventional and sprint, excluding testing), so the Backtest can build its in-scope list.
- **Loader: Regulation Era.** Historical inputs (Historical Degradation now, and the inputs Circuit Tendency will use) are drawn only from seasons in the same Regulation Era as the race. The era boundaries (2022–2025, then 2026 onward) are a single source of truth that the loader reads, not a scattered minimum-season number.
- **Loader: Pit Loss before the era.** Pit Loss uses same-era seasons at the circuit when there are any, exactly as today. Only when a circuit has no same-era race before the one being predicted (all of 2022, for example) does Pit Loss fall back to earlier seasons, 2018–2021, which FastF1's detailed data covers (ADR-0004 exception), recent seasons counting more. This keeps already-measured races, like Singapore 2024, unchanged.
- **Loader: estimated Pit Loss.** When a circuit has no previous race at all, Pit Loss is estimated from the pit lane's length and speed limit, plus a typical stationary time and an allowance for slowing into and accelerating out of the pit lane. FastF1 doesn't provide pit lane lengths, so they come from a small hand-maintained table covering only circuits that need it (e.g. Miami 2022 and other first-time venues found during implementation), filled from published figures with the source noted. The race weekend description records that Pit Loss was estimated, and the single-race report and the Backtest Result both show it. A circuit missing from the table, with no history either, is an Excluded Race with that reason.
- **Measuring download cost.** The first ticket measures how long one cold race-weekend download takes in a cloud session and on a cached run, and records it, so the README can say what a first full run costs.

## Testing Decisions

- **What makes a good test.** Test only external behaviour: what goes into the Backtest and comparison calls and what comes out. Don't assert on internal helpers. Internals should be free to change without breaking tests.
- **Seam 1 (main): run a Backtest.** Most tests go here, using small hand-built race weekend descriptions and a fake loader. Example scenarios:
  - The green headline excludes a Neutralised Race, and the Neutralised and all-races figures include it.
  - Pooled and race-averaged scores differ as expected when races have different numbers of scoreable drivers.
  - Tied split credit carries through to every total.
  - A refused (wet) race, a race whose prediction raises, and a race whose loader raises each become an Excluded Race with the right reason category, and the remaining races are still scored.
  - The season, circuit, sprint/conventional and Tuning Seasons vs Held-out Season breakdowns add up to the totals.
  - Degradation source counts and estimated-Pit-Loss flags are recorded per race.
  - Settings, label and seasons in scope are recorded.
  - One race's outcome never changes another race's prediction.
- **Seam 1b: saving and comparing.** Through the same public module:
  - A saved Backtest Result reads back identical.
  - The readable summary contains the headline figures.
  - Comparing two hand-built results reports each score change and the biggest-moving races.
  - Comparing results with different scope or Excluded Races raises a warning.
- **Seam 2 (existing, slow): the FastF1 loader.** A few slow real-data tests:
  - listing a season's race weekends returns the expected count with sprints marked
  - Historical Degradation for a 2023 race uses only 2022, and for a 2022 race uses nothing
  - Pit Loss for a 2022 race is measured from pre-2022 seasons
  - a first-time circuit gets an estimated, flagged Pit Loss
- **End to end (slow).** Running the Smoke Set produces a Backtest Result with no unexpected Excluded Races.
- **Prior art.** The single-race tests: hand-built weekends through `predict()` and `compare()`, the command tested with an injected `load` function, and slow tests marked `slow` against cached FastF1 data.

## Out of Scope

- Tuning settings (next spec; it will use the Tuning Seasons and never the Held-out Season).
- Circuit Tendency, Team Tendency and Situational Tendency, including breaking mirrored ties (ticket 09).
- Wet and mixed-condition races (later version; they remain Excluded Races).
- 2026 races (they join once enough same-era history exists).
- Live Predictions, Replay and real live timing.
- Fixing model gaps the Backtest reveals, such as Las Vegas track evolution or early Stop Windows (ticket 15). These become new tickets.
- A dashboard.
- Storing the FastF1 cache anywhere persistent for cloud sessions.

## Further Notes

- Domain vocabulary follows `CONTEXT.md`: Backtest, Backtest Result, Excluded Race, Held-out Season, Tuning Seasons, Smoke Set, Regulation Era, Neutralised Race, Strategy Match, Stop Window, Pit Loss, Historical Degradation.
- ADR-0004 sets the history rule and its Pit Loss exception; ADR-0003 sets the Degradation fallback chain the Backtest will exercise at scale.
- Known results from the single-race work that the first full run should reproduce for those races: Singapore 2024 top-1 6.5/18, top-3 13.75/18, Stop Window hits 3/20 (ticket 08). Differences there point to a Backtest or loader bug, not a model change.
- Ticket 15 (early Stop Windows) is parked waiting for this spec's first full Backtest Result. Re-triage it once one exists.
- Ticket 09 moves to the Circuit Tendency spec's folder when that spec is written.
