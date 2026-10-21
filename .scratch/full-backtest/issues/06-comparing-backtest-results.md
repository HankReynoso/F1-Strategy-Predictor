# 06: Comparing two Backtest Results

**What to build:** A public call and a command compare mode take two saved Backtest Results and show the before, after and change for every headline score and breakdown; the races whose credit moved most in each direction; and warnings when the in-scope races, Excluded Races or Held-out Season differ between them. See `../spec.md`.

**Blocked by:** 05 (Saving Backtest Results)

**Status:** ready-for-agent

- [ ] Comparing two hand-built results reports every headline and breakdown change correctly
- [ ] The biggest-moving races in each direction are listed
- [ ] Different scope, Excluded Races or Held-out Season produce a clear warning
- [ ] The command's compare mode prints the comparison for two saved results
- [ ] Tests go through the public compare call
