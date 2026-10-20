# 01: Tracer bullet: hand-built weekend → Strategy Predictions

**What to build:** Set up the project (Python 3.12, uv, pytest) and the plain, project-owned race weekend description, then make the main seam work end to end in its simplest form. Given a hand-built race weekend, every driver gets a Strategy Prediction: ranked Candidate Strategies with probabilities that sum to 100%. Deliberately simple internals:
- a Long Run is any run of consecutive laps on one Tyre Set
- Degradation is one field-wide rate per Compound with no fuel correction
- Pit Loss is supplied directly in the input
- Candidate Strategies are every legal 1–3 stop Strategy (at least two different dry Compounds)
- Simulated Race Time combines Degradation and Pit Loss over the race distance
- probabilities fall off with time gap from the fastest
- each stop gets a single best stop lap (Stop Windows come in 05)

The predictor refuses a weekend that isn't a Dry Race, and reads only pre-race information. See the spec (`../spec.md`) and use `CONTEXT.md` vocabulary throughout.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Project installs and tests run with uv and pytest on Python 3.12
- [x] A race weekend description exists, with pre-race information clearly separate from the race's actual Stints and neutralisation periods
- [x] One public call takes a race weekend description and returns a Strategy Prediction for every driver
- [x] Every Candidate Strategy has 1–3 stops and uses at least two different dry Compounds; single-Compound Strategies never appear
- [x] Each driver's probabilities sum to 100% and decrease as Simulated Race Time increases
- [x] Higher Degradation on a Compound shifts the favourite toward more stops (tested with hand-built weekends)
- [x] Each planned stop reports a best stop lap
- [x] Changing the race's actual Stints never changes the prediction (no-leakage test)
- [x] A weekend with Intermediate or Wet race laps is refused with a clear message
- [x] All tests go through the main seam using hand-built weekends; no internet needed

## Comments

**Implemented (2026-10-19).** Package `f1_strategy` under `src/`; tests in `tests/test_pre_race_prediction.py`, all through `predict(weekend, settings=None)`. Run with `uv sync && uv run pytest`.

- Race weekend description: `RaceWeekend(pre_race=PreRaceInfo(...), race=RaceOutcome(...))`. Pit Loss is `PreRaceInfo.pit_loss`.
- Simulated Race Time = race laps × base lap + Degradation cost (a Stint of L laps losing d s/lap costs d·L(L−1)/2) + Pit Loss per stop. Base lap is a placeholder (fastest Long Run lap in the field); it is identical across a driver's Candidate Strategies so it doesn't affect ranking.
- Probabilities: softmax over time gap to the fastest, scale set by `Settings.probability_scale_s` (default 5 s).
- Choices beyond the ticket's letter: a fitted Degradation below zero is clamped to 0; a dry Compound with no Long Runs takes the mean of the measured Compounds (proper field-average and Push Lap fallbacks come in 02/03).
- Known gap for later tickets: there is no Compound pace offset (Softs being quicker when fresh), so Softs only win on Degradation and rarely feature in favourites.
- The Dry Race guard reads the race's Stint Compounds only to decide whether to predict at all; the prediction itself reads only `pre_race`.

**From ticket 01 (2026-10-19).** Follow-up notes from this implementation have been filed where they'll be acted on: Compound pace and the base-pace placeholder (spec Open questions, 02), qualifying laps counting as Long Runs (03), Stints assumed to start on new tyres (04), mirrored-Strategy ties and how Stop Windows interact with stop-lap optimisation (05), retirements not being derivable from Stints (06), and Tyre Set identity in FastF1 (07). `done` has been added to `docs/agents/triage-labels.md`.
