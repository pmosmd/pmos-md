#!/usr/bin/env python3
"""Markdown receipt for a published issue: what went out under the editor's name, and how to undo it.

    python3 scripts/receipt.py --sha abc1234 [--report gate.md] > receipt.md
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import common as C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(C.ROOT))
    ap.add_argument("--sha", default="")
    ap.add_argument("--report")
    a = ap.parse_args()
    root = Path(a.root)
    blocks = C.archive_blocks(C.read(root / "archive.html"))
    n = max(blocks)
    block = blocks[n]
    date = re.search(r'issue-date">([^<]*)<', block).group(1)

    def pick(kicker: str):
        m = re.search(rf'pick-kicker">{kicker}[^<]*</div>\s*<a href="([^"]*)"[^>]*>([^<]*)</a>', block)
        return (html.unescape(C.strip_utm(m.group(1))), html.unescape(m.group(2))) if m else (None, None)

    def group(head: str) -> list[str]:
        m = re.search(rf'grp-head">{head}</div>(.*?)(?=<div class="grp">|</section>)', block, re.S)
        out = []
        for mm in re.finditer(r'<a class="row-link" href="([^"]*)"[^>]*>([^<]*)</a>.*?<div class="row-src">([^<]*)</div>', m.group(1) if m else "", re.S):
            out.append(f"- [{html.unescape(mm.group(2))}]({html.unescape(C.strip_utm(mm.group(1)))}) ({html.unescape(mm.group(3)).replace(' · ', ', ')})")
        return out

    hero_url, hero_title = pick("editor's pick")
    sp_url, sp_title = pick("★ spotlight")
    lines = [f"## Issue #{n} is live: {date}",
             "",
             f"[pmos.md](https://pmos.md) · [archive entry](https://pmos.md/archive.html#issue-{n})" + (f" · commit `{a.sha[:7]}`" if a.sha else ""),
             "",
             f"**Editor's pick:** [{hero_title}]({hero_url})",
             f"**Spotlight:** [{sp_title}]({sp_url})",
             "",
             "**Signal, this week**", *group("signal — this week"),
             "",
             "**Signal, also worth your time**", *group("signal — also worth your time"),
             ""]
    if a.report and Path(a.report).exists():
        lines += [C.read(a.report).strip(), ""]
    lines += ["To undo: `git revert " + (a.sha[:7] if a.sha else "<commit>") + "` and push, or ask Claude to revert issue #" + str(n) + ".",
              "", "_Posted by the weekly publisher. This issue closes itself._"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
