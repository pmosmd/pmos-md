# data/issue-NNN.json

The one file the weekly model writes for an issue. Everything not listed here (titles, dates, domains,
paid tags, stars, release tags, UTM tags, counts, HTML) is filled in from the verified facts by
`scripts/render.py`. Extra keys are ignored. See `tests/test_pipeline.py` for a complete example.

```json
{
  "issue": 42,                               // facts.issue
  "date": "2026-10-18",                      // facts.date (a Sunday)
  "note": "",                                // optional: missed weeks, corrections, format changes (max 1,100 chars)
  "hero": {                                  // editor's pick: one free, PM-native article from the last 7 days
    "url": "https://…",                      // must be in facts.articles; not also in signal
    "quote": "…",                            // 60–320 chars, paraphrase of the page
    "why": "…"                               // 10–140 chars
  },
  "spotlight": {
    "repo": "owner/name",                    // in data/repos.json, with a stable release in the last 7 days
    "tags": ["…"],                           // optional; defaults to the registry tags
    "text": "…"                              // 80–1,300 chars, grounded in the release notes
  },
  "signal": {
    "week":  [ { "url": "https://…", "takeaway": "…" } ],   // 3–4 items, each in facts.articles with window "week"
    "month": [ { "url": "https://…", "takeaway": "…" } ]    // 2–4 items, window "month"; takeaway is 40–240 chars
  },
  "repo_news": {                             // only for stable releases from the last 7 days
    "owner/name": { "release": "v1.2.3", "text": "adds …" }  // rendered as: This week's v1.2.3 (Oct 14) adds …
  }
}
```

Review weeks also edit `data/repos.json`, `data/mcp.json` and `data/state.json` (see CLAUDE.md > Cadence).

`facts.json` fields the model uses: `articles[]` (`url`, `title`, `date`, `window`, `paywall`, `kind`, `excerpt`,
`used`), `repos[]` (`stars`, `releases_7d[]` with `body_head`, `stale`, `hook`), `candidate_repos[]`,
`spotlight` (`eligible`, `suggested_lane`, `recent_repos_excluded`), `mode`, `warnings`.

Run `python3 scripts/render.py --issue data/issue-NNN.json --facts facts.json` and then
`python3 scripts/selfcheck.py --facts facts.json`; fix every error it prints and run both again.
