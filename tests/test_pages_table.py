import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
import gen_synthetic_b  # noqa: E402
from ashiato import brief as brief_mod, logs, report  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402
from ashiato.pages_table import page_rows  # noqa: E402


def brief_of(gen, site, name):
    with tempfile.TemporaryDirectory() as d:
        gen.write_all(Path(d))
        return brief_mod.build_brief(aggregate(logs.parse(Path(d) / "before.ndjson")), brief_mod.load_site(Path(d) / site), name)


class PagesTableTest(unittest.TestCase):
    def test_site_a(self):
        rows = {r["path"]: r for r in page_rows(brief_of(gen_synthetic, "site/before", "雪待荘"))}
        self.assertEqual(rows["/access"]["status"], "ページがない")
        self.assertEqual(rows["/plans/winter"]["status"], "ページがない")
        self.assertEqual(rows["/meals"]["status"], "読まれていない")
        self.assertEqual(rows["/blog/matsuri-2026"]["status"], "読まれている")
        self.assertEqual(rows["/access"]["ai_ok"], 0)
        self.assertGreater(rows["/access"]["ai_failed"], 0)

    def test_site_b_and_order(self):
        rows = page_rows(brief_of(gen_synthetic_b, "site", "かきわけ"))
        by = {r["path"]: r for r in rows}
        self.assertEqual(by["/help/export-kindle"]["status"], "ページがない")
        self.assertEqual(by["/pricing"]["status"], "一部のAIに断られている")
        self.assertEqual(by["/features"]["status"], "読まれている")
        self.assertEqual({rows[0]["path"], rows[1]["path"]}, {"/help/export-kindle", "/pricing"})  # 問題のあるものが先頭

    def test_report_contains_table(self):
        b = brief_of(gen_synthetic_b, "site", "かきわけ")
        html = report.render_report(b, [])
        self.assertIn("ページごとの様子", html)
        self.assertIn("一部のAIに断られている", html)


if __name__ == "__main__":
    unittest.main()
