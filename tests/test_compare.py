import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
from ashiato import brief as brief_mod, logs, report  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402
from ashiato.compare import compare  # noqa: E402


class CompareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen_synthetic.write_all(out)
        cls.before = aggregate(logs.parse(out / "before.ndjson"))
        cls.after = aggregate(logs.parse(out / "after.ndjson"))
        cls.c = compare(cls.before, cls.after)
        cls.brief = brief_mod.build_brief(cls.before, brief_mod.load_site(out / "site" / "before"), "雪待荘")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_days_differ_so_rates_are_per_day(self):
        self.assertEqual(self.c["days"], {"before": 28, "after": 14})

    def test_failures_drop_to_zero_after_the_fix(self):
        self.assertGreater(self.c["failed_per_day"]["before"], 0)
        self.assertEqual(self.c["failed_per_day"]["after"], 0)
        by_path = {r["path"]: r for r in self.c["paths"]}
        for path in ("/access", "/plans/winter"):
            self.assertGreater(by_path[path]["before_failed_per_day"], 0)
            self.assertEqual(by_path[path]["after_failed_per_day"], 0)
        self.assertGreater(by_path["/access"]["after_ok_per_day"], 0)

    def test_report_shows_comparison_in_plain_japanese(self):
        html = report.render_report(self.brief, [], self.c)
        self.assertIn("直したあとの変化", html)
        self.assertIn("1日あたり", html)
        self.assertNotIn("直したあとの変化", report.render_report(self.brief, []))


if __name__ == "__main__":
    unittest.main()
