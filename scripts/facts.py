#!/usr/bin/env python3
"""Collect the verified facts a weekly issue is written from. No model involved.

    python3 scripts/facts.py --date 2026-10-11 --out facts.json

Everything the model is allowed to cite lives in this file: article titles, dates
(read from page metadata, never from search rank), paywall flags, GitHub stars,
releases from the last 7 days, and the spotlight rotation state. The renderer and
the gate re-use the same data, so a link or number that is not here cannot ship.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import common as C

NS = {"atom": "http://www.w3.org/2005/Atom"}
HN_QUERIES = ["product management", "AI agents product", "MCP server", "Claude Code"]


# ───────────────────────── articles ─────────────────────────
def parse_feed(src: dict, body: str) -> list[dict]:
    items: list[dict] = []
    src_domains = set(src.get("domains", []))
    if src["type"] == "mtp-json":
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return items
        for r in data.get("results", []):
            d = r.get("data", {})
            if d.get("url") and d.get("title"):
                items.append({"title": C.squash(d["title"]), "link": d["url"], "date": None, "summary": ""})
        return items
    try:
        root = ET.fromstring(body.encode("utf-8", "replace"))
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        items.append({"title": C.squash(it.findtext("title") or ""), "link": (it.findtext("link") or "").strip(),
                      "date": C.parse_any_datetime(it.findtext("pubDate")),
                      "summary": C.strip_tags(it.findtext("description") or "")[:500]})
    for en in root.findall(".//atom:entry", NS):
        links = [l.get("href") for l in en.findall("atom:link", NS) if l.get("href")]
        # Link-blog feeds (Daring Fireball) point `alternate` at the external article; keep the site's own permalink.
        own = [h for h in links if C.host_of(h) in (src_domains or ())]
        link = own[0] if own else next((l.get("href") for l in en.findall("atom:link", NS) if l.get("rel") in (None, "alternate")), "")
        when = en.findtext("atom:published", namespaces=NS) or en.findtext("atom:updated", namespaces=NS)
        items.append({"title": C.squash(en.findtext("atom:title", namespaces=NS) or ""), "link": link,
                      "date": C.parse_any_datetime(when),
                      "summary": C.strip_tags(en.findtext("atom:summary", namespaces=NS) or "")[:500]})
    return items


def load_feed(src: dict, D: dt.date) -> tuple[list[dict], str | None]:
    code, _, body = C.fetch(src["feed"], accept="application/rss+xml, application/atom+xml, application/xml, text/xml, application/json, */*")
    if code != 200:
        return [], f"{src['id']}: feed HTTP {code}"
    items = parse_feed(src, body)
    if not items:
        return [], f"{src['id']}: feed parsed to 0 items"
    floor = dt.datetime.combine(D - dt.timedelta(days=31), dt.time.min, tzinfo=dt.timezone.utc)
    ceil = dt.datetime.combine(D + dt.timedelta(days=1), dt.time.max, tzinfo=dt.timezone.utc)
    keep = [i for i in items if i["link"] and (i["date"] is None or floor <= i["date"] <= ceil)]
    keep.sort(key=lambda i: i["date"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc), reverse=True)
    for i in keep:
        i["src"] = src
    return keep[: src.get("max_items", 12)], None


def path_date(url: str) -> dt.date | None:
    m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", url)
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def inspect(item: dict, D: dt.date, used: set[str], domain_kind: dict[str, str]) -> dict:
    code, final, body = C.fetch(item["link"], retries=1)
    out = {"title": item["title"], "url": C.strip_utm(item["link"]), "http": code, "source": item["src"]["id"] if item.get("src") else "hn",
           "via": item.get("via", "feed"), "kind": None, "paywall": "unknown", "date": None, "date_source": None,
           "date_confirmed": False, "excerpt": item.get("summary", ""), "note": (item.get("src") or {}).get("note", "")}
    if code != 200:
        return out
    m = C.page_meta(body)
    canon = m["canonical"]
    if canon and C.host_of(canon) == C.host_of(final):
        out["url"] = C.strip_utm(canon)
    else:
        out["url"] = C.strip_utm(final)
    out["title"] = m["title"] or item["title"]
    out["excerpt"] = (m["description"] or item.get("summary") or "")[:500]
    out["paywall"] = m["paywall"]
    host = C.host_of(out["url"])
    out["domain"] = host
    out["kind"] = domain_kind.get(host, "general")
    pub = C.parse_any_datetime(m["published"])
    meta_date = pub.date() if pub else None
    feed_date = item["date"].date() if item.get("date") else None
    if meta_date:
        out["date"], out["date_source"] = meta_date, "meta"
        out["date_confirmed"] = feed_date is None or abs((meta_date - feed_date).days) <= 2
        if not out["date_confirmed"]:
            out["note"] = (out["note"] + " feed and page dates differ").strip()
    elif feed_date:
        out["date"], out["date_source"] = feed_date, "feed"
        out["date_confirmed"] = path_date(out["url"]) == feed_date   # e.g. daringfireball.net/linked/2026/10/05/...
    if out["date"]:
        age = (D - out["date"]).days
        out["age_days"] = age
        out["window"] = "future" if age < 0 else "week" if age <= 7 else "month" if age <= 30 else "older"
        out["date"] = out["date"].isoformat()
    out["used"] = C.norm_url(out["url"]) in used
    out["id"] = hashlib.sha1(C.norm_url(out["url"]).encode()).hexdigest()[:8]
    return out


def hn_items(D: dt.date) -> list[dict]:
    since = int(dt.datetime.combine(D - dt.timedelta(days=7), dt.time.min, tzinfo=dt.timezone.utc).timestamp())
    seen, out = set(), []
    for q in HN_QUERIES:
        code, _, body = C.fetch("https://hn.algolia.com/api/v1/search?" + "&".join([
            "tags=story", f"query={q.replace(' ', '+')}", f"numericFilters=created_at_i>{since},points>150", "hitsPerPage=6"]), retries=1)
        if code != 200:
            continue
        try:
            hits = json.loads(body).get("hits", [])
        except json.JSONDecodeError:
            continue
        for h in hits:
            url = h.get("url")
            if url and url not in seen and "github.com" not in url:
                seen.add(url)
                out.append({"title": C.squash(h.get("title", "")), "link": url, "date": None, "summary": "", "via": "hn",
                            "hn_points": h.get("points"), "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}"})
    return out[:8]


def collect_articles(D: dt.date, sources: dict, used: set[str], warnings: list[str]) -> list[dict]:
    domain_kind = {d: s["kind"] for s in sources["feeds"] for d in s["domains"]}
    with cf.ThreadPoolExecutor(6) as ex:
        loaded = list(ex.map(lambda s: load_feed(s, D), sources["feeds"]))
    items: list[dict] = []
    for got, warn in loaded:
        items += got
        if warn:
            warnings.append(warn)
    known_hosts = set(domain_kind)
    for h in hn_items(D):
        if C.host_of(h["link"]) not in known_hosts:
            items.append(h)
    uniq, seen = [], set()
    for it in items:
        k = C.norm_url(it["link"])
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda i: inspect(i, D, used, domain_kind), uniq))
    arts = []
    for r in results:
        if r["http"] != 200:
            warnings.append(f"{r['source']}: {r['url']} returned HTTP {r['http']}")
            continue
        if r.get("window") in ("week", "month"):
            arts.append(r)
    arts.sort(key=lambda a: (a["date"] or ""), reverse=True)
    return arts


# ───────────────────────── repos ─────────────────────────
def release_facts(repo: str, D: dt.date) -> list[dict]:
    rels = C.gh_api(f"repos/{repo}/releases", per_page=8) or []
    out = []
    for r in rels:
        if r.get("draft") or not r.get("published_at"):
            continue
        day = C.parse_any_datetime(r["published_at"]).date()
        age = (D - day).days
        if not (0 <= age <= 7):
            continue
        body = r.get("body") or ""
        body = re.split(r"\n#+\s*Thanks", body, maxsplit=1)[0]
        links = [u for u in re.findall(r"https?://[^\s)>\]]+", body)
                 if not re.match(r"https://github\.com/[^/]+/?$", u)][:4]
        out.append({"tag": r["tag_name"], "name": r.get("name"), "date": day.isoformat(), "prerelease": bool(r.get("prerelease")),
                    "url": r.get("html_url"), "body_head": C.squash(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body))[:1100], "links": links})
    return out


def latest_snapshot(root: Path) -> dict:
    snaps = sorted((root / "data").glob("stars-*.json"))
    return C.load_json(snaps[-1], {}) if snaps else {}


def repo_facts(entry: dict, D: dt.date, prev: dict) -> dict:
    name = entry["repo"]
    r = C.gh_api(f"repos/{name}") or {}
    pushed = C.parse_any_datetime(r.get("pushed_at")) if r else None
    out = {"repo": name, "lane": entry["lane"], "found": bool(r), "stars": r.get("stargazers_count"), "archived": r.get("archived"),
           "pushed_at": r.get("pushed_at"), "canonical": bool(entry.get("canonical")), "description": r.get("description"),
           "releases_7d": release_facts(name, D) if r else []}
    out["stale"] = bool(pushed and (D - pushed.date()).days > 90 and not entry.get("canonical"))
    out["hook"] = next((x for x in out["releases_7d"] if not x["prerelease"]), None)
    if prev.get("stars", {}).get(name) and out["stars"]:
        out["stars_prev"] = prev["stars"][name]
        out["stars_delta"] = out["stars"] - prev["stars"][name]
    return out


def discover(D: dt.date, known: set[str]) -> list[dict]:
    d30 = (D - dt.timedelta(days=30)).isoformat()
    queries = [f"topic:product-management pushed:>{d30} stars:>200",
               f'"product manager" in:description pushed:>{d30} stars:>300',
               f'"product requirements" OR PRD in:description pushed:>{d30} stars:>200',
               f'"user research" OR "product discovery" in:description pushed:>{d30} stars:>300',
               f'"product management" in:description,topics pushed:>{d30} stars:>500']
    found: dict[str, dict] = {}
    for q in queries:
        res = C.gh_api("search/repositories", q=q, sort="stars", order="desc", per_page=8) or {}
        for it in res.get("items", []):
            n = it["full_name"]
            if n.lower() in known or n in found or not it.get("description"):
                continue
            found[n] = {"repo": n, "stars": it["stargazers_count"], "created_at": it["created_at"][:10], "pushed_at": it["pushed_at"][:10],
                        "description": it["description"][:160], "topics": it.get("topics", [])[:6], "url": it["html_url"]}
    return sorted(found.values(), key=lambda x: -x["stars"])[:10]


def spotlight_state(root: Path, registry: dict, repos: list[dict], exclude: int | None = None) -> dict:
    blocks = {n: b for n, b in C.archive_blocks(C.read(root / "archive.html")).items() if n != exclude}
    lane_of = {r["repo"]: r["lane"] for r in registry["repos"]}
    history = [{"issue": n, "repo": C.spotlight_of(b)} for n, b in sorted(blocks.items(), reverse=True)[:8]]
    recent = {h["repo"] for h in history[:6] if h["repo"]}
    last_by_lane = {lane: next((h["issue"] for h in history if lane_of.get(h["repo"]) == lane), None) for lane in registry["lanes"]}
    eligible = [{"repo": r["repo"], "lane": r["lane"], "hook": f"{r['hook']['tag']} ({r['hook']['date']})"}
                for r in repos if r["hook"] and r["repo"] not in recent and not r["archived"]]
    lanes_with = {e["lane"] for e in eligible}
    order = sorted(lanes_with, key=lambda l: (last_by_lane[l] if last_by_lane[l] is not None else -1))
    return {"history": history, "recent_repos_excluded": sorted(recent), "last_spotlight_issue_by_lane": last_by_lane,
            "eligible": eligible, "suggested_lane": order[0] if order else None}


# ───────────────────────── main ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(C.ROOT))
    ap.add_argument("--date", help="issue date (a Sunday); default: most recent Sunday (UTC)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rebuild", type=int, help="re-make this already-rendered issue: ignore its own block when de-duplicating")
    a = ap.parse_args()
    root = Path(a.root)
    D = C.parse_date(a.date) if a.date else C.last_sunday(dt.datetime.now(dt.timezone.utc).date())
    sources = C.load_json(root / "scripts" / "sources.json")
    registry = C.load_json(root / "data" / "repos.json")
    state = C.load_json(root / "data" / "state.json", {})
    warnings: list[str] = []

    used = C.used_urls(root, exclude_issue=a.rebuild)
    articles = collect_articles(D, sources, used, warnings)
    prev = latest_snapshot(root)
    with cf.ThreadPoolExecutor(4) as ex:
        repos = list(ex.map(lambda e: repo_facts(e, D, prev), registry["repos"]))
    for r in repos:
        if not r["found"]:
            warnings.append(f"{r['repo']}: GitHub API returned nothing")
        if r["stale"]:
            warnings.append(f"{r['repo']}: no push for 90+ days, candidate for retirement")
        if r["archived"]:
            warnings.append(f"{r['repo']}: archived")
    known = {r["repo"].lower() for r in registry["repos"]} | {x["repo"].lower() for x in registry.get("retired", []) + registry.get("rejected", [])}
    blocks = {n: b for n, b in C.archive_blocks(C.read(root / "archive.html")).items() if n != a.rebuild}
    month = f"{D.year}-{D.month:02d}"
    facts = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "issue": max(blocks) + 1, "date": D.isoformat(),
        "windows": {"week": f"{(D - dt.timedelta(days=7)).isoformat()}..{D.isoformat()}",
                    "month": f"{(D - dt.timedelta(days=30)).isoformat()}..{(D - dt.timedelta(days=8)).isoformat()}"},
        "mode": {"repo_audit_due": state.get("last_repo_audit") != month,
                 "quarterly_review_due": D.month in (1, 4, 7, 10) and state.get("last_quarterly_review") != month},
        "previous_issue": max(blocks),
        "articles": articles, "repos": repos, "candidate_repos": discover(D, known),
        "spotlight": spotlight_state(root, registry, repos, a.rebuild), "warnings": warnings,
    }
    Path(a.out).write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    wk = sum(1 for x in articles if x["window"] == "week")
    print(f"facts: issue #{facts['issue']} for {D}: {wk} articles this week, {len(articles) - wk} in the month window, "
          f"{len(repos)} repos, {len(facts['candidate_repos'])} discovery candidates, {len(warnings)} warnings -> {a.out}")
    for w in warnings:
        print("  warn:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
