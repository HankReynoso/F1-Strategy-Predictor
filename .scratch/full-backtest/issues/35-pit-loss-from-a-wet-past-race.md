# 35: Pit Loss measured from a wet past race looks inflated

**What to build:** 2024 Emilia Romagna scores (since ticket 30) with a Pit Loss of 52.1 s measured from 2022 Imola alone. 2022 Imola was not a Dry Race (an Excluded Race in the baseline, race laps on Intermediate), and its stops were mostly Intermediate-to-slick changes on a drying track. The in-lap and out-lap against the driver's median lap then measure the conditions as much as the pit lane. Ticket 29 reported 32.78 s for 2025 Imola from (2022, 2024) at season weights 0.25 and 1. Working back from that gives about 28 s for 2024 and about 52 s for 2022, so the 2022 sample is roughly twice the 2024 one at the same pit lane. Decide whether a past race that isn't a Dry Race (or a stop that changes between wet and dry Compounds) should contribute Pit Loss samples at all, and record the rule.

**Blocked by:** None (can start immediately)

**Status:** needs-triage

**Category:** bug

## Comments

Found during ticket 30, when 2024 Imola loaded for the first time. The 52.1 s is inside the existing `10 < loss < 60` clip, so nothing flags it. Check which other scored races take Pit Loss from a past race that is an Excluded Race for not being a Dry Race (2022 Monaco, Singapore, Suzuka; 2023 Monaco, Zandvoort; 2024 Montréal, Silverstone, São Paulo; 2025 Melbourne, Silverstone, Spa).

- [ ] The Pit Loss samples from each non-Dry past race in the era are listed next to the same circuit's dry samples
- [ ] A recorded rule for wet-race or wet-to-dry-stop samples, with fixture tests
- [ ] Smoke Set numbers re-checked; any race whose Pit Loss moves is listed
