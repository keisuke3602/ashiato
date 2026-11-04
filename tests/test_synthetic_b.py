import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gen_synthetic_b  # noqa: E402

LOGPUSH_FIELDS = {"ClientRequestHost", "ClientRequestMethod", "ClientRequestURI", "ClientRequestReferer",
                  "ClientRequestUserAgent", "EdgeResponseBytes", "EdgeResponseStatus", "EdgeStartTimestamp",
                  "VerifiedBotCategory"}


class SyntheticBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        gen_synthetic_b.write_all(cls.out)
        cls.expected = json.loads((cls.out / "expected.json").read_text())
        cls.rows = [json.loads(line) for line in (cls.out / "before.ndjson").read_text().splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as other:
            gen_synthetic_b.write_all(Path(other))
            for f in ("before.ndjson", "expected.json"):
                self.assertEqual((self.out / f).read_bytes(), (Path(other) / f).read_bytes(), f)

    def test_size_period_and_fields(self):
        self.assertTrue(7000 <= self.expected["totals"]["before"] <= 9000)
        self.assertGreaterEqual(len({r["EdgeStartTimestamp"][:10] for r in self.rows}), 28)
        for row in self.rows:
            self.assertEqual(set(row), LOGPUSH_FIELDS)

    def test_ai_is_a_minority_and_pages_dominate(self):
        s = self.expected["ai_share"]
        self.assertLess(s["ai_requests"] / s["total"], 0.15)
        self.assertGreater(s["ai_requests"], 0)
        p = self.expected["page_share"]
        self.assertGreater(p["page_requests"] / p["total"], 0.7)

    def test_hole_1_export_kindle(self):
        f = self.expected["hole_1_export_kindle_missing"]
        self.assertGreater(f["ai_404"], 50)
        self.assertEqual(f["ai_other"], 0)
        self.assertEqual(f["human"], 0)

    def test_hole_2_pricing_blocked_for_some_ai_only(self):
        f = self.expected["hole_2_pricing_blocked"]
        self.assertGreater(f["blocked_429"], 20)
        self.assertEqual(f["blocked_non429"], 0)
        self.assertGreater(f["unblocked_ai_200"], 0)
        self.assertGreater(f["human_pricing_total"], 0)
        self.assertEqual(f["human_pricing_200"], f["human_pricing_total"])

    def test_rest_of_site_is_healthy(self):
        f = self.expected["healthy_blog"]
        self.assertGreater(f["ai_200"], 0)
        self.assertEqual(f["ai_non200"], 0)
        # 穴の2つ以外で、AIが404や429を受けない
        for r in self.rows:
            path = r["ClientRequestURI"].split("?")[0]
            ai = r["ClientRequestUserAgent"] and any(k in r["ClientRequestUserAgent"] for k in (
                "GPTBot", "OAI-SearchBot", "PerplexityBot", "ChatGPT-User", "ClaudeBot"))
            if ai and path not in ("/help/export-kindle", "/pricing"):
                self.assertEqual(r["EdgeResponseStatus"], 200, r)


if __name__ == "__main__":
    unittest.main()
