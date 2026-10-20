# 08: End to end on a real 2024 race

**What to build:** One command, plus an example notebook, that takes a season and event name, loads that weekend, produces every driver's Pre-race Prediction, compares it with the actual race, and prints a per-driver table (top Candidate Strategies with probabilities and Stop Windows, actual Strategy, top-1/top-3 match, Stop Window hits) followed by the race summary. Run it on one recent, conventional 2024 Dry Race and record the result as the first "before" number for later comparison with Circuit Tendency (ADR-0001).

**Blocked by:** 03 (Long Run and Push Lap recognition), 04 (Remaining Sets), 06 (Comparing predictions with the actual race), 07 (FastF1 weekend loader)

**Status:** ready-for-agent

- [ ] One command runs a full prediction and comparison for a named 2024 race
- [ ] The output table shows, per driver, the top Candidate Strategies with probabilities and Stop Windows, the actual Strategy, and match results
- [ ] The race summary is printed
- [ ] An example notebook does the same and is runnable top to bottom
- [ ] Asking for a non-Dry Race gives the clear refusal message
- [ ] The chosen race and its summary numbers are recorded in this ticket under a Results heading
