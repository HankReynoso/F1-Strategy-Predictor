# 09: First full Backtest baseline

**What to build:** Run the full 2022–2025 Backtest on the laptop with default settings and save it as the "baseline" Backtest Result. Then, in a session, analyse it: check Singapore 2024 matches its known scores, explain the headline and the weakest circuits, turn Excluded Races and clear model gaps into new needs-triage tickets, and re-triage ticket 15 (early Stop Windows) of the previous spec with the full-Backtest evidence.

**Blocked by:** 01–08, 16 (Cross-season Location aliases)

**Status:** ready-for-human

Why human: the full run needs the persistent FastF1 cache on the user's laptop; cloud sessions only run the Smoke Set. The analysis afterwards can be done by an agent.

- [ ] The full 2022–2025 Backtest runs on the laptop and its "baseline" Backtest Result is committed
- [ ] Singapore 2024 within it matches its known scores, or the difference is explained
- [ ] The headline, the Tuning Seasons vs Held-out Season split and the weakest circuits are summarised under a Results heading here
- [ ] Every Excluded Race reason category and each clear model gap has a needs-triage ticket
- [ ] Ticket 15 in `.scratch/pre-race-prediction-single-race/` is re-triaged with the full-Backtest evidence
