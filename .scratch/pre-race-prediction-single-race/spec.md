# Spec: Pre-race Prediction for a single race (pure simulation)

Status: ready-for-agent

## Problem Statement

Before an F1 race, I want to know which Strategies each driver is likely to be on: how many stops, which Compounds in which order, and roughly when they'll pit. The information to estimate this exists in the weekend's practice running and in past races, but working it out by hand from timing data is slow and inconsistent. I also have no way to tell whether my reasoning is any good, because I never check it against what drivers actually ran.

## Solution

A Python library that takes one race weekend and produces a Pre-race Prediction for every driver: a ranked set of Plausible Candidate Strategies, each with a probability and a Stop Window per stop. This first version is pure simulation. It finds Long Runs in practice, fits Degradation per Compound per team, measures Pit Loss for the circuit from past races, rules out Strategies a driver can't run with their Remaining Sets, estimates a Simulated Race Time for each Candidate Strategy, and turns the time gaps into probabilities.

For a past race, the library also compares the predictions with the Strategies drivers actually ran. It reports whether each driver's actual Strategy was the top pick or in the top 3 (Strategy Match), whether the actual stops fell inside the predicted Stop Windows, and whether the race was a Neutralised Race. I can run this from a notebook or a single command and see a table per driver.

This is the thin end-to-end slice that later specs build on: the full Backtest across 2022+ races, then Circuit Tendency (ADR-0001), then Team and Situational Tendencies, richer simulation, and Live Predictions via Replay.

## User Stories

### Running a prediction

1. As an F1 fan, I want to pick a past race weekend by season and event name, so that I can generate Pre-race Predictions for it.
2. As an F1 fan, I want a Strategy Prediction for every driver who started the race, so that I can see the whole field at once.
3. As an F1 fan, I want each driver's Candidate Strategies ranked from most to least likely, so that I can see the favourite at a glance.
4. As an F1 fan, I want each Candidate Strategy to carry a probability, so that I can tell a clear favourite from a close call.
5. As an F1 fan, I want each driver's probabilities to add up to 100%, so that the numbers are easy to interpret.
6. As an F1 fan, I want each Candidate Strategy shown as its stop count and Compound sequence (e.g. "1-stop: M → H"), so that it reads the way commentators describe strategies.
7. As an F1 fan, I want each planned stop to show a Stop Window (a lap range), so that I know roughly when to expect it.
8. As an F1 fan, I want only Plausible Candidate Strategies shown, so that the list isn't cluttered with options no team would choose.
9. As an F1 fan, I want to run a prediction from a notebook, so that I can explore and chart the results.
10. As an F1 fan, I want to run a prediction from a single command that prints a per-driver table, so that I can get answers quickly without opening a notebook.
11. As an F1 fan, I want the tool to tell me clearly when a race weekend isn't a Dry Race, so that I don't trust predictions outside the model's scope.

### Strategy rules

12. As an F1 fan, I want Candidate Strategies to include every legal option from 1 to 3 stops, so that no reasonable Strategy is missed before pruning.
13. As an F1 fan, I want Strategies that don't use at least two different dry Compounds excluded, so that predictions respect the Dry Race rule.
14. As an F1 fan, I want a driver's Remaining Sets worked out from the Tyre Sets they used in practice and qualifying, so that the tool knows what they can still run.
15. As an F1 fan, I want Candidate Strategies a driver can't run with their Remaining Sets excluded for that driver, so that teammates can get different predictions when their tyres differ.
16. As an F1 fan, I want Candidate Strategies whose Simulated Race Time is too far behind the fastest excluded, so that only Plausible Strategies remain.
17. As a developer, I want the Plausible margin to be a setting, so that it can be tuned later by Backtesting.

### Long Runs and Push Laps

18. As an F1 fan, I want Long Runs found automatically in practice data, so that I don't have to label sessions by hand.
19. As an F1 fan, I want a Long Run recognised as a run of consistently timed consecutive laps on one Tyre Set, so that it reflects race-pace running.
20. As an F1 fan, I want out-laps, in-laps and abnormally slow laps (traffic, mistakes) left out of Long Runs, so that they don't distort Degradation.
21. As an F1 fan, I want Push Laps recognised by their slow–fast–slow pattern and kept out of Long Runs, so that qualifying-style running doesn't look like race pace.
22. As an F1 fan, I want several Push Laps on the same Tyre Set grouped together, so that their fall-off can be used as a backup Degradation signal.
23. As an F1 fan, I want sprint race Stints treated as Long Runs on sprint weekends, so that the model has enough data when there's only one practice session.
24. As a developer, I want the minimum Long Run length and the consistency and slow-lap thresholds to be settings, so that they can be tuned by Backtesting.

### Degradation and the simulation

