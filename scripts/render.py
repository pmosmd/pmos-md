#!/usr/bin/env python3
"""Render data/issue-NNN.json into index.html, archive.html and feed.xml. Deterministic; no model.

    python3 scripts/render.py --issue data/issue-041.json --facts facts.json [--replace]

index.html is regenerated only between <!-- pmos:begin NAME --> / <!-- pmos:end NAME --> markers.
archive.html and feed.xml get one new block at the top; existing blocks are never touched.
Titles, dates, paywall flags, stars, release tags, UTM tags and counts all come from the verified
facts and the registry, never from model-written text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import re
import sys
from pathlib import Path

import common as C
import rules

STAR_GLYPH_FEED = "&#9733;"


# ───────────────────────── small helpers ─────────────────────────
def indent(text: str, pad: str) -> str:
    return "\n".join((pad + ln) if ln.strip() else ln for ln in text.split("\n"))


def set_region(doc: str, name: str, inner: str, inline: bool = False) -> str:
    pat = re.compile(rf"([ \t]*)(<!-- pmos:begin {name} -->)(.*?)(<!-- pmos:end {name} -->)", re.S)
    m = pat.search(doc)
    if not m:
        raise SystemExit(f"index.html has no <!-- pmos:begin {name} --> markers")
    pad = m.group(1)
    body = inner if inline else "\n" + indent(inner.strip("\n"), pad) + "\n" + pad
    return doc[:m.start()] + pad + m.group(2) + body + m.group(4) + doc[m.end():]


def paid_tag(paywall: str) -> str:
    if paywall == "paid":
        return '<span class="tag tag-paid">paid</span>'
    if paywall == "partial":
        return '<span class="tag tag-paid">part paid</span>'
    return ""


def paid_text(paywall: str) -> str:
    return {"paid": "paid", "partial": "part paid"}.get(paywall, "")


def count_links(doc: str) -> int:
    return len({C.norm_url(h) for h in C.hrefs(doc) if not C.is_internal(h)})


# ───────────────────────── model ─────────────────────────
def month_label(ym: str) -> str:
    y, mth = ym.split("-")
    return f"{C.MONTHS[int(mth) - 1]} {y}"


def build_model(issue: dict, facts: dict, registry: dict, mcp: dict, state: dict) -> dict:
    n = issue["issue"]
    D = C.parse_date(issue["date"])
    arts = rules.by_url(facts)
    repo_facts = {r["repo"]: r for r in facts["repos"]}
    reg = {r["repo"]: r for r in registry["repos"]}

    def article(it: dict) -> dict:
        a = arts[C.norm_url(it["url"])]
        return {"title": a["title"], "url": a["url"], "domain": a["domain"], "date": C.parse_date(a["date"]),
                "paywall": a["paywall"], "takeaway": C.squash(it.get("takeaway", "")), "kind": a["kind"], "source": a["source"]}

    hero = {**article({"url": issue["hero"]["url"]}), "quote": C.squash(issue["hero"]["quote"]), "why": C.squash(issue["hero"]["why"])}
    signal = {g: [article(it) for it in issue["signal"][g]] for g in ("week", "month")}

    sp = issue["spotlight"]
    srepo = sp["repo"]
    spotlight = {"repo": srepo, "text": C.squash(sp["text"]), "tags": sp.get("tags") or reg[srepo]["tags"],
                 "lane": registry["lanes"][reg[srepo]["lane"]], "stars": repo_facts[srepo]["stars"]}

    news = issue.get("repo_news") or {}
    lanes = []
    for lane_id, lane_name in registry["lanes"].items():
        rows = []
        for r in registry["repos"]:
            if r["lane"] != lane_id:
                continue
            f = repo_facts[r["repo"]]
            nw = news.get(r["repo"])
            line = ""
            if nw:
                rel = next(x for x in f["releases_7d"] if x["tag"] == nw["release"])
                line = f"This week's {rel['tag']} ({C.short_date(C.parse_date(rel['date']))}) {C.squash(nw['text'])}"
            rows.append({"repo": r["repo"], "tags": r["tags"], "desc": (r["desc"] + " " + line).strip(), "news": line,
                         "stars": f["stars"], "has_news": bool(nw), "is_spotlight": r["repo"] == srepo})
        rows.sort(key=lambda x: (not x["has_news"], -x["stars"]))
        if rows:
            lanes.append({"id": lane_id, "name": lane_name, "rows": rows})
    return {"n": n, "date": D, "note": C.squash(issue.get("note", "")), "hero": hero, "spotlight": spotlight,
            "signal": signal, "lanes": lanes, "topic": registry["topic_link"], "mcp": mcp,
            "reviewed": month_label(state["last_quarterly_review"])}


# ───────────────────────── index.html regions ─────────────────────────
def r_topbar(m: dict) -> str:
    return (f'<span class="updated-prefix">issue #{m["n"]} · </span>'
            f'<span data-updated="{C.long_date(m["date"])}">{C.long_date(m["date"])}</span>')


def r_hero_pick(m: dict) -> str:
    h, n = m["hero"], m["n"]
    meta = " · ".join(x for x in (h["domain"], C.short_date(h["date"]), paid_text(h["paywall"])) if x)
    return f'''<div class="hero-pick">
  <div class="hero-pick-kicker">editor's pick <span class="bar"></span> #{n}</div>
  <h2 class="hero-pick-title">
    <a href="{C.utm(h['url'], n)}" target="_blank" rel="noopener">{C.esc(h['title'])}</a>
  </h2>
  <div class="hero-pick-byline">{C.esc(meta)}</div>
  <p class="hero-pick-quote">{C.esc(h['quote'])}</p>
  <div class="hero-pick-meta">
    <span class="why">{C.esc(h['why'])}</span>
    <a class="read" href="{C.utm(h['url'], n)}" target="_blank" rel="noopener">read →</a>
  </div>
</div>'''


def r_hero_meta(m: dict) -> str:
    d = m["date"]
    return f'''<div class="hero-meta">
  <span class="item lead">
    <span class="lead-n">@@LINKS@@</span>
    <span class="lead-lbl">links<br>checked</span>
  </span>
  <span class="sep">·</span>
  <span class="item col"><span class="k">updated</span><strong>weekly</strong><span class="k">every sunday</span></span>
  <span class="sep">·</span>
  <span class="item col"><span class="k">issue</span><strong>#{m['n']}</strong><span class="k">{C.lower_date(d)}</span></span>
  <span class="sep">·</span>
  <span class="item"><a class="rss-link" href="/archive.html">past issues →</a></span>
  <span class="sep">·</span>
  <span class="item"><a class="rss-link" href="/feed.xml">rss feed →</a></span>
</div>'''


def r_spotlight(m: dict) -> str:
    s, n = m["spotlight"], m["n"]
    tags = "".join(f'<span class="tag">{C.esc(t)}</span>' for t in s["tags"])
    return f'''<div class="spotlight">
  <div>
    <a class="spotlight-link" href="{C.utm('https://github.com/' + s['repo'], n)}" target="_blank" rel="noopener">{C.esc(s['repo'])}</a>
    <p class="spotlight-desc">{C.esc(s['text'])}</p>
    <div>{tags}<span class="tag tag-hot">★ this week</span><span class="tag">{C.esc(s['lane'])}</span><span class="tag tag-src">github.com</span></div>
  </div>
  <div class="spotlight-meta">
    <span class="stars">{C.fmt_stars(s['stars'])}</span>
  </div>
</div>'''


def r_signal(m: dict) -> str:
    n = m["n"]

    def col(title: str, items: list[dict]) -> str:
        rows = []
        for i, a in enumerate(items, 1):
            rows.append(f'''<div class="art-row">
  <span class="art-bullet">{i:02d}</span>
  <div>
    <a class="art-link" href="{C.utm(a['url'], n)}" target="_blank" rel="noopener">{C.esc(a['title'])}</a>
    <div class="art-take">{C.esc(a['takeaway'])}</div>
    <div class="art-src"><span class="tag tag-src">{C.esc(a['domain'])}</span><span class="art-date">{C.short_date(a['date'])}</span>{paid_tag(a['paywall'])}</div>
  </div>
</div>''')
        return (f'<div>\n  <div class="signal-col-head">{title} <span class="count">{len(items)}</span></div>\n'
                + indent("\n".join(rows), "  ") + "\n</div>")

    total = len(m["signal"]["week"]) + len(m["signal"]["month"])
    return f'''<div class="section-head">
  <h2 class="h2">Signal <span class="h2-count">{total} · filtered</span></h2>
  <span class="section-sub">best reads this week, plus a few from the past month</span>
</div>
<p class="section-desc">No hot takes. No think-pieces without a concrete takeaway.</p>

<div class="signal-grid">
{indent(col("this week", m["signal"]["week"]), "  ")}

{indent(col("also worth your time", m["signal"]["month"]), "  ")}
</div>'''


def r_repos(m: dict) -> str:
    n = m["n"]
    i = 0
    parts = []
    for lane in m["lanes"]:
        rows = []
        for r in lane["rows"]:
            i += 1
            tags = "".join(f'<span class="tag">{C.esc(t)}</span>' for t in r["tags"])
            if r["is_spotlight"]:
                tags += '<span class="tag tag-hot">★ spotlight</span>'
            elif r["has_news"]:
                tags += '<span class="tag tag-hot">new this week</span>'
            rows.append(f'''<div class="repo-row">
  <span class="r-bullet">{i:02d}</span>
  <div>
    <a class="r-link" href="{C.utm('https://github.com/' + r['repo'], n)}" target="_blank" rel="noopener">{C.esc(r['repo'])}</a>
    <div class="r-desc">{C.esc(r['desc'])}</div>
    <div>{tags}<span class="tag tag-src">github.com</span></div>
  </div>
  <div class="r-meta"><span class="stars">{C.fmt_stars(r['stars'])}</span></div>
</div>''')
        parts.append(f'<h3 class="lane-head">{C.esc(lane["name"])} <span class="count">{len(lane["rows"])}</span></h3>\n' + "\n\n".join(rows))
    t = m["topic"]
    foot = (f'<div class="repos-foot"><a class="r-link" href="{C.utm(t["url"], n)}" target="_blank" rel="noopener">{C.esc(t["title"])}</a>'
            f'<div class="r-desc">{C.esc(t["desc"])}</div></div>')
    total = sum(len(l["rows"]) for l in m["lanes"])
    return f'''<div class="section-head">
  <h2 class="h2">GitHub repos <span class="h2-count">{total} · watchlist</span></h2>
  <span class="section-sub">what changed this week comes first</span>
</div>
<p class="section-desc">Bias toward repos PMs can use directly, not just reference.</p>

<div>
{indent(chr(10).join([p + chr(10) for p in parts]) + chr(10) + foot, "  ")}
</div>'''


def r_mcp(m: dict) -> str:
    n = m["n"]
    rows = []
    for r in m["mcp"]["rows"]:
        rows.append(f'''<tr>
  <td><strong>{C.esc(r['tool'])}</strong> <span class="tag">{C.esc(r['stage'])}</span></td>
  <td><a href="{C.utm(r['url'], n)}" target="_blank" rel="noopener">{C.esc(r['text'])}</a> <span class="tag tag-src">{C.esc(C.host_of(r['url']))}</span></td>
  <td><code>{C.esc(r['status'])}</code></td>
  <td>{C.esc(r['use'])}</td>
</tr>''')
    return f'''<div class="section-head">
  <h2 class="h2">MCP for PMs <span class="h2-count">{len(rows)} · servers</span></h2>
  <span class="section-sub">official servers by workflow stage · reviewed {m['reviewed']}</span>
</div>
<p class="section-desc">MCP lets your AI agent reach into the tools you already use. Only vendor-official servers are listed, in the order a PM meets them, not all 300+.</p>

<div style="overflow-x:auto">
  <table class="picks-tbl" style="min-width:540px">
    <thead>
      <tr>
        <th>tool</th>
        <th>server</th>
        <th>status</th>
        <th>what PMs use it for</th>
      </tr>
    </thead>
    <tbody>
{indent(chr(10).join(rows), "      ")}
    </tbody>
  </table>
</div>'''


def retag(doc: str, n: int) -> str:
    def fix(mm):
        url = htmllib.unescape(mm.group(1))
        return mm.group(0) if C.is_internal(url) else f'href="{C.utm(url, n)}"'
    return re.sub(r'href="(https?://[^"]*)"', fix, doc)


def render_index(doc: str, m: dict) -> str:
    doc = set_region(doc, "topbar-meta", r_topbar(m), inline=True)
    doc = set_region(doc, "hero-pick", r_hero_pick(m))
    doc = set_region(doc, "hero-meta", r_hero_meta(m))
    doc = set_region(doc, "spotlight", r_spotlight(m))
    doc = set_region(doc, "signal", r_signal(m))
    doc = set_region(doc, "repos", r_repos(m))
    doc = set_region(doc, "mcp", r_mcp(m))
    doc = retag(doc, m["n"])
    return doc.replace("@@LINKS@@", str(count_links(doc)))


# ───────────────────────── archive block + feed item ─────────────────────────
def archive_block(m: dict) -> str:
    n, d = m["n"], m["date"]
    h, s = m["hero"], m["spotlight"]

    def rows(items: list[dict]) -> str:
        out = []
        for a in items:
            src = " · ".join(x for x in (a["domain"], C.short_date(a["date"]), paid_text(a["paywall"])) if x)
            out.append(f'''      <div class="row">
        <span class="bullet">-</span>
        <div class="row-body">
          <a class="row-link" href="{C.utm(a['url'], n)}" target="_blank" rel="noopener">{C.esc(a['title'])}</a>
          <div class="row-take">{C.esc(a['takeaway'])}</div>
          <div class="row-src">{C.esc(src)}</div>
        </div>
      </div>''')
        return "\n".join(out)

    repo_rows = []
    for lane in m["lanes"]:
        for r in lane["rows"]:
            bits = [f'<span class="stars">{C.fmt_stars(r["stars"])}</span>', C.esc(lane["name"])]
            if r["is_spotlight"]:
                bits.append("spotlight")
            if r["has_news"]:
                bits.append("release this week")
            repo_rows.append(f'''      <div class="row">
        <span class="bullet">-</span>
        <div class="row-body">
          <a class="row-link" href="{C.utm('https://github.com/' + r['repo'], n)}" target="_blank" rel="noopener">{C.esc(r['repo'])}</a>
          <div class="row-src">{" · ".join(bits)}</div>
        </div>
      </div>''')
    t = m["topic"]
    repo_rows.append(f'''      <div class="row">
        <span class="bullet">-</span>
        <div class="row-body">
          <a class="row-link" href="{C.utm(t['url'], n)}" target="_blank" rel="noopener">{C.esc(t['title'])}</a>
          <div class="row-src">topic page</div>
        </div>
      </div>''')
    note = f'    <p class="issue-note">\n      {C.esc(m["note"])}\n    </p>\n\n' if m["note"] else ""
    hmeta = " · ".join(x for x in (h["domain"], C.short_date(h["date"]), paid_text(h["paywall"])) if x)
    return f'''  <section class="issue" id="issue-{n}">
    <div class="issue-head">
      <h2 class="issue-no"><a href="#issue-{n}">issue #{n}</a></h2>
      <span class="issue-date">{C.lower_date(d)}</span>
    </div>
{note}    <div class="pick">
      <div class="pick-kicker">editor's pick</div>
      <a href="{C.utm(h['url'], n)}" target="_blank" rel="noopener">{C.esc(h['title'])}</a>
      <p>{C.esc(h['quote'])}</p>
      <div class="row-src">{C.esc(hmeta)}</div>
    </div>

    <div class="pick">
      <div class="pick-kicker">★ spotlight · {C.esc(s['lane'])}</div>
      <a href="{C.utm('https://github.com/' + s['repo'], n)}" target="_blank" rel="noopener">{C.esc(s['repo'])}</a>
      <p>{C.esc(s['text'])}</p>
    </div>

    <div class="grp">
      <div class="grp-head">signal — this week</div>
{rows(m['signal']['week'])}
    </div>

    <div class="grp">
      <div class="grp-head">signal — also worth your time</div>
{rows(m['signal']['month'])}
    </div>

    <div class="grp">
      <div class="grp-head">repos watchlist</div>
{chr(10).join(repo_rows)}
    </div>
  </section>

'''


def feed_item(m: dict, now: dt.datetime) -> str:
    n, d = m["n"], m["date"]
    h, s = m["hero"], m["spotlight"]

    def li(a: dict) -> str:
        extra = f", {paid_text(a['paywall'])}" if a["paywall"] in ("paid", "partial") else ""
        return (f'          <li><a href="{C.utm(a["url"], n)}">{C.esc(a["title"])}</a> — {C.esc(a["domain"])}, {C.short_date(a["date"])}{extra}. '
                f'{C.esc(a["takeaway"])}</li>')

    news_items = []
    for lane in m["lanes"]:
        for r in lane["rows"]:
            if r["has_news"]:
                news_items.append(f'          <li><a href="{C.utm("https://github.com/" + r["repo"], n)}">{C.esc(r["repo"])}</a> '
                                  f'({STAR_GLYPH_FEED} {C.fmt_stars(r["stars"])}): {C.esc(r["news"])}</li>')
    note = f'\n        <p><em>{C.esc(m["note"])}</em></p>\n' if m["note"] else ""
    hmeta = ", ".join(x for x in (h["domain"], C.short_date(h["date"]), paid_text(h["paywall"])) if x)
    body = f'''        <p><strong>Editor's pick:</strong> <a href="{C.utm(h['url'], n)}">{C.esc(h['title'])}</a> ({C.esc(hmeta)}). {C.esc(h['quote'])}</p>

        <p><strong>Spotlight:</strong> <a href="{C.utm('https://github.com/' + s['repo'], n)}">{C.esc(s['repo'])}</a> ({STAR_GLYPH_FEED} {C.fmt_stars(s['stars'])}, {C.esc(s['lane'])}). {C.esc(s['text'])}</p>

        <h3>Signal — this week</h3>
        <ul>
{chr(10).join(li(a) for a in m['signal']['week'])}
        </ul>

        <h3>Signal — also worth your time</h3>
        <ul>
{chr(10).join(li(a) for a in m['signal']['month'])}
        </ul>

        <h3>Repo changes</h3>
        <ul>
{chr(10).join(news_items) if news_items else "          <li>No stable releases among tracked repos this week.</li>"}
          <li>Star counts across the list re-verified against the GitHub API</li>
        </ul>
{note}'''.replace("]]>", "]]&gt;")
    return f'''    <item>
      <title>Issue #{n} — Week of {C.long_date(d)}</title>
      <link>https://pmos.md/archive.html#issue-{n}</link>
      <guid isPermaLink="false">pmos-md-{d.isoformat()}</guid>
      <pubDate>{C.rfc822(now)}</pubDate>
      <description><![CDATA[
{body}      ]]></description>
    </item>

'''


def insert_feed(feed: str, item: str, n: int, replace: bool) -> str:
    existing = C.feed_items(feed)
    if n in existing:
        if not replace:
            raise SystemExit(f"feed.xml already has an item for issue #{n}; the feed is append-only (use --replace only for an unpublished issue)")
        i = feed.index(existing[n])
        return feed[:i] + item.strip("\n").lstrip(" ") + feed[i + len(existing[n]):]
    first = re.search(r"    <item>", feed)
    if not first:
        raise SystemExit("feed.xml has no <item> to insert above")
    return feed[:first.start()] + item + feed[first.start():]


# ───────────────────────── main ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(C.ROOT))
    ap.add_argument("--issue", required=True)
    ap.add_argument("--facts", required=True)
    ap.add_argument("--replace", action="store_true", help="re-render an issue that is not published yet")
    ap.add_argument("--now", help="ISO timestamp for the feed pubDate (tests)")
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    issue = C.load_json(a.issue)
    facts = C.load_json(a.facts)
    registry = C.load_json(root / "data" / "repos.json")
    sources = C.load_json(root / "scripts" / "sources.json")
    mcp = C.load_json(root / "data" / "mcp.json")
    state = C.load_json(root / "data" / "state.json")

    if not a.no_validate:
        errors, warnings, report = rules.validate_issue(issue, facts, registry, sources)
        errors += rules.validate_data(registry, mcp, state, facts)
        for w in warnings:
            print("warn: ", w)
        if errors:
            print("render refused:\n  - " + "\n  - ".join(errors))
            return 2

    m = build_model(issue, facts, registry, mcp, state)
    now = C.parse_any_datetime(a.now) if a.now else dt.datetime.now(dt.timezone.utc)

    index = render_index(C.read(root / "index.html"), m)
    arch = insert_archive_block(C.read(root / "archive.html"), archive_block(m), m["n"], a.replace)
    feed = insert_feed(C.read(root / "feed.xml"), feed_item(m, now), m["n"], a.replace)
    C.write(root / "index.html", index)
    C.write(root / "archive.html", arch)
    C.write(root / "feed.xml", feed)

    C.dump_json(root / "data" / f"stars-{m['n']:03d}.json",
                {"issue": m["n"], "date": m["date"].isoformat(),
                 "stars": {r["repo"]: r["stars"] for l in m["lanes"] for r in l["rows"]}})
    print(f"rendered issue #{m['n']} ({C.long_date(m['date'])}): {count_links(index)} links on the page, "
          f"{len(m['signal']['week'])}+{len(m['signal']['month'])} Signal items, "
          f"{sum(len(l['rows']) for l in m['lanes'])} repos")
    return 0


def insert_archive_block(arch: str, block: str, n: int, replace: bool) -> str:
    """New block goes directly above the newest existing block (below the marker comment)."""
    existing = C.archive_blocks(arch)
    block = block.strip("\n")
    if n in existing:
        if not replace:
            raise SystemExit(f"archive.html already has issue #{n}; archive blocks are append-only (use --replace only for an unpublished issue)")
        i = arch.index(existing[n])
        # existing[n] starts at '<section'; the two leading spaces before it belong to the file
        return arch[:i] + block.lstrip(" ") + arch[i + len(existing[n]):]
    first = re.search(r'<section class="issue" id="issue-\d+">', arch)
    if not first:
        raise SystemExit("archive.html has no issue block to insert above")
    return arch[:first.start()] + block.lstrip(" ") + "\n\n  " + arch[first.start():]


if __name__ == "__main__":
    sys.exit(main())
