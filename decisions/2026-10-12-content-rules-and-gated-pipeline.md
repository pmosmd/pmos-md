## Decision: PM-first editorial rules, and an issue pipeline where code renders and gates and the model only writes editorial JSON

The weekly issue is now made by `scripts/` (facts, render, gate) from a small model-written file, `data/issue-NNN.json`.
The model picks from verified facts and writes takeaways; it never writes HTML, never commits, and its job has
no write credentials. A second job re-runs facts, render and the gate and commits only if the gate passes.
Editorial policy moves into CLAUDE.md (PM-first lead slots, free-first Signal with dates and takeaways, a repo
watchlist in three lanes, an official-only MCP table, a weekly/monthly/quarterly cadence).

## Context: the weekly job went dark for two weeks, and a review of issues #32 to #41 showed the content drifting from the promise

- The scheduled job failed on Oct 4 and Oct 11, 2026 when the Anthropic API credit ran out. A run cost $2.17 to
  $3.41 over 70 to 89 turns, most of them mechanical (fetching links, reading metadata, formatting HTML).
- Content audit (80 Signal items, 10 spotlights): 8 of 10 spotlights went to two general agent projects;
  only 55% of Signal came from PM-native sources; 17 of 27 Lenny's and Pragmatic Engineer picks were paid-only
  with no label; two articles ran twice; the MCP table had a row linking to a 22-star list instead of a
  Productboard server and nothing for analytics, design or research; the repo list changed by 3 repos in 10
  issues and sorted PM-specific repos to the bottom; Signal rows carried no date or takeaway.
- The gates that caught earlier production failures were instructions in a prompt, not code.

## Alternatives considered

- **Keep the model editing HTML, tighten the prompt.** Cheapest to build. Rejected: the gates stay advisory,
  the archive the model must open grows about 10 KB a week, and richer rows (date, takeaway, paid tag) make
  hand-written HTML more error-prone.
- **A review gate (the model opens a PR).** Still rejected, as on Aug 8: it reintroduces the human dependency
  that caused the 16-week gap. Visibility comes instead from a receipt issue after every publish.
- **Full static generator with per-issue pages.** Better SEO per issue; larger change. Deferred: the archive
  split is triggered by size (about 300 KB, around February 2027), not by date.
- **Subscription (OAuth) token instead of an API key.** Blocked upstream (claude-code-action#1316).
- **Add Reforge / First Round Review as sources.** Both produced 0 of 80 picks; dropped, not added.

## Reasoning

Putting everything verifiable in code makes the known-bad patterns impossible by construction (titles, dates,
stars, UTM tags and counts cannot be mistyped by a model), and the gate can finally be non-negotiable because
the model cannot push. It also cuts the model's work from 70+ turns to reading one facts file and writing one
JSON file, which makes a run cheap enough that a small balance lasts months. The editorial rules answer the
audit directly: lanes and a repeat window fix the spotlight, a PM-native quota, free-first and paid tags fix
Signal, official-only fixes the MCP table, and a monthly and quarterly cadence gives the static shelves an owner.

## Trade-offs accepted

- About 1,500 lines of Python to maintain, with tests. New page formats need a renderer change, not a prompt tweak.
- The gate checks integrity (links, dates, parity, history, counts), not whether a takeaway is wise. Editorial
  judgement is still delegated to the model and will occasionally be wrong; the receipt makes that visible.
- `data/` and `scripts/` live in a public repo (kept off the site by `_config.yml`).
- Quality of discovery still depends on a human-readable README check by the model; keyword searches lie.
