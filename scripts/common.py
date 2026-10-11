"""Shared helpers for the pmos.md weekly pipeline. Standard library only.

Design rule: everything that can be decided by code is decided by code. The model
only writes editorial text (see scripts/SCHEMA.md); titles, dates, star counts,
paywall flags, UTM tags, counts and HTML all come from here.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Links that never get UTM tags (CLAUDE.md, step 6).
INTERNAL_HOSTS = {"pmos.md", "pmosmd.goatcounter.com", "gc.zgo.at"}
INTERNAL_PATHS = ("github.com/pmosmd/pmos-md",)


# ───────────────────────── files ─────────────────────────
def read(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: Path | str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def load_json(path: Path | str, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def dump_json(path: Path | str, obj) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ───────────────────────── text / html ─────────────────────────
def esc(s: str) -> str:
    """Escape for an HTML text node."""
    return html.escape(s, quote=False)


def esc_attr(s: str) -> str:
    """Escape for a double-quoted HTML attribute."""
    return html.escape(s, quote=True)


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def strip_tags(s: str) -> str:
    return squash(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


# ───────────────────────── urls ─────────────────────────
def norm_url(u: str) -> str:
    """Identity of a link for de-duplication: host (no www) + path, no scheme/query/fragment."""
    p = urllib.parse.urlsplit(html.unescape((u or "").strip()))
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/") or "/"
    return f"{host}{path}"


def host_of(u: str) -> str:
    h = urllib.parse.urlsplit(html.unescape(u)).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def is_internal(u: str) -> bool:
    n = norm_url(u)
    if host_of(u) in INTERNAL_HOSTS:
        return True
    return any(n.startswith(p) for p in INTERNAL_PATHS)


def strip_utm(u: str) -> str:
    p = urllib.parse.urlsplit(html.unescape(u))
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def utm(u: str, issue: int) -> str:
    """URL with the pmos.md UTM tags, ready for an HTML/XML attribute (&amp; separators)."""
    base = strip_utm(u)
    sep = "&" if "?" in base else "?"
    tagged = f"{base}{sep}utm_source=pmos.md&utm_medium=referral&utm_campaign=issue-{issue}"
    return esc_attr(tagged)


def fetch(url: str, timeout: int = 25, retries: int = 2, accept: str | None = None):
    """GET with a browser UA. Returns (http_status, final_url, body). Status 0 = transport failure."""
    last = (0, url, "")
    for attempt in range(retries + 1):
        cmd = ["curl", "-sL", "--compressed", "--max-time", str(timeout), "-A", UA,
               "-w", "\n__PMOS__%{http_code} %{url_effective}"]
        if accept:
            cmd += ["-H", f"Accept: {accept}"]
        cmd.append(url)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            last = (0, url, "")
            continue
        body, _, tail = p.stdout.rpartition("\n__PMOS__")
        parts = tail.strip().split(" ", 1)
        try:
            code = int(parts[0])
        except ValueError:
            code = 0
        last = (code, parts[1] if len(parts) > 1 else url, body)
        if code in (200, 404, 410):
            break
        time.sleep(1.5 * (attempt + 1))
    return last


def gh_api(path: str, **params):
    """GitHub REST via the gh CLI (uses GH_TOKEN / local login). Returns parsed JSON or None."""
    cmd = ["gh", "api", "-X", "GET", path]
    for k, v in params.items():
        cmd += ["-f", f"{k}={v}"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


# ───────────────────────── dates ─────────────────────────
def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def parse_any_datetime(s: str | None) -> dt.datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(s)
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def last_sunday(d: dt.date) -> dt.date:
    """Most recent Sunday on or before d."""
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def short_date(d: dt.date) -> str:          # Oct 8
    return f"{MONTHS[d.month - 1]} {d.day}"


def long_date(d: dt.date) -> str:           # Oct 11, 2026
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def lower_date(d: dt.date) -> str:          # oct 11, 2026
    return long_date(d).lower()


def rfc822(d: dt.datetime) -> str:
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


def fmt_stars(n: int) -> str:
    """392k / 60.7k / 24k / 950 — one decimal below 100k, none above."""
    if n >= 100_000:
        return f"{round(n / 1000)}k"
    if n >= 1_000:
        s = f"{n / 1000:.1f}"
        return (s[:-2] if s.endswith(".0") else s) + "k"
    return str(n)


def stars_value(s: str) -> float:
    """Inverse of fmt_stars (approximate): '26.9k' -> 26900."""
    s = s.strip().lower()
    return float(s[:-1]) * 1000 if s.endswith("k") else float(s)


# ───────────────────────── page metadata ─────────────────────────
def meta_content(doc: str, key: str, attr: str = "property") -> str | None:
    for pat in (rf'<meta[^>]+{attr}=["\']{re.escape(key)}["\'][^>]*content=["\']([^"\']*)["\']',
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*{attr}=["\']{re.escape(key)}["\']'):
        m = re.search(pat, doc, re.I)
        if m:
            return html.unescape(m.group(1))
    return None


def page_meta(doc: str) -> dict:
    """Title, description, canonical URL, publish datetime and paywall hint from a fetched page."""
    out = {"title": None, "description": None, "canonical": None, "published": None, "paywall": "unknown"}
    t = meta_content(doc, "og:title")
    if not t:
        m = re.search(r"<title[^>]*>([^<]*)</title>", doc, re.I)
        t = html.unescape(m.group(1)) if m else None
    out["title"] = squash(t) if t else None
    out["description"] = squash(meta_content(doc, "og:description") or meta_content(doc, "description", "name") or "")
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', doc, re.I)
    out["canonical"] = html.unescape(m.group(1)) if m else None

    pub = meta_content(doc, "article:published_time")
    free = None
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', doc, re.S | re.I):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            m1 = re.search(r'"datePublished"\s*:\s*"([^"]+)"', block)
            if m1 and not pub:
                pub = m1.group(1)
            m2 = re.search(r'"isAccessibleForFree"\s*:\s*"?(true|false)"?', block, re.I)
            if m2:
                free = m2.group(1).lower() == "true"
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict):
                if not pub and node.get("datePublished"):
                    pub = str(node["datePublished"])
                if "isAccessibleForFree" in node:
                    free = str(node["isAccessibleForFree"]).lower() == "true"
    if not pub:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', doc)
        pub = m.group(1) if m else None
    out["published"] = pub

    # Substack embeds the audience flag in its preloaded JSON.
    a = re.search(r'\\?"audience\\?":\\?"(everyone|only_paid|only_free|founding)\\?"', doc)
    if a:
        out["paywall"] = "paid" if a.group(1) in ("only_paid", "founding") else "free"
    elif free is not None:
        out["paywall"] = "free" if free else "paid"
    # Some free newsletters outline locked sections with a lock emoji; call those partly paid.
    if out["paywall"] == "free" and ("\U0001F512" in doc or "\\ud83d\\udd12" in doc.lower()):
        out["paywall"] = "partial"
    return out


# ───────────────────────── archive / feed parsing ─────────────────────────
ISSUE_RE = re.compile(r'<section class="issue" id="issue-(\d+)">.*?</section>', re.S)
ITEM_RE = re.compile(r"<item>.*?</item>", re.S)


def archive_blocks(archive_html: str) -> dict[int, str]:
    """Issue number -> exact block text, in file order (newest first)."""
    return {int(m.group(1)): m.group(0) for m in ISSUE_RE.finditer(archive_html)}


def feed_items(feed_xml: str) -> dict[int, str]:
    out = {}
    for m in ITEM_RE.finditer(feed_xml):
        n = re.search(r"<title>Issue #(\d+)", m.group(0))
        if n:
            out[int(n.group(1))] = m.group(0)
    return out


def hrefs(chunk: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="(https?://[^"]*)"', chunk)]


def spotlight_of(block: str) -> str | None:
    """Repo (owner/name) featured as the spotlight in an archive block."""
    for m in re.finditer(r'<div class="pick[^"]*">\s*<div class="pick-kicker">([^<]*)</div>\s*<a [^>]*href="([^"]*)"', block):
        if "spotlight" in m.group(1).lower():
            p = urllib.parse.urlsplit(html.unescape(m.group(2)))
            return "/".join(p.path.strip("/").split("/")[:2])
    return None


def used_urls(root: Path, exclude_issue: int | None = None) -> set[str]:
    """Normalized URLs of every article/repo already published in the archive."""
    seen: set[str] = set()
    arch = read(root / "archive.html")
    for n, block in archive_blocks(arch).items():
        if n == exclude_issue:
            continue
        for h in hrefs(block):
            seen.add(norm_url(h))
    return seen


def index_state(index_html: str) -> dict:
    m = re.search(r'data-updated="([^"]*)"', index_html)
    updated = dt.datetime.strptime(m.group(1), "%b %d, %Y").date() if m else None
    n = re.search(r'<strong>#(\d+)</strong>', index_html)
    return {"updated": updated, "issue": int(n.group(1)) if n else None}
