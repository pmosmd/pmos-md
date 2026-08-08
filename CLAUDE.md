# CLAUDE.md — pmos.md

Instructions for Claude Code working on this project.

## What this project is

`pmos.md` is a single-page static site — a weekly-updated resource hub for product managers.
Hosted on GitHub Pages at `https://pmos.md` via the `pmosmd/pmos-md` repo.

## File structure

```
/
├── index.html     — the current issue (single file)
├── archive.html   — every past issue, append-only
├── feed.xml       — RSS feed, append-only
├── llms.txt       — AI agent discovery file
├── agent.html     — legacy local publish UI (never deploy; see note below)
├── CNAME          — pmos.md (do not edit)
└── CLAUDE.md      — this file
```

## Weekly update workflow

Runs automatically every Sunday 08:00 PT and commits straight to `main`.
Issue numbering follows the ISO week number.

**Archive first — this is the rule that matters.** Nothing is ever dropped.
Before touching `index.html`, append the outgoing issue to `archive.html` and
`feed.xml`. Both files are append-only: never edit or delete an existing issue
block, even to fix an error. Corrections go in the *new* issue, noting what changed.

Order of operations:

1. **Archive the outgoing issue** — prepend a `<section class="issue" id="issue-N">`
   directly below the marker comment in `archive.html`, and prepend a matching
   `<item>` in `feed.xml`. Every issue gets an anchor so
   `pmos.md/archive.html#issue-N` is a permalink.
2. **Research candidates** — see source list below.
3. **Verify before publishing** (non-negotiable, this is an unattended job):
   - Every URL must return HTTP 200. Drop anything that doesn't. Never publish
     a link you have not fetched.
   - Every star count must come from `api.github.com/repos/{owner}/{repo}`,
     never from a blog post, a search result, or a previous issue.
   - Repos must clear >1k stars *on verification*, not on reputation.
4. **Update `index.html`** — Signal (4 this week / 4 this month), repos,
   spotlight, editor's pick, `data-updated`, `wk NN`, and issue number in both
   the hero-pick kicker and hero-meta.
5. **Add the new issue to `archive.html` too** — the archive holds every issue
   including the current one, so permalinks always resolve.

Commit message format: `issue #NN — week of MMM DD, YYYY`

### Known-bad patterns to avoid

These have all shipped to production before. Check for them:
- Star counts drifting from reality (issue #16 listed a 524-star repo as 4.3k
  and a 227k-star repo as 65k)
- `href="#"` placeholders reaching `feed.xml`
- Invented article URLs that 404 (two shipped in issue #16)
- Mismatched heading tags (`<h2>` closed with `</h3>`) — breaks the a11y audit
- Skipped heading levels — the hero pick must be `<h2>`, not `<h3>`

### agent.html

Superseded by the scheduled job. It required pasting a GitHub PAT into a local
browser page; do not revive that pattern. Use `gh` CLI auth instead — never
embed a token in the git remote URL.

## Content guidelines

- Repos: must have >1k GitHub stars OR be demonstrably useful to working PMs
- Articles: no think-pieces without concrete takeaways, no hype without substance
- Recommended: permanent shelf, changes rarely, editor's subjective judgment only
- Tone: direct, no marketing language, no superlatives

## Design rules

- `index.html` stays a single file — do not split its CSS/JS out
- `archive.html` is the one additional page; it carries its own inline styles
  (a trimmed subset of the same tokens) rather than sharing a stylesheet
- JetBrains Mono throughout — do not introduce other fonts
- Markdown visual syntax (##, >, ---, -, code) must stay as design elements
- Max width 840px, monospace, minimal
- Dark mode works via CSS variables — do not hardcode colors

## Analytics

GoatCounter at `https://pmosmd.goatcounter.com`
Script tag in `<head>` — do not remove or change.

## When suggesting weekly content, search:

- GitHub trending (AI, PM, llm, product tags)
- Lenny's Newsletter, Reforge, First Round Review
- The Pragmatic Engineer, Stratechery, Mind the Product
- HN front page (Show HN, Ask HN)
- X/Twitter: @lennysan, @shreyas, @benedictevans, @joulee

Return candidates as a markdown list with source and one-line summary.
Editor makes final selection.

## Deploy

Push to `main` branch of `pmosmd/pmos-md`.
GitHub Pages auto-deploys on every commit.
Site is live at `https://pmos.md` within ~60 seconds.
