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

**Status:** ready-for-agent

- [ ] Project installs and tests run with uv and pytest on Python 3.12
- [ ] A race weekend description exists, with pre-race information clearly separate from the race's actual Stints and neutralisation periods
- [ ] One public call takes a race weekend description and returns a Strategy Prediction for every driver
- [ ] Every Candidate Strategy has 1–3 stops and uses at least two different dry Compounds; single-Compound Strategies never appear
- [ ] Each driver's probabilities sum to 100% and decrease as Simulated Race Time increases
- [ ] Higher Degradation on a Compound shifts the favourite toward more stops (tested with hand-built weekends)
- [ ] Each planned stop reports a best stop lap
- [ ] Changing the race's actual Stints never changes the prediction (no-leakage test)
- [ ] A weekend with Intermediate or Wet race laps is refused with a clear message
- [ ] All tests go through the main seam using hand-built weekends; no internet needed
