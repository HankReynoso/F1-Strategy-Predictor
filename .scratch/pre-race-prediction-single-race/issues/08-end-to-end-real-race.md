# 08: End to end on a real 2024 race

**What to build:** One command, plus an example notebook, that takes a season and event name, loads that weekend, produces every driver's Pre-race Prediction, compares it with the actual race, and prints a per-driver table (top Candidate Strategies with probabilities and Stop Windows, actual Strategy, top-1/top-3 match, Stop Window hits) followed by the race summary. Run it on one recent, conventional 2024 Dry Race and record the result as the first "before" number for later comparison with Circuit Tendency (ADR-0001).

**Blocked by:** 03 (Long Run and Push Lap recognition), 04 (Remaining Sets), 06 (Comparing predictions with the actual race), 07 (FastF1 weekend loader)

**Status:** done

- [x] One command runs a full prediction and comparison for a named 2024 race
- [x] The output table shows, per driver, the top Candidate Strategies with probabilities and Stop Windows, the actual Strategy, and match results
- [x] The race summary is printed
- [x] An example notebook does the same and is runnable top to bottom
- [x] Asking for a non-Dry Race gives the clear refusal message
- [x] The chosen race and its summary numbers are recorded in this ticket under a Results heading

## Results

**Race: 2024 Singapore Grand Prix** (Marina Bay, round 18, 22 Sep 2024). Conventional weekend, Dry Race, not a Neutralised Race. 62 laps. Pit Loss 30.6 s, measured from Singapore 2022 and 2023 (see the data note below). Monza 2024 can't be predicted at all: see "Why not Monza".

**Settings used:** all defaults, untuned: `probability_scale_s=5.0`, `plausible_margin_s=20.0`, `stop_window_margin_s=1.0`, `fuel_effect_s_per_lap=0.03`, `min_long_run_length=4`, `long_run_slow_lap_margin_s=3.0`, `push_lap_fast_margin_s=1.0`. Tyre Allocation is the FIA default (ADR-0002).

**Command:** `uv run f1-strategy 2024 "Singapore Grand Prix"` (the notebook `notebooks/end_to_end_real_race.ipynb` prints the same).

### Race summary (the "before" number)

| | |
|---|---|
| Scoreable drivers | 7 of 20 |
| Top-1 Strategy Match | 2/7 (29%) |
| Top-3 Strategy Match | 6/7 (86%) |
| Stop Window hits | 1/7 actual stops (14%) |
| Neutralised Race | no |

### Every driver's top prediction vs actual Strategy

"Rank" is where the actual Strategy sits in the driver's Strategy Prediction (— = not Plausible, so absent). "Tied" counts other Candidate Strategies with exactly the same probability as the top one. Drivers marked *unscoreable* by the scorer are shown for completeness; 11 of them were lapped finishers, not retirements (see Misses, point 1).

