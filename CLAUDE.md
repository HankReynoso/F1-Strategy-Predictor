# F1 Strategy Predictor

A data analytics tool that combines historical F1 data, weekend practice-session data, and live race data to predict which strategies drivers could be on. Built in Python on the FastF1 API.

## Recording work

Every session that writes or changes code leaves a written record in the repo, not just in chat. The chat reply to the user summarises the same record. A ticket is done only when every item below that applies is written alongside the code. Sessions don't commit or push: the user reviews and commits every change. End by listing the changed files and giving the exact `git add` and `git commit` commands for the user to run:

- **Ticket file**: tick the passing acceptance criteria, set `Status: done` (or leave it open and say why), and append an `## Implementation notes` section covering:
  - what was built
  - each decision made and the reasoning behind it, including alternatives rejected
  - every deviation from the ticket or spec, and why
  - open questions, known limitations and suggested follow-ups
  - any review feedback given to the user about the work
- **Spec**: when a decision changes what the spec says, update the spec and note the change in the ticket's implementation notes.
- **`CONTEXT.md`**: add or correct domain terms the work introduced or sharpened. Glossary entries only; reasoning belongs in the ticket.
- **`docs/adr/`**: record any decision that is hard to reverse, surprising without context, and the result of a real trade-off (see `docs/agents/domain.md`).
- **New tickets**: write follow-up work the session discovered as new ticket files in the same `issues/` folder, with `Status: needs-triage`.

## Choosing between options

Any comparison used to choose between modelling options, settings or rules is judged on the Tuning Seasons (2022–2024) only. Report the Held-out Season (2025) alongside, but never use it to decide, so it stays a fair test of the finished model. Record which seasons each decision was judged on.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix), recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
