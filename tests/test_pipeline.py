import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
import gen_synthetic_b  # noqa: E402
from ashiato.aggregate import aggregate, path_type  # noqa: E402
from ashiato.classify import classify_ua, is_verified  # noqa: E402
from ashiato.logs import parse, parse_nginx  # noqa: E402

AI_NAMES = {"GPTBot", "OAI-SearchBot", "PerplexityBot", "ChatGPT-User", "ClaudeBot"}


class ClassifyTest(unittest.TestCase):
    def test_ua_table(self):
        self.assertEqual(classify_ua(gen_synthetic.BOTS["GPTBot"][0]), ("GPTBot", "ai_crawler"))
        self.assertEqual(classify_ua(gen_synthetic.BOTS["OAI-SearchBot"][0]), ("OAI-SearchBot", "ai_search"))
        self.assertEqual(classify_ua(gen_synthetic.CHATGPT_USER[0])[1], "ai_assistant")
        self.assertEqual(classify_ua(gen_synthetic.SEARCH_BOTS["Googlebot"][0])[1], "search")
        self.assertEqual(classify_ua("python-requests/2.31.0")[1], "scanner")
        self.assertEqual(classify_ua(gen_synthetic.HUMAN_UAS[0])[1], "human")
        self.assertEqual(classify_ua("")[1], "unknown")

    def test_verified_flag(self):
        self.assertIs(is_verified("AI Crawler"), True)
        self.assertIs(is_verified(""), False)
        self.assertIsNone(is_verified(None))

    def test_path_type(self):
        self.assertEqual(path_type("/plan/winter"), "page")
        self.assertEqual(path_type("/_next/image"), "asset")
        self.assertEqual(path_type("/images/hero.jpg"), "asset")
        self.assertEqual(path_type("/api/v1/items"), "api")
        self.assertEqual(path_type("/robots.txt"), "meta")