| Driver | Finish | Top prediction (prob.) | Tied | Stop Window | Actual Strategy (stop laps) | Rank | Scored? | Top-1 / Top-3 / Window |
|---|---|---|---|---|---|---|---|---|
| NOR | 1 | 1-stop: S → H (32%) | 1 | 5–9 | 1-stop: M → H (30) | 3 | yes | no / yes / 0/1 |
| VER | 2 | 1-stop: M → H (50%) | 1 | 11–16 | 1-stop: M → H (29) | 1 | yes | yes / yes / 0/1 |
| PIA | 3 | 1-stop: M → H (50%) | 1 | 3–6 | 1-stop: M → H (38) | 1 | yes | yes / yes / 0/1 |
| RUS | 4 | 1-stop: S → M (17%) | 5 | 1–2 | 1-stop: M → H (27) | 4 | yes | no / no / 1/1 |
| LEC | 5 | 1-stop: S → H (25%) | 3 | 1–2 | 1-stop: M → H (36) | 2 | yes | no / yes / 0/1 |
| HAM | 6 | 1-stop: S → M (17%) | 5 | 1–2 | 1-stop: S → H (17) | 2 | yes | no / yes / 0/1 |
| SAI | 7 | 1-stop: S → H (25%) | 3 | 1–2 | 1-stop: M → H (13) | 2 | yes | no / yes / 0/1 |
| ALO | 8, lapped | 1-stop: M → H (39%) | 1 | 16–21 | 1-stop: M → H (25) | 1 | unscoreable | — |
| HUL | 9, lapped | 1-stop: M → H (50%) | 1 | 22–27 | 1-stop: M → H (29) | 1 | unscoreable | — |
| PER | 10, lapped | 1-stop: M → H (47%) | 1 | 11–16 | 1-stop: M → H (28) | 1 | unscoreable | — |
| COL | 11, lapped | 1-stop: S → M (25%) | 3 | 1–2 | 1-stop: M → H (29) | 3 | unscoreable | — |
| TSU | 12, lapped | 1-stop: M → H (50%) | 1 | 31–36 | 1-stop: M → S (33) | — | unscoreable | — |
| OCO | 13, lapped | 1-stop: M → H (38%) | 1 | 7–12 | 1-stop: M → H (29) | 1 | unscoreable | — |
| STR | 14, lapped | 1-stop: M → H (37%) | 1 | 16–21 | 1-stop: H → M (26) | 2 | unscoreable | — |
| ZHO | 15, lapped | 1-stop: S → M (17%) | 5 | 1–2 | 1-stop: H → M (34) | 6 | unscoreable | — |
| BOT | 16, lapped | 1-stop: S → M (17%) | 5 | 1–2 | 1-stop: H → M (33) | 6 | unscoreable | — |
| GAS | 17, lapped | 1-stop: M → H (38%) | 1 | 7–12 | 1-stop: M → S (37) | — | unscoreable | — |
| RIC | 18, lapped | 1-stop: S → M (25%) | 3 | 58–61 | 3-stop: S → M → S → S (10, 46, 58) | — | unscoreable | — |
| MAG | retired lap 57 | 1-stop: S → H (27%) | 1 | 23–30 | 2-stop: H → M → S (28, 49) | 10 | unscoreable | — |
| ALB | retired lap 15 | 1-stop: S → M (25%) | 3 | 1–2 | 1-stop: M → H (11) | 3 | unscoreable | — |

The full per-driver table with the top 3 Candidate Strategies each is in the executed notebook.

### What drove the misses

Settings were not tuned to improve any of this. The numbers above are the honest "before".

