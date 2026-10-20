# 15: Stop Windows are systematically early against the actual race

**What to build:** Find out why predicted Stop Windows fall 15–30 laps before the real stops, and fix what's a modelling error rather than a tuning one.

**Blocked by:** Probably 13 (zero Degradation) and the full Backtest, to judge on more than one race

**Status:** needs-triage

- [ ] The cause is identified across several races, not just Singapore
- [ ] Modelling fixes are made through `predict()` tests; anything that's just a setting is left to Backtest tuning

## Comments

**From ticket 08 (2026-10-20).** Singapore 2024, where the actual Strategy was predicted: PIA M → H window 3–6 vs actual stop 38; VER 11–16 vs 29; NOR 3–6 vs 30; LEC 1–3 vs 36. Medium Degradation fitted from practice is many times the Hard's (McLaren 0.59 vs field-average Hard 0.043 s/lap; Ferrari's Medium 0.29 from Push Laps), so the model ends the Medium Stint early. In the race teams went long on the Medium. Candidates: short, noisy practice runs; track evolution during FP2; linear Degradation; the 0.03 s/lap fuel effect default; Push Lap fall-off overstating race wear.
