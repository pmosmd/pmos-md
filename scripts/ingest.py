#!/usr/bin/env python3
"""Copy the model's data files into the workspace of the publishing job, and nothing else.

    python3 scripts/ingest.py <dir-with-data-files> <issue-number>

The model job has no write credentials; its only output is a handful of JSON files. The publishing job
takes exactly these names, requires them to parse as JSON, and ignores everything else, so the model can
change content but never code, workflows, HTML or history.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import common as C


def main() -> int:
    src, n = Path(sys.argv[1]), int(sys.argv[2])
    allowed = {f"issue-{n:03d}.json", "repos.json", "mcp.json", "state.json"}
    found = sorted(p for p in src.rglob("*") if p.is_file())
    ignored = [p.name for p in found if p.name not in allowed]
    if ignored:
        print(f"ignored (not an allowed name): {ignored}")
    wanted = [p for p in found if p.name in allowed]
    if f"issue-{n:03d}.json" not in {p.name for p in wanted}:
        print(f"no issue-{n:03d}.json in the model's output; nothing to publish")
        return 1
    for p in wanted:
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"{p.name} is not valid JSON: {e}")
            return 1
        shutil.copy(p, C.ROOT / "data" / p.name)
        print(f"ingested data/{p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
