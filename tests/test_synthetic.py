import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gen_synthetic  # noqa: E402

LOGPUSH_FIELDS = {"ClientRequestHost", "ClientRequestMethod", "ClientRequestURI", "ClientRequestReferer",
                  "ClientRequestUserAgent", "EdgeResponseBytes", "EdgeResponseStatus", "EdgeStartTimestamp",
                  "VerifiedBotCategory"}


class SyntheticDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        gen_synthetic.write_all(cls.out)
        cls.expected = json.loads((cls.out / "expected.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, name):
        return [json.loads(line) for line in (self.out / f"{name}.ndjson").read_text().splitlines()]

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as other:
            gen_synthetic.write_all(Path(other))
            for f in ("before.ndjson", "after.ndjson", "before.nginx.txt", "expected.json"):
                self.assertEqual((self.out / f).read_bytes(), (Path(other) / f).read_bytes(), f)

    def test_no_ip_or_cookie_fields(self):
        for name in ("before", "after"):
            for row in self.rows(name):
                self.assertEqual(set(row), LOGPUSH_FIELDS)

    def test_sizes_and_period(self):
        self.assertTrue(3500 <= self.expected["totals"]["before"] <= 4500)
        days = {r["EdgeStartTimestamp"][:10] for r in self.rows("before")}
        self.assertGreaterEqual(len(days), 28)
        self.assertEqual(len(self.rows("before")), len((self.out / "before.nginx.txt").read_text().splitlines()))

    def test_finding_1_access_missing_then_fixed(self):
        f = self.expected["1_access_missing"]
        self.assertGreater(f["ai_404_before"], 0)
        self.assertEqual(f["ai_404_after"], 0)
        self.assertGreater(f["ai_200_after"], 0)

    def test_finding_2_moved_without_redirect(self):
        f = self.expected["2_moved_no_redirect"]
        self.assertGreater(f["ai_404_old_path_before"], 0)
        self.assertGreater(f["ai_301_old_path_after"], 0)
        self.assertGreater(f["ai_answer_visitors_new_path_before"], 0)

    def test_finding_3_healthy_post(self):
        f = self.expected["3_healthy"]
        self.assertGreater(f["ai_200"], 0)
        self.assertEqual(f["ai_non200"], 0)

    def test_finding_4_noise_is_all_404(self):
        f = self.expected["4_noise"]
        self.assertGreater(f["requests"], 0)
        self.assertEqual(f["non404"], 0)

    def test_finding_5_thin_page_ignored_by_ai(self):
        f = self.expected["5_thin_page"]
        self.assertEqual(f["ai_fetches_meals"], 0)
        self.assertGreater(f["human_fetches_meals"], 0)

    def test_finding_6_claudebot_blocked(self):
        f = self.expected["6_robots_block"]
        self.assertGreater(f["claudebot_requests"], 0)
        self.assertEqual(f["claudebot_non_robots"], 0)
        robots = (self.out / "site" / "before" / "robots.txt").read_text()
        self.assertIn("User-agent: ClaudeBot\nDisallow: /", robots)

    def test_finding_7_spoof_is_unverified(self):
        f = self.expected["7_spoofed_gptbot"]
        self.assertGreater(f["requests"], 0)
        self.assertEqual(f["verified_category_nonempty"], 0)

    def cats_for(self, needle):
        return {r["VerifiedBotCategory"] for r in self.rows("before") if needle in r["ClientRequestUserAgent"]}

    def test_category_cannot_decide_ai_vs_search(self):
        # 実サイトの集計に合わせた性質。UAの表で種類を決め、カテゴリは「検証されたか」の印だけに使う。
        self.assertEqual(self.cats_for("like Gecko; compatible; GPTBot/1.4"), {"AI Crawler"})
        self.assertEqual(self.cats_for("OAI-SearchBot"), {"Search Engine Crawler"})
        self.assertEqual(self.cats_for("PerplexityBot"), {"", "Search Engine Crawler"})
        self.assertEqual(self.cats_for("ChatGPT-User"), {"", "AI Assistant"})

    def test_spoofed_gptbot_format_is_never_verified(self):
        self.assertEqual(self.cats_for("like Gecko); compatible; GPTBot/1.4"), {""})

    def test_utm_requests_are_mostly_not_human(self):
        f = self.expected["8_utm_requests"]
        self.assertGreater(f["human_200"], 0)
        self.assertGreater(f["not_human"], 0)
        self.assertEqual(f["not_human_200"], 0)

    def test_after_has_no_site_404_for_fixed_paths(self):
        for row in self.rows("after"):
            if row["ClientRequestURI"].split("?")[0] == "/access":
                self.assertEqual(row["EdgeResponseStatus"], 200)
            if row["ClientRequestURI"].split("?")[0] == "/plans/winter":
                self.assertEqual(row["EdgeResponseStatus"], 301)


if __name__ == "__main__":
    unittest.main()
