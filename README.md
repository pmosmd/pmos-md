# pmos.md

A weekly-updated index of GitHub repos, articles, and curated reads for product managers navigating AI. Built by a PM, for PMs. No ads, no affiliates, no fluff.

**Live at [pmos.md](https://pmos.md) · [RSS feed](https://pmos.md/feed.xml) · [archive](https://pmos.md/archive.html)**

## How it updates

Every Sunday a scheduled GitHub Actions workflow publishes a new issue, with no human review in the loop. The model only chooses and writes. Code does everything that can be checked:

- `scripts/facts.py` reads the feeds and every candidate page (title, publish date from page metadata, paywall flag), plus GitHub stars and releases from the API.
- The model writes one small file, `data/issue-NNN.json`. `scripts/render.py` turns it into the page, one archive block and one feed item.
- `scripts/selfcheck.py` refuses to publish unless every check passes: links answer 200, dates and titles match the pages, stars match the GitHub API, history is append-only.
- The job that writes has no write credentials. A second job re-runs the checks and is the only one that commits.
- A Monday watchdog opens an issue if the page is stale, and each published issue posts a receipt issue.

See [`CLAUDE.md`](CLAUDE.md) for the editorial and verification rules, [`decisions/`](decisions) for why it works this way, and [`.github/workflows/`](.github/workflows) for the jobs.

## Structure

- `index.html` — the current issue
- `archive.html` — every past issue, append-only
- `feed.xml` — RSS feed, append-only
- `llms.txt` — AI agent discovery file
- `data/` — the repo watchlist, the MCP table, and what the model wrote for each issue
- `scripts/` — the pipeline (Python, standard library only); `tests/` — its offline tests
- `CLAUDE.md` — editorial rules, verification gates, design constraints

## Suggest a resource

[Open an issue](https://github.com/pmosmd/pmos-md/issues/new) or email hello@pmos.md.
