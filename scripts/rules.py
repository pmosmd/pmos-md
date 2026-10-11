"""Editorial and integrity rules for an issue file (data/issue-NNN.json).

The model writes only editorial text and picks URLs / repos. Everything else is looked up in
the verified facts (scripts/facts.py). validate_issue() returns (errors, warnings, report):
errors block publishing; warnings and the report are surfaced in the receipt.
"""
from __future__ import annotations

import datetime as dt
import re

import common as C

LIMITS = {
    "note": (0, 1100), "hero.quote": (60, 320), "hero.why": (10, 140),
    "spotlight.text": (80, 1300), "takeaway": (40, 240), "repo_news.text": (20, 420),
}
MIN_STARS = 1000          # CLAUDE.md > Repos; emerging repos need "emerging": true in the registry
STALE_DAYS = 90


def by_url(facts: dict) -> dict[str, dict]:
    return {C.norm_url(a["url"]): a for a in facts["articles"]}


def _len_ok(name: str, text: str, errors: list[str], key: str) -> None:
    lo, hi = LIMITS[key]
    n = len(text or "")
    if not (lo <= n <= hi):
        errors.append(f"{name}: length {n} is outside {lo}-{hi} characters")


def validate_issue(issue: dict, facts: dict, registry: dict, sources: dict) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    arts = by_url(facts)
    repos = {r["repo"]: r for r in facts["repos"]}
    reg = {r["repo"]: r for r in registry["repos"]}

    # identity
    if issue.get("issue") != facts["issue"]:
        errors.append(f"issue number {issue.get('issue')} != expected {facts['issue']}")
    if issue.get("date") != facts["date"]:
        errors.append(f"issue date {issue.get('date')} != expected {facts['date']}")
    try:
        if C.parse_date(facts["date"]).weekday() != 6:
            warnings.append(f"issue date {facts['date']} is not a Sunday")
    except ValueError:
        errors.append("issue date is not an ISO date")

    if "note" in issue:
        _len_ok("note", issue["note"], errors, "note")

    # hero (editor's pick): one free, PM-native, this-week article that is not also in Signal
    hero = issue.get("hero") or {}
    ha = arts.get(C.norm_url(hero.get("url", "")))
    if not ha:
        errors.append(f"hero: {hero.get('url')} is not in the verified facts")
    else:
        if ha["window"] != "week":
            errors.append(f"hero: must be from the last 7 days (window={ha['window']})")
        if ha["paywall"] in ("paid", "partial"):
            errors.append("hero: must be free to read")
        if ha["kind"] != "pm":
            errors.append(f"hero: must come from a PM-native source (kind={ha['kind']})")
        if ha["used"] or not ha["date_confirmed"]:
            errors.append("hero: already used, or its publish date is unconfirmed")
    _len_ok("hero.quote", hero.get("quote", ""), errors, "hero.quote")
    _len_ok("hero.why", hero.get("why", ""), errors, "hero.why")

    # signal
    sig = issue.get("signal") or {}
    seen = {C.norm_url(hero.get("url", ""))}
    chosen: list[dict] = []
    for group, window, lo, hi in (("week", "week", 3, 4), ("month", "month", 2, 4)):
        items = sig.get(group) or []
        if not (lo <= len(items) <= hi):
            errors.append(f"signal.{group}: {len(items)} items, expected {lo}-{hi}")
        for i, it in enumerate(items, 1):
            tag = f"signal.{group}[{i}]"
            a = arts.get(C.norm_url(it.get("url", "")))
            if not a:
                errors.append(f"{tag}: {it.get('url')} is not in the verified facts")
                continue
            k = C.norm_url(a["url"])
            if k in seen:
                errors.append(f"{tag}: duplicate link ({a['title'][:50]})")
            seen.add(k)
            if a["window"] != window:
                errors.append(f"{tag}: dated {a['date']} ({a['age_days']} days old) belongs in '{a['window']}', not '{group}'")
            if a["used"]:
                errors.append(f"{tag}: already published in an earlier issue ({a['title'][:50]})")
            if not a["date_confirmed"]:
                errors.append(f"{tag}: publish date is not confirmed by page metadata")
            _len_ok(f"{tag}.takeaway", it.get("takeaway", ""), errors, "takeaway")
            chosen.append(a)

    # spotlight
    sp = issue.get("spotlight") or {}
    srepo = sp.get("repo")
    if srepo not in reg:
        errors.append(f"spotlight: {srepo} is not in data/repos.json")
    else:
        rf = repos.get(srepo, {})
        if not rf.get("hook"):
            errors.append(f"spotlight: {srepo} has no stable release in the last 7 days (no this-week story)")
        if srepo in facts["spotlight"]["recent_repos_excluded"]:
            errors.append(f"spotlight: {srepo} was a spotlight in the last 6 issues")
        sl = facts["spotlight"]["suggested_lane"]
        if sl and reg[srepo]["lane"] != sl:
            warnings.append(f"spotlight lane is '{reg[srepo]['lane']}', rotation suggested '{sl}'")
    _len_ok("spotlight.text", sp.get("text", ""), errors, "spotlight.text")

    # repo news: only stable releases from the last 7 days, tag must match the facts
    for repo, news in (issue.get("repo_news") or {}).items():
        rf = repos.get(repo)
        if repo not in reg or not rf:
            errors.append(f"repo_news: {repo} is not in the registry")
            continue
        match = next((r for r in rf["releases_7d"] if r["tag"] == news.get("release") and not r["prerelease"]), None)
        if not match:
            errors.append(f"repo_news[{repo}]: release {news.get('release')} is not a stable release from the last 7 days")
        _len_ok(f"repo_news[{repo}].text", news.get("text", ""), errors, "repo_news.text")
        if re.match(r"(?i)this week", news.get("text", "")):
            errors.append(f"repo_news[{repo}]: text must continue the sentence 'This week's <tag> (<date>) ...'")

    # registry health
    for name, r in reg.items():
        rf = repos.get(name)
        if not rf or not rf["found"]:
            errors.append(f"registry: {name} not found on GitHub")
            continue
        if rf["archived"]:
            errors.append(f"registry: {name} is archived; retire it")
        if rf["stale"]:
            errors.append(f"registry: {name} has had no push for {STALE_DAYS}+ days; retire it (data/repos.json > retired)")
        if (rf["stars"] or 0) < MIN_STARS and not r.get("emerging"):
            errors.append(f"registry: {name} has {rf['stars']} stars (< {MIN_STARS}) and is not flagged emerging")

    # report (soft editorial measures, surfaced in the receipt)
    kinds = [a["kind"] for a in chosen]
    n = len(chosen) or 1
    pm_native = sum(1 for k in kinds if k == "pm")
    paywalled = sum(1 for a in chosen if a["paywall"] in ("paid", "partial"))
    report = {"signal_items": len(chosen), "pm_native": pm_native, "other_kinds": len(chosen) - pm_native,
              "paid_or_partial": paywalled, "distinct_sources": len({a["source"] for a in chosen}),
              "spotlight_lane": reg.get(srepo, {}).get("lane"), "suggested_lane": facts["spotlight"]["suggested_lane"]}
    if len(chosen) - pm_native > 2:
        warnings.append(f"{len(chosen) - pm_native} of {len(chosen)} Signal items are not PM-native (target: at most 2)")
    if paywalled > 2:
        warnings.append(f"{paywalled} of {len(chosen)} Signal items are paid or part-paid (target: at most 2)")
    top = max((sum(1 for a in chosen if a["source"] == s) for s in {a["source"] for a in chosen}), default=0)
    if top > 2:
        warnings.append(f"one source supplies {top} Signal items (target: at most 2)")
    return errors, warnings, report