class PipelineATest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen_synthetic.write_all(out)
        cls.raw = [json.loads(l) for l in (out / "before.ndjson").read_text().splitlines()]
        cls.rows = parse(out / "before.ndjson")
        cls.nginx_rows = parse(out / "before.nginx.txt")
        cls.agg = aggregate(cls.rows)
        cls.after = aggregate(parse(out / "after.ndjson"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def count_raw(self, path, status, names=AI_NAMES):
        """生の行から独立に数える: AIのUA・検証済み・パス・ステータスが一致する行。"""
        return sum(1 for r in self.raw
                   if classify_ua(r["ClientRequestUserAgent"])[0] in names and r["VerifiedBotCategory"] != ""
                   and r["ClientRequestURI"].split("?")[0] == path and r["EdgeResponseStatus"] == status)

    def test_row_count_and_ids(self):
        self.assertEqual(len(self.rows), len(self.raw))
        self.assertEqual(self.rows[0]["id"], "before.ndjson:1")
        self.assertEqual(self.agg["total_rows"], len(self.raw))

    def test_nginx_matches_logpush(self):
        self.assertEqual(len(self.nginx_rows), len(self.rows))
        for a, b in zip(self.nginx_rows[:200], self.rows[:200]):
            self.assertEqual((a["ts"], a["path"], a["query"], a["status"], a["ua"]),
                             (b["ts"], b["path"], b["query"], b["status"], b["ua"]))
            self.assertIsNone(a["category"])

    def test_finding_1_access_404(self):
        p = self.agg["pages"]["/access"]
        self.assertEqual(p["ai"]["404"], self.count_raw("/access", 404))
        self.assertGreater(p["ai"]["404"], 0)
        self.assertEqual(set(p["ai"]), {"404"})
        self.assertTrue(p["evidence"]["404"])
        self.assertNotIn("404", self.after["pages"]["/access"]["ai"])
        self.assertGreater(self.after["pages"]["/access"]["ai"]["200"], 0)

    def test_finding_2_old_path_404_while_new_path_has_visitors(self):
        self.assertEqual(self.agg["pages"]["/plans/winter"]["ai"]["404"], self.count_raw("/plans/winter", 404))
        self.assertGreater(self.agg["pages"]["/plan/winter"]["ai_answer_visitors"], 0)
        self.assertGreater(self.after["pages"]["/plans/winter"]["ai"]["301"], 0)

    def test_finding_3_healthy_blog(self):
        p = self.agg["pages"]["/blog/matsuri-2026"]
        self.assertGreater(p["ai"]["200"], 0)
        self.assertEqual(set(p["ai"]), {"200"})

    def test_finding_4_scanners_are_ignored_not_pages(self):
        self.assertGreater(self.agg["ignored"]["scanner_requests"], 0)
        self.assertIn("/wp-login.php", self.agg["ignored"]["scanner_paths"])
        self.assertNotIn("/wp-login.php", self.agg["pages"])

    def test_finding_5_thin_page_not_fetched_by_ai(self):
        p = self.agg["pages"]["/meals"]
        self.assertEqual(p["ai"], {})
        self.assertGreater(p["human"], 0)

    def test_finding_6_claudebot_only_robots(self):
        b = self.agg["bots"]["ClaudeBot"]
        self.assertTrue(b["only_robots_txt"])
        self.assertEqual(b["paths"].keys(), {"/robots.txt"})

    def test_finding_7_spoofed_gptbot_not_counted_as_demand(self):
        b = self.agg["bots"]["GPTBot"]
        spoofed = sum(1 for r in self.raw if "GPTBot" in r["ClientRequestUserAgent"] and r["VerifiedBotCategory"] == "")
        self.assertGreater(spoofed, 0)
        self.assertEqual(b["unverified"], spoofed)
        # ページの需要に入るのは、検証済みのGPTBotがページを取った分だけ
        genuine_pages = sum(1 for r in self.raw if "GPTBot" in r["ClientRequestUserAgent"]
                            and r["VerifiedBotCategory"] != "" and path_type(r["ClientRequestURI"].split("?")[0]) == "page")
        counted = sum(sum(p["ai_by_bot"].get("GPTBot", {}).values()) for p in self.agg["pages"].values())
        self.assertEqual(counted, genuine_pages)

    def test_utm_visitors_only_count_human_looking_200(self):
        visitors = sum(p["ai_answer_visitors"] for p in self.agg["pages"].values())
        expected = json.loads(Path(self.tmp.name, "expected.json").read_text())["8_utm_requests"]["human_200"]
        self.assertEqual(visitors, expected)

    def test_assets_are_not_pages(self):
        self.assertFalse([p for p in self.agg["pages"] if p.startswith("/images/") or p.endswith(".css")])
        self.assertGreater(self.agg["ignored"]["non_page_requests"].get("asset", 0), 0)


class PipelineBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen_synthetic_b.write_all(out)
        cls.expected = json.loads((out / "expected.json").read_text())
        cls.agg = aggregate(parse(out / "before.ndjson"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_hole_1_export_kindle(self):
        p = self.agg["pages"]["/help/export-kindle"]
        self.assertEqual(set(p["ai"]), {"404"})
        self.assertGreater(p["ai"]["404"], 50)
        self.assertEqual(p["human"], 0)

    def test_hole_2_pricing_429_only_for_some_bots(self):
        p = self.agg["pages"]["/pricing"]
        self.assertGreater(p["ai"]["429"], 20)
        for bot in ("GPTBot", "OAI-SearchBot", "ClaudeBot"):
            self.assertEqual(set(p["ai_by_bot"][bot]), {"429"})
        self.assertEqual(set(p["ai_by_bot"]["PerplexityBot"]) | set(p["ai_by_bot"].get("ChatGPT-User", {})), {"200"})
        self.assertGreater(p["human"], 0)

    def test_everything_else_is_healthy(self):
        for path, p in self.agg["pages"].items():
            if path not in ("/help/export-kindle", "/pricing"):
                self.assertTrue(set(p["ai"]) <= {"200"}, (path, p["ai"]))


if __name__ == "__main__":
    unittest.main()
