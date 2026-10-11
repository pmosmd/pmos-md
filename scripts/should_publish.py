#!/usr/bin/env python3
"""Does this cycle need an issue? Prints key=value lines (usable as $GITHUB_OUTPUT).

Idempotency is date-based, never issue-number-based. Issue #33 was published by a Monday test run; the
next Sunday's real run computed the same ISO-week number, saw "#33 already published" and skipped, and
the site went a full week stale. Comparing dates cannot collide that way: publish only when the page's
data-updated date is older than the most recent Sunday on or before today (UTC).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import common as C


def decide(updated: dt.date | None, today: dt.date) -> tuple[bool, dt.date]:
    target = C.last_sunday(today)
    return (updated is None or updated < target), target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(C.ROOT))
    ap.add_argument("--today", help="YYYY-MM-DD (tests); default: today in UTC")
    a = ap.parse_args()
    root = Path(a.root)
    today = C.parse_date(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    st = C.index_state(C.read(root / "index.html"))
    publish, target = decide(st["updated"], today)
    blocks = C.archive_blocks(C.read(root / "archive.html"))
    nxt = max(blocks) + 1
    reason = (f"page last updated {st['updated']}, target Sunday {target}: " + ("publish" if publish else "already published this cycle"))
    print(f"publish={'true' if publish else 'false'}")
    print(f"date={target.isoformat()}")
    print(f"issue={nxt}")
    print(f"reason={reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
