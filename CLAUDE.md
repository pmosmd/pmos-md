# CLAUDE.md — pmos.md

Instructions for Claude Code working on this project. The weekly publisher reads **Editorial rules**
before it writes an issue.

## What this project is

`pmos.md` is a single-page static site, a weekly resource hub for product managers navigating AI.
Hosted on GitHub Pages at `https://pmos.md` via the `pmosmd/pmos-md` repo.

The promise: the PM stack is being rewritten weekly, and we keep track so the reader doesn't have to.
Every link, date and number on the page is machine-verified. Issues publish unattended every Sunday
with no human review (decision of Aug 8, 2026, see `decisions/`), so trust lives in the checks.

## File structure

```
/
├── index.html      — the current issue (single file). Regions between <!-- pmos:begin NAME -->
│                     and <!-- pmos:end NAME --> are generated; everything else is hand-written.
├── archive.html    — every past issue, append-only
├── feed.xml        — RSS feed, append-only
├── llms.txt        — AI agent discovery file
├── robots.txt, sitemap.xml
├── _config.yml     — keeps project files (scripts, data, docs) off the public site
├── data/
│   ├── repos.json      — the repo watchlist: lanes, descriptions, retired, rejected
│   ├── mcp.json        — the MCP table (official servers only)
│   ├── state.json      — when the monthly audit and quarterly review last ran
│   ├── issue-NNN.json  — what the model wrote for issue NNN (picks + editorial text)
│   └── stars-NNN.json  — star counts as published (baseline for the next issue)
├── scripts/        — the pipeline (Python, standard library only); schema in scripts/SCHEMA.md
├── tests/          — offline tests for the pipeline
├── decisions/      — decision log
├── .github/workflows/ — weekly-issue.yml (publisher), watchdog.yml (freshness), ci.yml (checks)
├── CNAME           — pmos.md (do not edit)
└── CLAUDE.md       — this file
```

## How an issue is made

Code decides, the model writes. The model picks from verified facts and writes short editorial text.
It never writes HTML, never fetches a number that the facts already hold, and never commits.

1. `scripts/should_publish.py` — **date-based idempotency**: publish only when the page's `data-updated`
   is older than the most recent Sunday on or before today (UTC). Never compare issue numbers: issue #33
   was published by a Monday test run, the next Sunday's real run computed the same ISO-week number, saw
   "#33 already published" and skipped, and the site went a full week stale. The issue number is the next
   integer after the highest in `archive.html`; there is no ISO-week label.
2. `scripts/facts.py` — fetches every feed in `scripts/sources.json`, opens every candidate page and reads
   its title, publish date (from page metadata), paywall flag and excerpt; reads stars, releases from the
   last 7 days and push dates from the GitHub API; works out spotlight rotation; lists discovery candidates.
3. The model writes `data/issue-NNN.json` (schema: `scripts/SCHEMA.md`). It picks URLs and repos that exist
   in the facts; titles, dates, stars, release tags, paid tags, counts and UTM tags are filled in by code.
4. `scripts/render.py` — writes the generated regions of `index.html` and prepends one new block to
   `archive.html` and one new item to `feed.xml`. Existing blocks are never touched.
5. `scripts/selfcheck.py` — the gate. Every check maps to a Known-bad pattern below. Nothing is committed
   unless it passes.
6. A second job with write access re-runs facts, render and the gate itself, then commits
   `issue #NN — week of MMM DD, YYYY` and posts a receipt. The model's job has no write credentials.

**Archive first.** Nothing is ever dropped. `archive.html` and `feed.xml` are append-only: never edit or
delete an existing issue block, even to fix an error. Corrections go in the *new* issue's `note`.

**By hand** (a Claude Code session): same pipeline. `python3 scripts/facts.py --out /tmp/facts.json`, write
`data/issue-NNN.json`, `python3 scripts/render.py --issue data/issue-NNN.json --facts /tmp/facts.json`,
`python3 scripts/selfcheck.py --facts /tmp/facts.json`, then open a PR and wait for approval. Use
`--rebuild N` on facts and `--replace` on render only for an issue that is not published yet.

## Editorial rules

The reader is a working PM adopting AI tools. A piece earns its place if, five minutes later, they would
do or know something different. Tone: direct, plain sentences, no marketing language, no superlatives, no
emoji in takeaways.

**Signal** (4 "this week" + 4 "also worth your time")
- Windows come from verified publish dates: this week = 0–7 days before the issue date, also worth your time
  = 8–30 days. Dates come from `article:published_time` / `datePublished` on the page, never from search
  rank, feed order or a homepage label. A link whose `date_confirmed` is false cannot be used.
- PM-first: at least 6 of 8 from `kind: pm` sources in `scripts/sources.json`; at most 2 from `ai` or
  `general`, and only if the piece changes what a PM does. At most 2 items from one source.
- Free first: at most 2 of 8 paid or part-paid. Paid items are tagged automatically from the page's own flag.
- Every item gets a takeaway of 40–240 characters, written only from what the page says (use
  `excerpt` or fetch the page). Say what to do or know. Do not copy the excerpt.
- No article is ever used twice (`used` in the facts). Corrections to history go in `note`.
- The editor's pick is never also in Signal.

**Editor's pick** (the hero card): one free, PM-native article from the last 7 days. `quote` paraphrases the
page in 60–320 characters; `why` says why it is the pick.

