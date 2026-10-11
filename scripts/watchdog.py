#!/usr/bin/env python3
"""Is the live site stale? Prints key=value lines (usable as $GITHUB_OUTPUT).

Runs on Mondays, independently of the publisher, so it catches every way a week can be missed: an
exhausted API balance, an outage, GitHub dropping a scheduled run, or GitHub switching a scheduled
workflow off after 60 days without repository activity (a failing job makes no commits).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys

import common as C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://pmos.md/")
    ap.add_argument("--today", help="YYYY-MM-DD (tests)")
    ap.add_argument("--html-file", help="read the page from a file instead of the network (tests)")
    a = ap.parse_args()
    today = C.parse_date(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    target = C.last_sunday(today)
    if a.html_file:
        body, code = C.read(a.html_file), 200
    else:
        code, _, body = C.fetch(a.url, retries=3)
    m = re.search(r'data-updated="([^"]*)"', body)
    if code != 200 or not m:
        print("stale=unknown")
        print(f"message=Could not read the live page (HTTP {code}); check https://pmos.md by hand.")
        return 0
    updated = dt.datetime.strptime(m.group(1), "%b %d, %Y").date()
    n = re.search(r"<strong>#(\d+)</strong>", body)
    stale = updated < target
    print(f"stale={'true' if stale else 'false'}")
    print(f"updated={updated.isoformat()}")
    print(f"target={target.isoformat()}")
    print(f"issue={n.group(1) if n else '?'}")
    print(f"days_behind={(target - updated).days}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
