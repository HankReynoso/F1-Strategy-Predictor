# 19: ADR for the per-season data-source policy

**What to build:** `docs/adr/0006-per-season-data-source.md`, recording the decision to use OpenF1 for 2023+ and FastF1 for 2018–2022, the licence implications (OpenF1 CC BY-NC-SA 4.0), the known 2018–2020 pre-era Pit Loss hole, and the FastF1 3.9 F1 TV path as a reversible future option. The ADR itself is hard to reverse once baselines are published against it, which is why this is an ADR and not just a code comment.

**Blocked by:** None, but should land before (or with) ticket 20.

**Status:** needs-triage

**Category:** docs

Context and reasoning come from [`openf1-findings.md`](../openf1-findings.md) ("Recommendation" and "Does it still give one consistent weekend description?"). Follow-up from [ticket 18](18-check-openf1-as-second-data-source.md).
