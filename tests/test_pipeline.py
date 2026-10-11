"""Offline tests for the weekly pipeline: facts -> issue json -> render -> gate.

They render a synthetic next issue (fake URLs, no network) into a throwaway git copy of the real
index.html / archive.html / feed.xml, then try to break it. Run: python3 -m unittest discover -s tests -v
"""
import copy
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common as C          # noqa: E402
import should_publish       # noqa: E402


def run(args, cwd, **kw):
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, **kw)


def make_facts(root: Path, n: int, day: dt.date) -> dict:
    registry = C.load_json(root / "data" / "repos.json")
    arts = []

    def art(i, window, kind="pm", paywall="free", used=False, age=2):
        d = day - dt.timedelta(days=age)
        return {"id": f"a{i}", "title": f"Synthetic article {i} & friends", "url": f"https://pm{i}.example-pm.test/p/{i}",
                "domain": f"pm{i}.example-pm.test", "source": f"src{i}", "kind": kind, "paywall": paywall, "date": d.isoformat(),
                "age_days": age, "window": window, "date_confirmed": True, "used": used, "http": 200, "excerpt": "", "note": ""}
    for i in range(1, 5):
        arts.append(art(i, "week", age=i))
    for i in range(5, 9):
        arts.append(art(i, "month", age=10 + i))
    arts.append(art(9, "week", age=1))                       # hero
    arts.append(art(10, "week", used=True, age=3))           # already published once
    arts.append(art(11, "week", kind="general", paywall="paid", age=2))
    repos = []
    for r in registry["repos"]:
        rel = [{"tag": "v9.9.9", "name": "v9.9.9", "date": day.isoformat(), "prerelease": False, "url": "https://example-pm.test/r", "body_head": "", "links": []}]
        repos.append({"repo": r["repo"], "lane": r["lane"], "found": True, "stars": 5000, "archived": False, "pushed_at": day.isoformat(),
                      "canonical": False, "description": "", "releases_7d": rel if r is registry["repos"][0] else [], "stale": False,
                      "hook": rel[0] if r is registry["repos"][0] else None})
    return {"issue": n, "date": day.isoformat(), "windows": {}, "mode": {}, "articles": arts, "repos": repos, "candidate_repos": [],
            "spotlight": {"history": [], "recent_repos_excluded": [], "last_spotlight_issue_by_lane": {}, "eligible": [], "suggested_lane": None},
            "warnings": []}