**Spotlight**: a repo from `data/repos.json` with a *stable* release in the last 7 days (pre-releases do not
count). Take the lane the facts suggest unless it has no eligible repo. No repo twice within 6 issues. It
must be usable by a PM in 30 minutes, not only by engineers. The paragraph says what the release changes for
a PM, grounded in the release notes or changelog.

**Repos** (a watchlist with news, not a popularity list)
- Three lanes: built for PMs, agent platforms PMs are adopting, project & product platforms. Within a lane,
  repos with news this week come first, then by stars.
- To be added: at least 1,000 stars, or `"emerging": true` with at least 200 stars, pushed in the last 30 days
  and PM-specific. Re-justify emerging repos at every monthly audit.
- Retire a repo with no push for 90 days unless it is flagged `canonical`. The gate blocks stale repos.
- News: only for stable releases from the last 7 days; the tag must match the facts. `text` continues
  "This week's <tag> (<date>) …" and must be grounded in the release notes. Skip the repo if you cannot
  explain the release.
- Read the README before adding anything from `candidate_repos`. Keyword matches lie ("PM" can mean
  Professional; "product management" can mean Product Information Management). Put rejects in `rejected`
  with a reason. "No new entrants this week" is a fine outcome; never pad.
- Star counts come from the GitHub API through the renderer.

**MCP for PMs**: vendor-official servers only, in workflow order, 6–12 rows, every link answering 200.
A community server is listed only when the vendor has none. Rewrite a row only after reading the vendor's page.

**Recommended**: the editor's shelf. The weekly publisher never edits it; change it only when the editor says so.

**Cadence**
- Weekly: Signal, editor's pick, spotlight, repo news.
- Monthly (the first issue of a month; the facts set `mode.repo_audit_due`): repo audit using the discovery
  candidates and stale warnings, then set `last_repo_audit` in `data/state.json`.
- Quarterly (the first issue in Jan, Apr, Jul, Oct; `mode.quarterly_review_due`): re-verify every MCP row,
  review `scripts/sources.json` (feeds alive, paywall mix, PM-native share), then set `last_quarterly_review`.
- A missed week is not backfilled; the next 30-day window covers it. Say so in `note`.

## Known-bad patterns to avoid

These have all shipped to production before. The gate checks for them.
- Star counts drifting from reality (issue #16 listed a 524-star repo as 4.3k and a 227k-star repo as 65k)
- `href="#"` placeholders reaching `feed.xml`
- Invented article URLs that 404 (two shipped in issue #16)
- Stale articles mislabeled as fresh (issue #32 shipped "this week" articles dated back to May, and a "this
  month" pick from March 2025)
- Mismatched heading tags (`<h2>` closed with `</h3>`) and skipped heading levels
- Issue-number-based idempotency colliding with a manual mid-week run (issue #33, above)
- Paywalled links presented as free: 17 of 27 Lenny's and Pragmatic Engineer picks in #35–#41 were
  paid-only and the page did not say so
- The same article published twice (#37 and #39, #36 and #39)
- A table row whose link does not go to the thing the row names (the Productboard MCP row pointed at a
  22-star list of servers)
- "This week" claims that outlive the week; release news is generated per issue from the facts
- Discovery keyword collisions (see Repos)
- A silent failure: the weekly job failed on Oct 4 and Oct 11, 2026 because the API credit ran out, and
  nothing flagged it for two weeks. The watchdog and the preflight exist for this.

## Operations

- **Credit balance too low** is the failure signature: the run dies in about half a second at $0, and GitHub
  hides the message unless `show_full_output` is on. `scripts/preflight.py` now names it in the failure
  issue. Fix: top up at console.anthropic.com. A normal run cost $2.17–$3.41 under the old design; the
  facts-first design should cost a fraction of that. To see a hidden error, put `show_full_output: true` on a
  throwaway branch and `workflow_dispatch` it. Never merge that; Actions logs on this public repo are public.
- **Watchdog** (`watchdog.yml`, Mondays): if the live page is older than the last Sunday, it opens a GitHub
  issue and re-dispatches the publisher once. It also covers GitHub switching off a scheduled workflow after
  60 days without repository activity.
- **Receipt**: each published issue posts a short closed GitHub issue listing what went out and how to revert.
- **OAuth token auth** does not work in Actions (anthropics/claude-code-action#1316); use `ANTHROPIC_API_KEY`.
- Never put a token in a remote URL, a URL parameter, a commit or a log.

## Design rules

- `index.html` stays a single file; do not split its CSS/JS out
- `archive.html` is the one additional page; it carries its own inline styles (a trimmed subset of the same tokens)
- JetBrains Mono throughout; do not introduce other fonts
- Markdown visual syntax (##, >, ---, -, code) must stay as design elements
- Max width 840px, monospace, minimal
- Use CSS variables for colors; do not hardcode colors
- Generated regions are edited in `scripts/render.py` (templates), not in `index.html`

## Analytics

GoatCounter at `https://pmosmd.goatcounter.com`
Script tag in `<head>`; do not remove or change.

## Deploy

Push to `main` branch of `pmosmd/pmos-md`. GitHub Pages builds with Jekyll; `_config.yml` keeps project
files off the site. Site is live at `https://pmos.md` within ~60 seconds. Outbound content links carry
`?utm_source=pmos.md&utm_medium=referral&utm_campaign=issue-NN` (the renderer adds them; never retag a
published archive block).
