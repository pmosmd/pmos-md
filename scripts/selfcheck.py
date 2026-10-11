#!/usr/bin/env python3
"""The publish gate. Exit 0 = clear to publish, 1 = blocked.

    python3 scripts/selfcheck.py [--root .] [--base HEAD] [--facts facts.json] [--offline] [--report out.md]

Every check maps to a failure that shipped before (CLAUDE.md > Known-bad patterns): wrong star counts,
dead or invented links, stale articles labelled fresh, mismatched headings, edited history, placeholder
hrefs, numbers that drifted from reality. The model cannot skip a check: the workflow commits only if
this script passes, and the model has no write credentials.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html as htmllib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.dom import minidom

import common as C
import render as R
import rules

SOFT_HOSTS = {"amazon.com"}          # bot-hostile hosts on the static Recommended shelf: warn, don't block


class Gate:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    def ok(self, name: str) -> None:
        self.passed.append(name)
        print(f"ok    {name}")

    def fail(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"FAIL  {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"warn  {msg}")

    def check(self, cond: bool, ok_name: str, fail_msg: str) -> bool:
        (self.ok(ok_name) if cond else self.fail(fail_msg))
        return cond


class HeadingScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.seq: list[int] = []
        self.errs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag):
            self.stack.append(tag)
            self.seq.append(int(tag[1]))

    def handle_endtag(self, tag):
        if re.fullmatch(r"h[1-6]", tag):
            if not self.stack or self.stack[-1] != tag:
                self.errs.append(f"</{tag}> closes {self.stack[-1:] or 'nothing'}")
            else:
                self.stack.pop()


def git_show(root: Path, ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def section(doc: str, sid: str) -> str:
    m = re.search(rf'<section[^>]*id="{sid}">(.*?)\n  </section>', doc, re.S)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(C.ROOT))
    ap.add_argument("--base", default="HEAD", help="git ref holding the last published state (append-only check)")
    ap.add_argument("--facts")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    root = Path(a.root)
    g = Gate()
    index, arch, feed = C.read(root / "index.html"), C.read(root / "archive.html"), C.read(root / "feed.xml")

    # ── identity ──
    st = C.index_state(index)
    n = st["issue"]
    if not g.check(n is not None and st["updated"] is not None, "index carries an issue number and data-updated date",
                   "index.html is missing the issue number or data-updated"):
        return finish(g, a, None)
    ds = C.long_date(st["updated"])
    g.check(f'<span data-updated="{ds}">{ds}</span>' in index and f"issue #{n} · " in index, f"topbar says issue #{n}, {ds}", "topbar label does not match the issue")
    g.check(f"editor's pick <span class=\"bar\"></span> #{n}</div>" in index, "hero kicker carries the issue number", "hero kicker issue number is missing or wrong")

    # ── structure ──
    try:
        minidom.parseString(feed.encode("utf-8"))
        g.ok("feed.xml parses as XML")
    except Exception as e:  # noqa: BLE001
        g.fail(f"feed.xml is not valid XML: {e}")
    for name, doc in (("index.html", index), ("archive.html", arch)):
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S):
            try:
                json.loads(blk)
            except json.JSONDecodeError as e:
                g.fail(f"{name}: JSON-LD does not parse: {e}")
        hs = HeadingScan()
        hs.feed(doc)
        skips = [(x, y) for x, y in zip(hs.seq, hs.seq[1:]) if y > x + 1]
        g.check(not (hs.errs or hs.stack or skips) and hs.seq[:1] == [1], f"{name}: headings balanced, h1 first, no skipped levels",
                f"{name}: heading problems: closers={hs.errs} unclosed={hs.stack} skips={skips}")
    for name, doc in (("index.html", index), ("archive.html", arch), ("feed.xml", feed)):
        bad = len(re.findall(r'href="(#|)"', doc)) + len(re.findall(r"@@|\bTODO\b|lorem ipsum|example\.com", doc, re.I))
        g.check(bad == 0, f"{name}: no placeholder hrefs or leftovers", f"{name}: {bad} placeholder href(s) or leftover marker(s)")

    # ── counts must equal what is on the page ──
    sig = section(index, "signal")
    rows_sig = re.findall(r'<a class="art-link" href="([^"]*)"[^>]*>([^<]*)</a>\s*<div class="art-take">([^<]*)</div>', sig)
    repos_sec = section(index, "repos")
    rows_repo = re.findall(r'<div class="repo-row">', repos_sec)
    mcp_rows = len(re.findall(r"<td><strong>", section(index, "mcp")))
    pick_rows = len(re.findall(r"<td><a href", section(index, "picks")))

    def badge(name: str) -> int | None:
        m = re.search(rf'{re.escape(name)} <span class="h2-count">(\d+)', index)
        return int(m.group(1)) if m else None
    for label, real in (("Signal", len(rows_sig)), ("GitHub repos", len(rows_repo)), ("MCP for PMs", mcp_rows), ("Recommended", pick_rows)):
        g.check(badge(label) == real, f"{label} badge matches {real} rows", f"{label} badge says {badge(label)} but the page has {real} rows")
    lead = re.search(r'<span class="lead-n">(\d+)</span>', index)
    g.check(bool(lead) and int(lead.group(1)) == R.count_links(index), f"hero shows {R.count_links(index)} links checked",
            f"hero 'links checked' is {lead.group(1) if lead else '?'} but the page has {R.count_links(index)} distinct outbound links")

    # ── archive + feed carry this issue, newest first ──
    blocks = C.archive_blocks(arch)
    items = C.feed_items(feed)
    g.check(bool(blocks) and next(iter(blocks)) == n and max(blocks) == n, f"archive.html has issue #{n} on top", f"archive.html does not have issue #{n} on top")
    g.check(bool(items) and next(iter(items)) == n and max(items) == n, f"feed.xml has issue #{n} as the first item", f"feed.xml does not have issue #{n} as the first item")
    block, item = blocks.get(n, ""), items.get(n, "")
    arch_rows = re.findall(r'<a class="row-link" href="([^"]*)"[^>]*>([^<]*)</a>\s*<div class="row-take">([^<]*)</div>', block)
    g.check(len(arch_rows) == len(rows_sig) and all(C.norm_url(x[0]) == C.norm_url(y[0]) and htmllib.unescape(x[1]) == htmllib.unescape(y[1])
            and htmllib.unescape(x[2]) == htmllib.unescape(y[2]) for x, y in zip(arch_rows, rows_sig)),
            "Signal links, titles and takeaways are identical in index and archive", "Signal rows differ between index.html and the archive block")
    feed_text = htmllib.unescape(item)
    g.check(all(htmllib.unescape(t) in feed_text and htmllib.unescape(k) in feed_text and C.norm_url(h) in {C.norm_url(x) for x in C.hrefs(feed_text)}
                for h, t, k in rows_sig), "feed item carries the same Signal links, titles and takeaways", "feed item is missing a Signal row that index.html has")
    index_urls = {C.norm_url(h) for h in C.hrefs(index) if not C.is_internal(h)}
    stray = {C.norm_url(h) for h in C.hrefs(block) if not C.is_internal(h)} - index_urls
    g.check(not stray, "every link in the archive block is also on the page", f"archive block links not on the page: {sorted(stray)[:3]}")

    # ── UTM: this issue's links carry this issue's campaign, nothing else ──
    def untagged(doc: str) -> list[str]:
        out = []
        for h in C.hrefs(doc):
            if C.is_internal(h):
                continue
            if f"utm_campaign=issue-{n}" not in h or "utm_source=pmos.md" not in h or "utm_medium=referral" not in h:
                out.append(h)
        return out
    for name, doc in (("index.html", index), ("archive block", block), ("feed item", item)):
        bad = untagged(htmllib.unescape(doc) if name == "feed item" else doc)
        g.check(not bad, f"{name}: every outbound link is tagged utm_campaign=issue-{n}", f"{name}: {len(bad)} outbound link(s) without the issue-{n} UTM tags, e.g. {bad[:2]}")
    other = re.findall(r"utm_campaign=issue-(\d+)", block + item)
    g.check(all(int(x) == n for x in other), "new archive block and feed item contain no other issue's UTM tag", "new archive block or feed item carries another issue's UTM tag")

    # ── history is append-only ──
    base_arch, base_feed = git_show(root, a.base, "archive.html"), git_show(root, a.base, "feed.xml")
    if base_arch is None or base_feed is None:
        g.warn(f"no archive.html/feed.xml at {a.base}; skipped the append-only check")
    else:
        old_blocks, old_items = C.archive_blocks(base_arch), C.feed_items(base_feed)
        changed = [k for k, v in old_blocks.items() if k != n and blocks.get(k) != v]
        g.check(not changed, "no earlier archive block was edited or removed", f"archive blocks changed or missing: {changed}")
        changed_f = [k for k, v in old_items.items() if k != n and items.get(k) != v]
        g.check(not changed_f, "no earlier feed item was edited or removed", f"feed items changed or missing: {changed_f}")
        if n in old_blocks and old_blocks[n] != block:
            g.fail(f"issue #{n} is already published at {a.base} and may not be rewritten")

    # ── data files ──
    issue_path = root / "data" / f"issue-{n:03d}.json"
    registry = C.load_json(root / "data" / "repos.json")
    sources = C.load_json(root / "scripts" / "sources.json")
    reg_names = {r["repo"] for r in registry["repos"]}
    page_repos = set(re.findall(r'class="r-link" href="https://github\.com/([^"?]+)\?', repos_sec)) - {"topics/product-management"}
    g.check(page_repos == reg_names, "repo rows on the page match data/repos.json", f"repo rows differ from the registry: {sorted(page_repos ^ reg_names)}")
    mcp = C.load_json(root / "data" / "mcp.json")
    g.check(len(mcp["rows"]) == mcp_rows and {C.norm_url(r["url"]) for r in mcp["rows"]} <= index_urls,
            "MCP table on the page matches data/mcp.json", "MCP table on the page differs from data/mcp.json")
    if not g.check(issue_path.exists(), f"data/issue-{n:03d}.json is present", f"data/issue-{n:03d}.json is missing"):
        return finish(g, a, None)
    issue = C.load_json(issue_path)

    report = None
    if a.facts:
        facts = C.load_json(a.facts)
        errs, warns, report = rules.validate_issue(issue, facts, registry, sources)
        errs += rules.validate_data(registry, C.load_json(root / "data" / "mcp.json"), C.load_json(root / "data" / "state.json"), facts)
        for e in errs:
            g.fail(e)
        for w in warns:
            g.warn(w)
        if not errs:
            g.ok("issue file passes the editorial and integrity rules against the verified facts")
    else:
        g.warn("no --facts given; skipped the editorial rules and facts membership checks")

    # ── network (skipped with --offline) ──
    if not a.offline:
        urls = sorted({htmllib.unescape(h) for doc in (index, block, htmllib.unescape(item)) for h in C.hrefs(doc)})
        urls = [u for u in urls if C.host_of(u) not in C.INTERNAL_HOSTS]

        def probe(u: str):
            code, final, body = C.fetch(u, retries=2)
            return u, code, body

        with cf.ThreadPoolExecutor(8) as ex:
            res = list(ex.map(probe, urls))
        hard = [(c, u) for u, c, _ in res if c != 200 and C.host_of(u) not in SOFT_HOSTS]
        soft = [(c, u) for u, c, _ in res if c != 200 and C.host_of(u) in SOFT_HOSTS]
        g.check(not hard, f"{len(urls)} distinct URLs answer HTTP 200", f"URLs that did not return 200: {hard}")
        for c, u in soft:
            g.warn(f"{u} returned {c} (bot-hostile host, not blocking)")
        # dates and titles re-read from page metadata now, not trusted from the model or the feed
        want = {C.norm_url(h): (t, k) for h, t, k in rows_sig}
        hero_url = re.search(r'<h2 class="hero-pick-title">\s*<a href="([^"]*)"', index)
        bodies = {C.norm_url(u): b for u, c, b in res if c == 200}
        rendered = {C.norm_url(x["url"]): C.parse_date(x["date"]) for x in facts["articles"]} if a.facts else {}
        for u in list(want) + ([C.norm_url(htmllib.unescape(hero_url.group(1)))] if hero_url else []):
            body = bodies.get(u)
            if not body:
                continue
            meta = C.page_meta(body)
            pub = C.parse_any_datetime(meta["published"])
            if pub and a.facts and u in rendered:
                if abs((pub.date() - rendered[u]).days) > 1:
                    g.fail(f"{u}: page says {pub.date()} but the issue uses {rendered[u]}")
        # star counts re-fetched now: rendered value must be within 2% of the API
        drift = []
        for name in reg_names:
            live = (C.gh_api(f"repos/{name}") or {}).get("stargazers_count")
            m = re.search(rf'href="https://github\.com/{re.escape(name)}\?[^"]*"[^>]*>[^<]*</a>.*?<span class="stars">([^<]+)</span>', repos_sec, re.S)
            if not live or not m:
                drift.append(f"{name}: could not compare")
                continue
            shown = C.stars_value(m.group(1))
            if abs(shown - live) / live > 0.02:
                drift.append(f"{name}: page {m.group(1)} vs API {live}")
        g.check(not drift, "star counts match the GitHub API within 2%", f"star counts drifted: {drift}")
    return finish(g, a, report)


def finish(g: Gate, a, report) -> int:
    print(f"\n{'BLOCKED' if g.errors else 'CLEAR TO PUBLISH'}: {len(g.passed)} checks passed, {len(g.errors)} failed, {len(g.warnings)} warnings")
    if a.report:
        lines = ["## Gate report", f"- {len(g.passed)} checks passed, {len(g.errors)} failed, {len(g.warnings)} warnings"]
        if report:
            lines.append(f"- Signal: {report['pm_native']}/{report['signal_items']} PM-native, {report['paid_or_partial']} paid or part-paid, "
                         f"{report['distinct_sources']} distinct sources")
            lines.append(f"- Spotlight lane: {report['spotlight_lane']} (rotation suggested: {report['suggested_lane']})")
        lines += [f"- warning: {w}" for w in g.warnings] + [f"- FAILED: {e}" for e in g.errors]
        Path(a.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if g.errors else 0


if __name__ == "__main__":
    sys.exit(main())
