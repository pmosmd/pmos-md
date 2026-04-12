# CLAUDE.md — pmos.md

Instructions for Claude Code working on this project.

## What this project is

`pmos.md` is a single-page static site — a weekly-updated resource hub for product managers.
Hosted on GitHub Pages at `https://pmos.md` via the `pmosmd/pmos-md` repo.

## File structure

```
/
├── index.html     — the entire site (single file)
├── feed.xml       — RSS feed, updated weekly
├── llms.txt       — AI agent discovery file
├── agent.html     — weekly scan + publish workflow (run locally, never deploy)
├── CNAME          — pmos.md (do not edit)
└── CLAUDE.md      — this file
```

## Weekly update workflow

Every Sunday, update two sections in `index.html`:

### Signal section
- Replace 4 articles under "This week" with new ones
- Move best "This week" articles to "This month" (keep top 4, drop the rest)

### GitHub repos section
- Add notable new repos if they emerge, keep list at 5
- Update star counts if significantly changed

Then update `feed.xml`:
- Duplicate the most recent `<item>` block
- Update `<title>`, `<guid>`, `<pubDate>`, `<description>` with this week's content

Update the last-updated date:
- Find `<span data-updated="` and update the date in both attribute and text
- Format: `MMM DD, YYYY` e.g. `Apr 20, 2026`

Commit message format: `week of MMM DD, YYYY`

## Content guidelines

- Repos: must have >1k GitHub stars OR be demonstrably useful to working PMs
- Articles: no think-pieces without concrete takeaways, no hype without substance
- Recommended: permanent shelf, changes rarely, editor's subjective judgment only
- Tone: direct, no marketing language, no superlatives

## Design rules

- Single HTML file — do not split into separate CSS/JS files
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
