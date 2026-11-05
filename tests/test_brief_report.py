import json
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
from ashiato import brief as brief_mod, drafts as drafts_mod, report  # noqa: E402

BANNED = ("ユーザーエージェント", "ステータスコード")


class Built:
    def __init__(self, gen, log, site, name):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        gen.write_all(root / "data")
        self.brief, self.drafts = build_report.build(root / "data" / log, root / "data" / site, name, root / "out")
        self.out = root / "out"
        self.known = brief_mod.known_ids(self.brief)
        self.by_target = {}
        for d in self.drafts:
            self.by_target.setdefault((d["kind"], d["target"]), []).append(d)


class BriefATest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = Built(gen_synthetic, "before.ndjson", "site/before", "雪待荘")

    @classmethod
    def tearDownClass(cls):
        cls.a.tmp.cleanup()

    def test_signals(self):
        s = self.a.brief["signals"]
        errors = {e["path"]: e for e in s["ai_errors"]}
        self.assertIn("/access", errors)
        self.assertIn("/plans/winter", errors)
        self.assertEqual({(c["from"], c["to"]) for c in s["redirect_candidates"]}, {("/plans/winter", "/plan/winter")})
        self.assertEqual([r["bot"] for r in s["robots_blocks"]], ["ClaudeBot"])
        self.assertTrue(s["robots_blocks"][0]["only_robots_txt"])
        # 偽装のGPTBotに加え、PerplexityBot と ChatGPT-User も実サイトのとおり一部が未検証
        self.assertEqual({u["bot"] for u in s["unverified_ai_claims"]}, {"GPTBot", "PerplexityBot", "ChatGPT-User"})
        self.assertIn("/meals", [p["path"] for p in s["pages_ai_never_fetched"]])
        self.assertIn("/blog/matsuri-2026", [h["path"] for h in s["healthy_pages"]])
        self.assertGreater(s["noise"]["requests"], 0)

    def test_drafts_cover_the_planted_findings(self):
        t = self.a.by_target
        self.assertIn(("new_page", "/access"), t)
        self.assertIn(("redirect", "/plans/winter"), t)
        self.assertNotIn(("new_page", "/plans/winter"), t)  # 新規作成ではなく転送
        self.assertIn(("fix_config", "/robots.txt"), t)
        self.assertIn(("rewrite_page", "/meals"), t)
        self.assertIn(("leave_alone", "/blog/matsuri-2026"), t)
        self.assertTrue([d for d in self.a.drafts if d["kind"] == "ignore"])

    def test_every_draft_has_known_evidence_and_plain_words(self):
        for d in self.a.drafts:
            self.assertEqual(drafts_mod.validate(d, self.a.known), [], d["title"])
            for term in BANNED:
                self.assertNotIn(term, d["title"] + d["why"])

    def test_brief_has_no_raw_log_fields(self):
        text = json.dumps(self.a.brief, ensure_ascii=False)
        for field in ("ClientRequestUserAgent", "EdgeStartTimestamp", "ClientIP"):
            self.assertNotIn(field, text)

    def test_report_html(self):
        html = (self.a.out / "report.html").read_text(encoding="utf-8")
        self.assertIn("見本", html)
        self.assertIn("次にやること", html)
        self.assertIn("手を付けなくてよいこと", html)
        for term in BANNED:
            self.assertNotIn(term, html)
        for d in self.a.drafts:
            self.assertIn(d["evidence"][0], html)

    def test_saved_files(self):
        self.assertEqual(json.loads((self.a.out / "drafts.json").read_text(encoding="utf-8")), self.a.drafts)


class BriefBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Built(gen_synthetic_b, "before.ndjson", "site", "かきわけ")

    @classmethod
    def tearDownClass(cls):
        cls.b.tmp.cleanup()

    def test_two_holes_and_no_noise_findings(self):
        s = self.b.brief["signals"]
        self.assertEqual({(e["path"], e["status"]) for e in s["ai_errors"]}, {("/help/export-kindle", 404), ("/pricing", 429)})
        self.assertEqual(s["redirect_candidates"], [])
        self.assertEqual(s["robots_blocks"], [])
        t = self.b.by_target
        self.assertIn(("new_page", "/help/export-kindle"), t)
        self.assertIn(("fix_config", "/pricing"), t)
        actions = [d for d in self.b.drafts if d["kind"] in ("new_page", "rewrite_page", "redirect", "fix_config")]
        self.assertEqual(len(actions), 2)  # 穴は2つだけ。仕事をでっち上げない

    def test_blog_pages_are_left_alone(self):
        left = {d["target"] for d in self.b.drafts if d["kind"] == "leave_alone"}
        self.assertTrue({"/blog/reading-notes-habit", "/blog/kindle-highlights-tips"} <= left)


class DraftsTest(unittest.TestCase):
    known = {"a.ndjson:1", "a.ndjson:2"}
    ok = {"kind": "new_page", "target": "/x", "title": "t", "why": "w", "body": "b", "priority": "high", "evidence": ["a.ndjson:1"]}

    def test_valid(self):
        self.assertEqual(drafts_mod.validate(self.ok, self.known), [])

    def test_rejects_missing_or_unknown_evidence(self):
        self.assertTrue(drafts_mod.validate(dict(self.ok, evidence=[]), self.known))
        self.assertTrue(drafts_mod.validate(dict(self.ok, evidence=["zzz:9"]), self.known))
        no_ev = {k: v for k, v in self.ok.items() if k != "evidence"}
        self.assertTrue(drafts_mod.validate(no_ev, self.known))

    def test_rejects_bad_kind_and_technical_words(self):
        self.assertTrue(drafts_mod.validate(dict(self.ok, kind="publish"), self.known))
        self.assertTrue(drafts_mod.validate(dict(self.ok, why="ステータスコードが404です"), self.known))

    def test_save_refuses_when_any_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                drafts_mod.save([self.ok, dict(self.ok, evidence=[])], self.known, d)
            self.assertFalse((Path(d) / "drafts.json").exists())
            drafts_mod.save([self.ok], self.known, d)
            self.assertTrue((Path(d) / "drafts.json").exists())

    def test_parse_response_splits_valid_and_rejected(self):
        text = "```json\n" + json.dumps([self.ok, dict(self.ok, evidence=["zzz:9"])]) + "\n```"
        valid, rejected = drafts_mod.parse_response(text, self.known)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(rejected), 1)

    def test_report_escapes_html(self):
        brief = {"site_name": "<b>x</b>", "period": {"from": "a", "to": "b"}, "pages": {}}
        html = report.render_report(brief, [dict(self.ok, title="<script>1</script>")])
        self.assertNotIn("<script>1</script>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)


if __name__ == "__main__":
    unittest.main()
