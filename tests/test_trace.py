import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_report  # noqa: E402
import gen_synthetic  # noqa: E402
import gen_synthetic_b  # noqa: E402
from ashiato import brief as brief_mod  # noqa: E402
from ashiato.trace import build_trace  # noqa: E402


def built(gen, site, name, example):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    gen.write_all(root / "d")
    brief, drafts = build_report.build(root / "d" / "before.ndjson", root / "d" / site, name, root / "o",
                                       response=ROOT / "examples" / example / "claude_response.json")
    html = (root / "o" / "report.html").read_text(encoding="utf-8")
    tmp.cleanup()
    return brief, drafts, html


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = built(gen_synthetic, "site/before", "雪待荘", "ryokan")
        cls.b = built(gen_synthetic_b, "site", "かきわけ", "readnote")

    def test_errors_come_in_order_of_size_with_verdicts(self):
        brief, drafts, _ = self.a
        steps = build_trace(brief, drafts)
        titles = [s["title"] for s in steps]
        self.assertEqual(titles[0], "全体を数える")
        self.assertLess(titles.index("/access が読めなかった理由を調べる"), titles.index("/plans/winter が読めなかった理由を調べる"))
        verdict = {s["title"]: s["verdict"] for s in steps}
        self.assertIn("アクセス", verdict["/access が読めなかった理由を調べる"])
        self.assertIn("転送", verdict["/plans/winter が読めなかった理由を調べる"])

    def test_no_verdict_is_invented(self):
        brief, drafts, _ = self.a
        for s in build_trace(brief, drafts):
            if s["verdict"]:
                self.assertIn(s["verdict"], [d["title"] for d in drafts])
        steps = build_trace(brief, [])
        self.assertTrue(all(s["verdict"] == "" for s in steps))

    def test_evidence_ids_exist_in_the_brief(self):
        for brief, drafts, _ in (self.a, self.b):
            known = brief_mod.known_ids(brief)
            for s in build_trace(brief, drafts):
                self.assertTrue(set(s["evidence"]) <= known, s["title"])

    def test_site_b_has_two_problem_steps(self):
        brief, drafts, html = self.b
        problem = [s for s in build_trace(brief, drafts) if "読めなかった理由" in s["title"]]
        self.assertEqual({s["title"] for s in problem}, {"/help/export-kindle が読めなかった理由を調べる", "/pricing が読めなかった理由を調べる"})
        self.assertIn("調べた順番", html)
        self.assertNotIn("ステータスコード", html)


if __name__ == "__main__":
    unittest.main()
