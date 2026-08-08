## Decision: single append-only `archive.html` + unattended weekly job that auto-publishes to `main`

Every issue is retained forever in one append-only page, with `#issue-N` anchors as
permalinks. `feed.xml` becomes append-only too. `index.html` is demoted to "the current
view" rather than the source of truth. A scheduled agent runs Sundays 08:00 PT, archives
the outgoing issue, researches the new one, and commits directly to `main` with no
human review step.

## Context: the site had gone 16 weeks without an update and was silently losing all history

The front page still read "wk 16 · Apr 19, 2026" on Aug 8, 2026. Two separate failures:

- **Retention.** The documented workflow said "keep top 4, drop the rest." Nothing was
  ever written down, so ~16 weeks of curation is permanently gone. The one artifact meant
  to preserve it — `feed.xml` — held a single stale item whose every link was `href="#"`.
- **Cadence.** Updating required opening `agent.html` locally, pasting a GitHub PAT into
  a browser page, and clicking through scan → approve → publish. It depended on a human
  being available every Sunday, and that dependency is what failed.

A link/star audit run during this work found the cost of having no verification step:
`product-on-purpose/pm-skills` was listed at 4.3k stars but actually had 524;
`NousResearch/hermes-agent` was listed at 65k but actually had 227k; and two article URLs
in issue #16 returned 404, consistent with having been invented rather than fetched.

## Alternatives considered

- **Per-issue pages (`/issues/32.html`).** Real URLs, individually indexable, better SEO.
  Rejected for now: ~52 files/year, needs its own index page anyway, and each page either
  duplicates the full stylesheet or forces a shared CSS file that breaks the single-file rule.
- **RSS as the only archive.** Zero new pages. Rejected: most readers truncate older items,
  and there would be no browsable archive on the site itself.
- **JSON data file rendered by JS.** Rejected on the same grounds as the earlier design
  refresh — the content is the SEO surface and must stay in static HTML.
- **Scheduled agent that opens a PR instead of committing.** Recommended, but the editor
  chose auto-publish deliberately: a review gate reintroduces exactly the human dependency
  that produced the 16-week gap.
- **Keep it manual.** Rejected — this is the status quo that failed.

## Reasoning

Making the archive the source of truth means retention is structural rather than a step
someone remembers. The weekly job cannot lose content, because archiving happens *before*
the front page is touched, and both archive files are append-only by rule.

A single `archive.html` preserves the no-build-step property and the markdown aesthetic
while still giving shareable permalinks via anchors. The append-only structure is
deliberately mechanical, so splitting into per-issue pages later is a pure transform if
the archive ever grows enough to justify it.

On auto-publish: since the editor declined a review gate, trust has to live in the
automation instead. So verification became non-negotiable and is written into CLAUDE.md —
every URL fetched for a 200, every star count read from the GitHub API, every repo's >1k
threshold checked on the day. That directly targets the three defect classes already found
in production rather than assuming a human would have caught them (they didn't).

## Trade-offs accepted

- **Unreviewed content publishes to a public domain under the editor's name.** Mitigated by
  hard verification rules, not eliminated. Editorial judgment — tone, "is this worth
  reading" — is genuinely delegated to the agent and will occasionally be wrong.
- **`archive.html` duplicates ~90 lines of CSS** rather than sharing a stylesheet. Accepted
  to keep the single-file rule intact for `index.html`; the cost is that palette changes
  must be made in two places.
- **The archive grows unbounded** (~75KB/year). Fine for years; revisit if it becomes slow.
- **No per-issue SEO.** Individual issues won't rank on their own. Accepted as the cost of
  staying build-free; revisit if archive traffic ever justifies the split.
- **Historical errors are preserved, not corrected.** Wrong star counts and dead links stay
  in issue #16, annotated. The archive is a record of what was published, not what was true.