25. As an F1 fan, I want Degradation fitted per Compound per team, so that differences in how cars treat tyres show up in the predictions.
26. As an F1 fan, I want Long Run lap times corrected for fuel burn, so that Degradation isn't hidden by the car getting lighter.
27. As an F1 fan, I want a team's Push Lap fall-off used when it has no Long Runs on a Compound, so that the model uses the best evidence available for that team.
28. As an F1 fan, I want the field average Degradation used when a team has neither Long Runs nor Push Laps on a Compound, so that every Compound always has an estimate.
29. As an F1 fan, I want to see where each team's Degradation estimate came from (Long Runs, Push Laps, or field average), so that I know how much to trust it.
30. As an F1 fan, I want Pit Loss measured from previous seasons' races at the same circuit, so that the cost of a stop reflects that circuit.
31. As an F1 fan, I want each Candidate Strategy's Simulated Race Time to combine Degradation, fuel effect and Pit Loss over the race distance, so that the core trade-off of fresh tyres against time lost in the pits is captured.
32. As an F1 fan, I want each Stop Window to cover every stop lap whose Simulated Race Time is within a small margin of the best stop lap, so that flat trade-offs give wide windows and sharp ones give narrow windows.
33. As a developer, I want the Stop Window margin to be a setting, so that it can be tuned by Backtesting.
34. As an F1 fan, I want probabilities to fall off as a Candidate Strategy's Simulated Race Time gets further from the fastest, so that nearly-as-fast options stay plausible.
35. As a developer, I want how sharply probability falls off with time gap to be a setting, so that it can be tuned by Backtesting.

### Comparing with what happened

36. As an F1 fan, I want each driver's actual Strategy extracted from their race Stints, so that predictions can be scored.
37. As an F1 fan, I want to see whether each driver's actual Strategy was the top-ranked prediction, so that I know how often the favourite is right.
38. As an F1 fan, I want to see whether each driver's actual Strategy was in the top 3, so that I can tell near misses from complete misses.
39. As an F1 fan, I want Strategy Match judged on stop count and Compound sequence only, so that a stop a couple of laps early doesn't count as a wrong Strategy.
40. As an F1 fan, I want to see whether each actual stop fell inside the predicted Stop Window, scored separately from Strategy Match, so that I can judge window accuracy on its own.
41. As an F1 fan, I want the race marked as a Neutralised Race when it had a Safety Car or Virtual Safety Car period, so that I can tell model errors from unpredictable race events.
42. As an F1 fan, I want drivers who retired or never completed a stop marked as unscoreable, so that they don't count as wrong predictions.
43. As an F1 fan, I want a summary for the race (how many drivers had a top-1 match, a top-3 match, and Stop Window hits), so that I get one number for how the model did.

### Trust and correctness

44. As an F1 fan, I want Pre-race Predictions to use nothing from the race itself, so that comparisons with the actual result are honest.
45. As a developer, I want race-weekend data loaded once and cached locally, so that re-runs are fast and work offline.
46. As a developer, I want the prediction logic to work on a plain, project-owned description of a race weekend rather than FastF1's objects, so that it can be tested without the internet.

## Implementation Decisions

- **Overall approach.** This version is pure simulation. Probabilities come only from Simulated Race Time gaps. Circuit Tendency and the other tendencies from ADR-0001 come in later specs, so their effect on the Backtest score can be measured. The interface should leave room to multiply in a historical weight per Candidate Strategy later without changing callers.
- **Project shape.** A Python package (Python 3.12, managed with uv, tested with pytest) holds all logic. Notebooks and a small command-line entry point only call into the package.
- **Race weekend description (the main input).** A plain, project-owned data shape describing one weekend:
  - the circuit and season
  - the race length in laps
  - whether it's a sprint weekend
  - for every practice, sprint and qualifying session: per-driver laps (lap time, lap number, Tyre Set identity, Compound, tyre age, whether the set was new when fitted, pit in/out flags, and whether the lap was under a Safety Car or VSC)
  - each driver's team
  - the race's actual Stints and neutralisation periods, kept clearly separate from pre-race information
  - Pit Loss reference data from past races at the circuit

  The prediction step must only read pre-race information.
- **Modules (deep, with small interfaces):**
  - **Weekend loader (FastF1 adapter).** Turns a FastF1 race weekend (season + event) into the race weekend description, using FastF1's on-disk cache. It's the only module that knows about FastF1, and it's also where previous seasons' races at the circuit are read for Pit Loss.
  - **Run classifier.** Splits practice laps into Long Runs and Push Laps per driver and Tyre Set, using the consistency-based Long Run rule and the slow–fast–slow Push Lap pattern. Sprint race Stints become Long Runs.
  - **Degradation model.** Fuel-corrects Long Run laps and fits a per-lap Degradation rate per team per Compound. It falls back to the team's Push Lap fall-off, then the field average, and records which source each estimate came from.
  - **Pit Loss estimator.** Measures typical time lost per stop at the circuit from previous seasons' races.
  - **Tyre Allocation tracker.** Works out each driver's Remaining Sets (by Compound, new vs used) from sets used before the race.
  - **Strategy generator.** Enumerates legal Strategies (1–3 stops, at least two different dry Compounds) and drops those a driver can't run with their Remaining Sets.
  - **Race simulator.** Computes the Simulated Race Time for a Strategy and the best stop laps, and derives Stop Windows using the Stop Window margin. In this version, a driver's base pace doesn't affect the comparison between their own Candidate Strategies, so no car-pace model is needed.
  - **Predictor.** Orchestrates the steps above for every driver: applies the Plausible margin, turns time gaps into probabilities with a tunable sharpness setting, and returns one Strategy Prediction per driver.
  - **Scorer.** Extracts actual Strategies from race Stints and reports Strategy Match (top-1 and top-3), Stop Window hits, the Neutralised Race flag, unscoreable drivers, and a race summary.