1. **Lapped finishers count as retired, so 13 of 20 drivers are unscoreable.** Ticket 06 infers retirement from the last Stint ending before the race distance, and the loader never got the finishing status ticket 06 asked ticket 07 for. At Singapore only the top 7 finished on the lead lap; 11 classified finishers were lapped. Counting every classified finisher (a diagnostic run outside the code using FastF1's results) gives top-1 6/19, top-3 12/19 and Stop Window hits 4/22. → ticket 10.
2. **Every top-1 match is a mirrored tie decided by enumeration order.** Both scored top-1 matches (VER, PIA), and all six among classified finishers, are M → H tied exactly with H → M at the same probability. Ticket 09 accepts the 50/50 split, but `predict()` sorts stably over Strategies generated in S, M, H order, so the softer-first mirror is always ranked first and the scorer counts it as the top pick. That happens to match what most teams do, so it flatters the "before" top-1 number, and the gain Circuit Tendency shows will be understated by the same amount. With ties credited fairly (half a match each), top-1 would be 1/7 among scored drivers. → ticket 14.
3. **Zero Degradation produces token Stints, degenerate windows and many-way ties.** Long Run fits clamp at 0. Mercedes (Medium and Hard), Ferrari (Hard), Williams (Medium), Sauber (Medium and Hard) and RB (Soft) all came out at exactly 0. With no Compound pace and no minimum Stint length, running a 1–2 lap Stint on the other Compound is free, so the top picks become things like "S → M, stop on lap 1–2", tied 4–6 ways (RUS, HAM, ZHO, BOT, COL, ALB). The clamped zeros also drag the field average down, so teams on the field-average Hard got 0.043 s/lap. The single scored Stop Window hit (RUS) is one of these degenerate windows (laps 1–61). → ticket 13.
4. **Stop Windows are far too early.** Where the actual Strategy was predicted, its window sits 15–30 laps before the real stop: PIA lap 3–6 vs 38, VER 11–16 vs 29, NOR 3–6 vs 30 on M → H. The Medium Degradation fitted from practice (McLaren 0.59 s/lap, Ferrari 0.29 from Push Laps) is many times the Hard's, so the model shortens the Medium Stint. Teams in the race went long on the Medium. Likely contributors: short and noisy practice runs, track evolution through FP2 masking or exaggerating wear, linear Degradation, and the fuel effect default. Some of this is tuning (out of scope here); some is modelling. → ticket 15.
5. **Not Plausible.** TSU and GAS ran M → S, which no prediction had within the Plausible margin; Softs only win on low Degradation without Compound pace (spec Open questions). RIC's S → S end of race was a fastest-lap stop, a Deviation the model can't predict.

### Why not Monza (and what else was screened)

The ticket and the user's brief preferred Monza 2024, but `predict()` refuses it: "No Long Runs or Push Laps on Hard across the field". Only Tsunoda ran Hards in practice (three short FP1 Stints that give one Push Lap per set or a 3-lap run below the 4-lap minimum; the five FP3 Hard laps are all in/out laps). Yet all 20 starters raced the Hard. The user chose to switch race and file the gap rather than change the model in this ticket.

Recent conventional 2024 races screened with default settings:

| Race | Result |
|---|---|
| Abu Dhabi | refused: no Hard data in practice (VSC laps 2–3) |
| Las Vegas | refused: no Hard data in practice |
| Mexico City | runs, but Neutralised Race (SC laps 1–6) |
| Singapore | runs, green: **chosen** (most recent green conventional race that runs) |
| Azerbaijan | crashes: Alonso has no runnable Strategy under new-sets-only Remaining Sets |
| Netherlands | runs, green (top-1 4/8, top-3 4/8, Stop Window hits 0) |
| Italy (Monza) | refused: no Hard data in practice |

→ tickets 11 (no Degradation for a Compound nobody ran) and 12 (no runnable Strategy crash).

### Data note

`livetiming.formula1.com` still returns 403 for 2022 data (2023 and 2024 return 200). FastF1 now falls back by itself to `livetiming-mirror.fastf1.dev`, which this environment can reach (it was proxy-denied when ticket 07 ran). So 2022 Singapore loaded normally with no workaround: Pit Loss is 30.59 s with 2022 and 2023, against 28.31 s from 2023 alone. The Monza 2022 cache from the `fastf1-cache-2022` branch was restored as asked before starting, but isn't needed for Singapore.

## Implementation notes

**What was built.**
- `src/f1_strategy/report.py`: `strategy_label(compounds)` ("1-stop: M → H"), `format_table(predictions, comparison)` (one block per driver: top 3 Candidate Strategies with probability and Stop Windows; on the driver's first line the actual Strategy with stop laps, top-1, top-3 and Stop Window hits, or "unscoreable"), `format_summary(comparison)` (scoreable drivers, top-1, top-3, Stop Window hits out of actual stops, Neutralised Race), and `format_header(pre_race, settings)` (race, laps, Pit Loss and every setting used).
- `src/f1_strategy/cli.py`: `main(argv, load=None)`, installed as the `f1-strategy` script (`uv run f1-strategy 2024 "Singapore Grand Prix"`). It loads the weekend, predicts, compares, then prints header, table and summary. A non-Dry Race prints the refusal to stderr and exits 2, with nothing on stdout. FastF1's INFO logging is turned down to warnings.
- `notebooks/end_to_end_real_race.ipynb`: the same steps cell by cell, a per-driver pandas DataFrame for exploring, and the refusal on Canada 2024. Committed with outputs.
- Tests: `tests/test_end_to_end_report.py` (10 tests, hand-built weekends through `predict` → `compare` → report calls and `main`) and `tests/test_example_notebook.py` (slow: executes the notebook top to bottom with nbclient). Dev dependencies `nbclient`, `nbformat` and `ipykernel` were added for it. Full suite: 70 passed.

**Decisions and alternatives rejected.**
- *Formatting lives in the package, not in the command.* Both the command and the notebook call the same `format_*` functions, so they print identical reports and the table is testable without FastF1. Rejected: formatting inside `cli.py`, which would have needed the notebook to duplicate it.
- *The command takes an injectable `load` function.* Tests pass a hand-built weekend instead of FastF1. Rejected: monkeypatching the loader module, which ties tests to an import path.
- *Settings are printed in the header* so every run records the exact settings behind its numbers, which the "before" comparison needs. No command-line flags for settings yet: tuning is out of scope and belongs to the Backtest.
- *Stop Window hits are shown out of actual stops,* not out of drivers, because a multi-stop driver has several stops to hit. Ticket 06's `RaceSummary` only counts hits, so the formatter sums the per-driver tuples for the denominator.
- *Refusal exit code 2, message on stderr.* It's a refusal, not a crash, so there's no traceback; stdout stays empty so a pipe never sees a half report.
- *Other errors are not caught.* The two crashes found (no Degradation for a Compound, no runnable Strategy) still raise. Catching a generic `ValueError` or `IndexError` in the command would hide model gaps; tickets 11 and 12 should give them proper handling.
- *Race choice.* Singapore 2024 instead of Monza 2024. Monza can't be predicted by the current model; the user chose to switch races and file the gap. Singapore is the most recent conventional, green Dry Race the pipeline runs on. Zandvoort was the alternative; Mexico City was rejected as a Neutralised Race.

**Deviations.**
- Race: Singapore 2024 instead of the preferred Monza 2024 (reasons above). The spec's "Default first race" now records this.
- The ticket asked for "a recent, conventional 2024 Dry Race"; Singapore is round 18 of 24 and fits.

**Spec changes.** "Default first race" now names Singapore 2024 and why Monza could not be used. The Project shape bullet names the `f1-strategy` command and the example notebook.

**CONTEXT.md / ADRs.** No new domain terms were introduced. The report uses existing glossary terms throughout. No ADR: the report format and command are easy to change and involved no hard-to-reverse trade-off.

**Open questions and follow-ups (new needs-triage tickets).**
- 10: Lapped finishers are scored as retired.
- 11: No Degradation estimate when nobody runs a Compound in practice (Monza, Abu Dhabi and Las Vegas 2024 refused).
- 12: `predict()` crashes when Remaining Sets leave a driver no runnable Strategy (Baku 2024, Alonso).
- 13: Zero Degradation produces token Stints, degenerate Stop Windows and many-way ties.
- 14: The scorer counts mirrored ties as top-1 by enumeration order.
- 15: Stop Windows are systematically early against the actual race.

**Review feedback given to the user.**
- The "before" number is weak evidence: 7 scoreable drivers, every top-1 match a coin-flip tie, and the one Stop Window hit degenerate. Tickets 10, 13 and 14 should land before it is used as the baseline for Circuit Tendency, otherwise the comparison measures scoring artefacts as much as the model.
- Ticket 11 matters for the Backtest: 3 of the 7 recent conventional 2024 races screened can't be predicted at all.
- The FastF1 mirror is now reachable. The `fastf1-cache-2022` branch sideload from ticket 07 is no longer needed, and the Backtest can draw on 2022 directly.

## Rerun after ticket 10 (2026-10-20)

Added separately from the original "before" record above; the "before" table and numbers are unchanged.

With lapped finishers now scored (ticket 10), rerunning `uv run f1-strategy 2024 "Singapore Grand Prix"` on the same settings and the same loader cache gives:

| | Before (above) | After ticket 10 |
|---|---|---|
| Scoreable drivers | 7 of 20 | 18 of 20 |
| Top-1 Strategy Match | 2/7 (29%) | 6/18 (33%) |
| Top-3 Strategy Match | 6/7 (86%) | 12/18 (67%) |
| Stop Window hits | 1/7 actual stops (14%) | 3/20 actual stops (15%) |
| Neutralised Race | no | no |

Who moved from unscoreable to scoreable: the 11 lapped classified finishers (ALO, HUL, PER, COL, TSU, OCO, STR, ZHO, BOT, GAS, RIC). MAG stays unscoreable per ticket 10's triage decision (retired lap 57 of 62, classified 19th but did not take the chequered flag); ALB stays unscoreable (retired lap 15). The 18 scoreable total is the 19-driver official classification minus MAG.

Both tops-1 matches held, and six more showed up among the lapped finishers (every M → H mirror), which is why top-1 only rises from 29% to 33% despite nearly tripling the denominator. The ticket-08 note's diagnostic forecast (top-1 6/19, top-3 12/19, Stop Window hits 4/22) is close for top-1 and top-3 but on different denominators; it counted MAG as a finisher and included Ricciardo's three stops in the window-hit denominator the same way we do.

Takeaway for the baseline: ticket 10 fixes the single biggest hole in the "before" number, but the top-1 figure is still dominated by mirrored-tie enumeration order (ticket 14) and the Stop Window hits by degenerate token-Stint windows (ticket 13), both of which need to land before this is used as the Circuit Tendency baseline.

## Rerun after ticket 13 (2026-10-20)

Added separately from both the original "before" record and the ticket-10 rerun above; neither is edited. Ticket 13 (shrink team Degradation toward the field average instead of clamping to zero, and enforce a minimum race Stint length) was built on top of ticket 10. Rerunning `uv run f1-strategy 2024 "Singapore Grand Prix"` with its new defaults (`degradation_shrinkage_laps=4.0`, `min_stint_length=5`; every other setting unchanged) gives:

| | Before (original) | After ticket 10 | After ticket 13 |
|---|---|---|---|
| Scoreable drivers | 7 of 20 | 18 of 20 | 18 of 20 |
| Top-1 Strategy Match | 2/7 (29%) | 6/18 (33%) | 10/18 (56%) |
| Top-3 Strategy Match | 6/7 (86%) | 12/18 (67%) | 14/18 (78%) |
| Stop Window hits | 1/7 (14%) | 3/20 (15%) | 3/20 (15%) |
| Neutralised Race | no | no | no |

Who moved: among the 18 scored drivers, four more now get the actual Strategy as their top pick — RUS, LEC, HAM and SAI used to tie 3–6 ways on a degenerate "S → M, stop on lap 1–2" favourite, and now top-pick M → H outright; two further drivers' top-3 (STR, ZHO) picks up the actual Strategy because the mirrored M → H is no longer displaced by token Strategies. HAM is the one scored driver whose actual Strategy (S → H) sits outside the top 3; without Compound pace (spec Open questions) the model still never ranks a Soft-first strategy highly on a Singapore-like race. Stop Window hits are unchanged at 3/20 — ticket 15 is the one about Stop Windows landing too early.

Who did NOT move: VER, PIA (already on M → H in the before column) keep their top-1; NOR still misses top-1 by ranking S → H ahead of M → H by a sliver (same mirrored S/H pairs problem); TSU, GAS (actual M → S), RIC (3-stop ending S → S), ALB (DNF, unscoreable), MAG (unscoreable per ticket 10).

What the two new settings each contributed:

- **Shrinkage (no more clamp to zero).** The six Singapore teams whose fits previously clamped to exactly zero (Mercedes M/H, Ferrari H, Williams M, Sauber M/H, RB S) now receive a non-zero shrunk rate instead of a zero. The "stop on lap 1–2" tie disappears, which flips four scored drivers' top picks to M → H. This is where the top-1 lift from 33% → 56% comes from.
- **Minimum Stint length = 5.** No Candidate Strategy now contains a Stint shorter than 5 laps, and no Stop Window begins before lap 5 or past `race_laps − 5 = 57`. The lap 1–2 Stop Windows in the previous records are gone (narrowest Stop Windows are now 5–5 or 5–7). RUS's degenerate 1–61 Stop Window shrinks to 5–57; the one Stop Window hit from the before record (RUS's actual lap 27) still counts.

Residual oddities still visible: on teams whose Degradation is still uniformly flat across all Compounds after shrinkage (Mercedes, Sauber, Williams's RUS/HAM/COL/ALB rows), 1-stop Stop Windows span the full feasible range (laps 5–57). This is honest — the simulator sees no preference when every Compound has the same rate. The underlying cause is still Compound pace (spec Open questions); ticket 15 is the one tracking Stop Windows systematically.

Settings were not tuned to improve any of this. The defaults are reasoned in ticket 13's Implementation notes (shrinkage anchored on `min_long_run_length = 4`; minimum Stint length conservative lower bound at 5 laps) and were not revisited after this run.

Takeaway for the baseline: ticket 13 lifts top-1 Strategy Match from 33% to 56% and top-3 from 67% to 78%, both without touching Stop Window accuracy (which still needs ticket 15). Combined with ticket 10's lapped-finisher fix, this is a materially stronger "before" number for Circuit Tendency than the original record, though ticket 14 (mirrored-tie enumeration order) will shift it again.