def make_issue(root: Path, n: int, day: dt.date) -> dict:
    first = C.load_json(root / "data" / "repos.json")["repos"][0]["repo"]
    take = "A grounded one-line takeaway that is long enough to pass the length rule."
    return {"issue": n, "date": day.isoformat(), "note": "Synthetic issue for tests.",
            "hero": {"url": "https://pm9.example-pm.test/p/9", "quote": "A synthetic editor's pick quote that is comfortably longer than sixty characters.", "why": "Because it is a test"},
            "spotlight": {"repo": first, "tags": ["t1"], "text": "A synthetic spotlight paragraph that explains this week's release in enough words to pass the minimum length rule."},
            "signal": {"week": [{"url": f"https://pm{i}.example-pm.test/p/{i}", "takeaway": take} for i in range(1, 5)],
                       "month": [{"url": f"https://pm{i}.example-pm.test/p/{i}", "takeaway": take} for i in range(5, 9)]},
            "repo_news": {first: {"release": "v9.9.9", "text": "adds a synthetic feature for tests."}}}


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmos-test-"))
        for f in ("index.html", "archive.html", "feed.xml"):
            shutil.copy(ROOT / f, self.tmp / f)
        for d in ("data", "scripts"):
            shutil.copytree(ROOT / d, self.tmp / d, ignore=shutil.ignore_patterns("__pycache__", "issue-*.json", "stars-*.json") if d == "data" else shutil.ignore_patterns("__pycache__"))
        st = C.index_state(C.read(self.tmp / "index.html"))
        self.n = max(C.archive_blocks(C.read(self.tmp / "archive.html"))) + 1
        self.day = st["updated"] + dt.timedelta(days=7)
        self.facts = make_facts(self.tmp, self.n, self.day)
        self.issue = make_issue(self.tmp, self.n, self.day)
        subprocess.run("git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm base", shell=True, cwd=self.tmp, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self):
        C.dump_json(self.tmp / "facts.json", self.facts)
        C.dump_json(self.tmp / "data" / f"issue-{self.n:03d}.json", self.issue)

    def render(self, *extra):
        self.write()
        return run(["scripts/render.py", "--issue", f"data/issue-{self.n:03d}.json", "--facts", "facts.json", "--now", "2030-01-06T08:00:00Z", *extra], self.tmp)

    def gate(self):
        return run(["scripts/selfcheck.py", "--offline", "--base", "HEAD", "--facts", "facts.json"], self.tmp)

    # ── happy path ──
    def test_render_then_gate_passes(self):
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        g = self.gate()
        self.assertEqual(g.returncode, 0, g.stdout)
        self.assertIn("CLEAR TO PUBLISH", g.stdout)

    def test_replace_is_stable(self):
        self.assertEqual(self.render().returncode, 0)
        first = [C.read(self.tmp / f) for f in ("index.html", "archive.html", "feed.xml")]
        self.assertEqual(self.render("--replace").returncode, 0)
        self.assertEqual(first, [C.read(self.tmp / f) for f in ("index.html", "archive.html", "feed.xml")])

    def test_second_render_without_replace_refuses(self):
        self.assertEqual(self.render().returncode, 0)
        r = self.render()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("append-only", r.stdout + r.stderr)

    def test_older_blocks_are_untouched(self):
        before = C.archive_blocks(C.read(self.tmp / "archive.html"))
        self.assertEqual(self.render().returncode, 0)
        after = C.archive_blocks(C.read(self.tmp / "archive.html"))
        for k, v in before.items():
            self.assertEqual(after[k], v)
        self.assertEqual(next(iter(after)), self.n)

    # ── what the model cannot do ──
    def test_titles_come_from_facts_not_the_model(self):
        self.issue["signal"]["week"][0]["title"] = "EVIL TITLE"
        self.assertEqual(self.render().returncode, 0)
        out = C.read(self.tmp / "index.html")
        self.assertNotIn("EVIL TITLE", out)
        self.assertIn("Synthetic article 1 &amp; friends", out)

    def test_html_in_takeaway_is_escaped(self):
        self.issue["signal"]["week"][0]["takeaway"] = "<script>alert(1)</script> padded out so that it is long enough to pass."
        self.assertEqual(self.render().returncode, 0)
        self.assertNotIn("<script>alert(1)", C.read(self.tmp / "index.html"))

    def test_link_not_in_facts_is_rejected(self):
        self.issue["signal"]["week"][0]["url"] = "https://evil.example-pm.test/not-verified"
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("not in the verified facts", r.stdout)

    def test_reused_article_is_rejected(self):
        self.issue["signal"]["week"][0]["url"] = "https://pm10.example-pm.test/p/10"
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("already published", r.stdout)

    def test_article_in_wrong_window_is_rejected(self):
        self.issue["signal"]["week"][0], self.issue["signal"]["month"][0] = self.issue["signal"]["month"][0], self.issue["signal"]["week"][0]
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("belongs in", r.stdout)

    def test_paid_hero_is_rejected(self):
        self.issue["hero"]["url"] = "https://pm11.example-pm.test/p/11"
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("hero", r.stdout)

    def test_stale_repo_blocks_publishing(self):
        self.facts["repos"][1]["stale"] = True
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("retire", r.stdout)

    def test_spotlight_needs_a_this_week_release(self):
        self.issue["spotlight"]["repo"] = self.facts["repos"][2]["repo"]
        r = self.render()
        self.assertEqual(r.returncode, 2)
        self.assertIn("no stable release", r.stdout)

    # ── the gate catches tampering ──
    def test_gate_catches_edited_history(self):
        self.assertEqual(self.render().returncode, 0)
        arch = C.read(self.tmp / "archive.html")
        old = max(k for k in C.archive_blocks(arch) if k != self.n)
        block = C.archive_blocks(arch)[old]
        C.write(self.tmp / "archive.html", arch.replace(block, block.replace("issue #", "Issue #", 1)))
        g = self.gate()
        self.assertEqual(g.returncode, 1)
        self.assertIn("archive blocks changed or missing", g.stdout)

    def test_gate_catches_missing_utm(self):
        self.assertEqual(self.render().returncode, 0)
        doc = C.read(self.tmp / "index.html")
        doc = doc.replace("?utm_source=pmos.md&amp;utm_medium=referral&amp;utm_campaign=issue-%d" % self.n, "", 1)
        C.write(self.tmp / "index.html", doc)
        self.assertEqual(self.gate().returncode, 1)

    def test_gate_catches_wrong_count_badge(self):
        self.assertEqual(self.render().returncode, 0)
        doc = C.read(self.tmp / "index.html").replace("8 · filtered", "9 · filtered")
        C.write(self.tmp / "index.html", doc)
        g = self.gate()
        self.assertEqual(g.returncode, 1)
        self.assertIn("badge", g.stdout)

    def test_gate_catches_placeholder_href(self):
        self.assertEqual(self.render().returncode, 0)
        C.write(self.tmp / "index.html", C.read(self.tmp / "index.html").replace('href="/archive.html"', 'href="#"', 1))
        self.assertEqual(self.gate().returncode, 1)

    def test_gate_catches_mismatched_heading(self):
        self.assertEqual(self.render().returncode, 0)
        doc = C.read(self.tmp / "index.html").replace("</h3>", "</h2>", 1)
        C.write(self.tmp / "index.html", doc)
        self.assertEqual(self.gate().returncode, 1)

    # ── helpers ──
    def test_star_formatting(self):
        for n, s in ((391688, "392k"), (252774, "253k"), (60674, "60.7k"), (24002, "24k"), (16385, "16.4k"), (7253, "7.3k"), (1000, "1k"), (950, "950")):
            self.assertEqual(C.fmt_stars(n), s)

    def test_idempotency_is_date_based(self):
        d = dt.date
        self.assertEqual(should_publish.decide(d(2026, 10, 11), d(2026, 10, 12))[0], False)   # Monday after a Sunday issue
        self.assertEqual(should_publish.decide(d(2026, 10, 11), d(2026, 10, 18))[0], True)    # next Sunday
        self.assertEqual(should_publish.decide(d(2026, 8, 10), d(2026, 8, 16))[0], True)      # the #33 collision: Monday test run, then Sunday
        self.assertEqual(should_publish.decide(d(2026, 10, 11), d(2026, 10, 11))[0], False)   # re-run on the same Sunday

    def test_last_sunday(self):
        self.assertEqual(C.last_sunday(dt.date(2026, 10, 11)), dt.date(2026, 10, 11))
        self.assertEqual(C.last_sunday(dt.date(2026, 10, 17)), dt.date(2026, 10, 11))
        self.assertEqual(C.last_sunday(dt.date(2026, 10, 12)), dt.date(2026, 10, 11))

    def test_watchdog_flags_a_missed_week(self):
        updated = C.index_state(C.read(ROOT / "index.html"))["updated"]      # a Sunday
        for today, stale in ((updated + dt.timedelta(days=1), "false"), (updated + dt.timedelta(days=8), "true")):
            r = run(["scripts/watchdog.py", "--html-file", "index.html", "--today", today.isoformat()], ROOT)
            self.assertIn(f"stale={stale}", r.stdout)


if __name__ == "__main__":
    unittest.main()