def validate_data(registry: dict, mcp: dict, state: dict, facts: dict) -> list[str]:
    """Checks on the long-lived data files (registry, MCP table, review state)."""
    errors: list[str] = []
    ym = r"\d{4}-\d{2}"
    for key in ("last_repo_audit", "last_quarterly_review"):
        if not re.fullmatch(ym, state.get(key, "")):
            errors.append(f"data/state.json: {key} must look like 2026-10")
    mode = facts.get("mode", {})
    if mode.get("repo_audit_due"):
        errors.append("monthly repo audit is due: review data/repos.json (add, retire, reject), then set last_repo_audit in data/state.json to this month")
    if mode.get("quarterly_review_due"):
        errors.append("quarterly review is due: re-verify every row in data/mcp.json against the vendor's own page and review scripts/sources.json, "
                      "then set last_quarterly_review in data/state.json to this month")
    rows = mcp.get("rows", [])
    if not (6 <= len(rows) <= 12):
        errors.append(f"data/mcp.json: {len(rows)} rows, expected 6-12")
    seen = set()
    for r in rows:
        name = r.get("tool", "?")
        if r.get("stage") not in mcp.get("stages", []):
            errors.append(f"data/mcp.json: {name}: stage '{r.get('stage')}' is not one of {mcp.get('stages')}")
        if r.get("status") != "official":
            errors.append(f"data/mcp.json: {name}: only vendor-official servers are listed (status must be 'official')")
        if not str(r.get("url", "")).startswith("https://"):
            errors.append(f"data/mcp.json: {name}: url must be https")
        if not (20 <= len(r.get("use", "")) <= 200):
            errors.append(f"data/mcp.json: {name}: 'use' must be 20-200 characters")
        k = C.norm_url(r.get("url", ""))
        if k in seen:
            errors.append(f"data/mcp.json: {name}: duplicate url")
        seen.add(k)
    for r in registry["repos"]:
        if r["lane"] not in registry["lanes"]:
            errors.append(f"data/repos.json: {r['repo']}: unknown lane '{r['lane']}'")
    return errors