- **Main public interface.** One call: race weekend description in, a Strategy Prediction per driver out. A second call takes those predictions plus the race's actual Stints and returns the comparison. All tunable settings (Plausible margin, Stop Window margin, probability sharpness, Long Run thresholds, fuel effect per lap) are passed in as one settings object with sensible defaults.
- **Scope guard.** If the race weekend isn't a Dry Race (any race lap on Intermediate or Wet), the predictor refuses with a clear message rather than producing predictions.
- **Default first race.** Develop against one recent, conventional (non-sprint) Dry Race from 2024, chosen by whoever implements this. Note which race was used.

## Testing Decisions

- **What makes a good test.** Test only external behaviour: what goes into the main interface and what comes out (which Candidate Strategies appear, their order, rough probabilities, Stop Windows, and comparison results). Don't test the internal modules individually or assert on intermediate values. Internals should be free to change without breaking tests.
- **Seam 1 (main seam): race weekend in → Strategy Predictions out.** Almost all tests go here, using small hand-built race weekend descriptions. Example scenarios:
  - A team with a clear Long Run on Mediums and Hards produces the expected favourite Strategy.
  - Heavier Degradation pushes the favourite from 1-stop toward 2-stop.
  - A driver with no new Hards left never gets a Hard-heavy Strategy, while their teammate does.
  - A single-Compound Strategy never appears.
  - Push Laps on a set don't count as a Long Run.
  - A Compound with no Long Runs uses Push Lap fall-off, then the field average, with the source reported.
  - A flat time trade-off gives a wider Stop Window than a sharp one.
  - Probabilities sum to 100% and fall as Simulated Race Time increases.
  - Changing the race's actual Stints never changes the Pre-race Prediction (no leakage).
  - A weekend with Intermediate laps in the race is refused.
- **Comparison tests, also through seam 1's public calls.** Hand-built actual Stints check top-1 and top-3 Strategy Match, Stop Window hits scored independently, the Neutralised Race flag, and unscoreable drivers.
- **Seam 2 (thin): FastF1 weekend → race weekend description.** A small number of tests load one real, cached 2024 race and check the description is sensible: all starters present, Tyre Sets and Compounds populated, race laps match the official distance, practice sessions included. These guard against FastF1 data quirks. They can be marked as slower tests and rely on the local FastF1 cache.
- **Prior art.** Ticket 01 set the pattern: `tests/test_pre_race_prediction.py` tests only through `predict()`, using the hand-built weekend helpers in `tests/weekend_builder.py`, with expected values worked out by hand in comments. Use the `tdd` skill's red-green-refactor approach at seam 1.

## Out of Scope

- The full Backtest across 2022+ seasons (next spec; it reuses this spec's predictor and scorer per race).
- Circuit Tendency, Team Tendency and Situational Tendency (later specs, per ADR-0001).
- Traffic, undercut and overcut effects in the simulation.
- Live Predictions, Replay, Remaining Strategies after a Deviation, and real live timing.
- Wet and mixed-condition races (refused, not predicted).
- A dashboard.
- Tuning the settings. Sensible defaults are enough here, and tuning happens once the Backtest exists.

## Further Notes

- Domain vocabulary follows `CONTEXT.md`. Use its terms (Strategy, Stint, Compound, Stop Window, Long Run, Push Lap, Remaining Sets, Pit Loss, Simulated Race Time, Plausible, Strategy Match, Neutralised Race) in code names, test names and output.
- ADR-0001 sets the direction: this spec is deliberately the simulation half only. Results from this version are the "before" number that Circuit Tendency will be measured against.
- FastF1 detailed timing and tyre data is available from 2018 onward. Pit Loss for the chosen race should draw on recent previous seasons at that circuit (2022+, current regulations), weighted toward recent seasons where enough data exists.

## Open questions

Raised while implementing ticket 01 (2026-10-19). Not yet decided.

- **Compound pace.** User story 31 defines Simulated Race Time from Degradation, fuel effect and Pit Loss only. It leaves out that softer Compounds are quicker when fresh. Without that, Softs only win on low Degradation and almost never appear as favourites, which will hurt Strategy Match. The term isn't in `CONTEXT.md` yet; if it's adopted, settle the name via `/domain-modeling`. Ticket 02 is the natural place to add it, since per-team fits produce a pace intercept per Compound.
- **Base pace placeholder.** Simulated Race Time includes race laps × the fastest Long Run lap in the field. It doesn't affect rankings (it's the same for all of a driver's Candidate Strategies) but means the absolute time isn't a real estimate. Fine until a car-pace model exists, which this spec rules out.
- **Mirrored Strategies tie.** M → H and H → M always have identical Simulated Race Times because nothing depends on Compound order. See ticket 05.
