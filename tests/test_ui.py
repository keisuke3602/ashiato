"""複数ページの画面（ダッシュボード、調べた順番、次にやること、直したあとの変化）とグラフのテスト。"""
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
from ashiato import app, brief as brief_mod, charts, logs, report  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402
from ashiato.trace import build_trace  # noqa: E402

BANNED = ("ユーザーエージェント", "ステータスコード", "User-Agent")


def svgs(html):
    return re.findall(r"<svg.*?</svg>", html, re.S)


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        gen_synthetic.write_all(cls.root)
        cls.before = (cls.root / "before.ndjson").read_text(encoding="utf-8")
        cls.after = (cls.root / "after.ndjson").read_text(encoding="utf-8")
        cls.response = ROOT / "examples" / "ryokan" / "claude_response.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cfg(self, with_after=False):
        after = (str(self.root / "after.ndjson"), None) if with_after else None
        return app.Config(self.root / "site" / "before", "雪待荘", self.response, after)

    def test_daily_series_matches_the_page_counts(self):
        agg = aggregate(logs.parse_text(self.before, "before.ndjson"))
        ok = sum(d["ai_ok"] for d in agg["daily"].values())
        bad = sum(d["ai_failed"] for d in agg["daily"].values())
        visitors = sum(d["answer_visitors"] for d in agg["daily"].values())
        pages = agg["pages"].values()
        self.assertEqual(ok, sum(n for p in pages for st, n in p["ai"].items() if st[0] in "23"))
        self.assertEqual(bad, sum(n for p in pages for st, n in p["ai"].items() if st[0] in "45"))
        self.assertEqual(visitors, sum(p["ai_answer_visitors"] for p in pages))

    def test_daily_series_is_not_sent_to_claude(self):
        agg = aggregate(logs.parse_text(self.before, "before.ndjson"))
        brief = brief_mod.build_brief(agg, brief_mod.load_site(self.root / "site" / "before"), "雪待荘")
        self.assertNotIn("daily", brief)

    def test_no_page_before_anything_is_analyzed(self):
        self.assertIsNone(app.render_page(self.cfg(), "dashboard"))
        self.assertIsNone(app.render_page(self.cfg(), "nope"))

    def test_four_pages_after_analysis(self):
        cfg = self.cfg()
        app.analyze(self.before, "before.ndjson", cfg)
        dash = app.render_page(cfg, "dashboard")
        self.assertGreaterEqual(len(svgs(dash)), 3)  # 日ごと、AIの種類別、お客様
        for needle in ("713", "219", "44", 'href="/actions"', "どのAIが来ているか", "日ごとの、AIの動き"):
            self.assertIn(needle, dash)
        for needle in ("どんなページが求められているか", "AIが探したのに、無かったページ", "AIがよく読んでいるページ"):
            self.assertIn(needle, dash)
        lost = dash.split("AIが探したのに、無かったページ")[1].split("AIがよく読んでいるページ")[0]
        self.assertIn("/access", lost)
        self.assertIn("新しく作る候補", lost)
        self.assertIn("転送で足りる（/plan/winter）", lost)  # /plans/winter は、既存の /plan/winter に近い
        self.assertIn("お客様の質問に答えるために来たAI（ChatGPT-User）", lost)  # /access を、質問に応じて取りに来たAIが探した
        self.assertIn("/blog/matsuri-2026", dash.split("AIがよく読んでいるページ")[1])
        self.assertIn("調べた順番", app.render_page(cfg, "trace"))
        actions = app.render_page(cfg, "actions")
        for needle in ("次にやること", "承認した下書き", 'data-id="0"', "手を付けなくてよいこと", "まとめてコピー"):
            self.assertIn(needle, actions)
        self.assertNotIn("日ごとの、AIの動き", actions)  # グラフはダッシュボードにある

    def test_nav_marks_the_current_page(self):
        cfg = self.cfg()
        app.analyze(self.before, "before.ndjson", cfg)
        for name in ("dashboard", "trace", "actions", "changes"):
            html = app.render_page(cfg, name)
            self.assertEqual(html.count('aria-current="page"'), 1, name)
            self.assertIn(f'href="/{name}" aria-current="page"', html)
            for other in ("dashboard", "trace", "actions", "changes"):
                self.assertIn(f'href="/{other}"', html)

    def test_changes_page_asks_for_the_after_log_first(self):
        cfg = self.cfg()
        app.analyze(self.before, "before.ndjson", cfg)
        html = app.render_page(cfg, "changes")
        self.assertIn("直したあとのアクセス記録を入れると", html)
        self.assertNotIn('class="grid3"', html)
        app.compare_after(self.after, "after.ndjson", cfg)
        html = app.render_page(cfg, "changes")
        self.assertIn('class="grid3"', html)
        self.assertIn("7.8", html)
        self.assertNotIn("直したあとのアクセス記録を入れると", html)
        self.assertGreaterEqual(len(svgs(html)), 7)  # 日ごと、合計、読めた割合、提案したページ宛、3つの前後
        for needle in ("AIの要求の合計", "AIが読めた割合", "AIが来る回数そのものは、ほぼ変わっていません", "提案したページ宛の要求",
                       "/access、/plans/winter", "30.7%が、提案したページ宛で、そのうち読めたのは0%", "25.5%が、同じページ宛で、そのうち読めたのは100%"):
            self.assertIn(needle, html)

    def test_changes_page_with_a_fixed_after_log(self):
        cfg = self.cfg(with_after=True)
        app.analyze(self.before, "before.ndjson", cfg)
        html = app.render_page(cfg, "changes")
        self.assertIn("7.8", html)
        self.assertIn("この間に直した", html)  # 区切りの印（日付に空きがあるので、そう書く）
        self.assertEqual(html.count("1日あたりで比べています"), 1)  # 同じ説明を、2回出さない

    def test_every_chart_is_well_formed_svg_and_has_a_label(self):
        cfg = self.cfg(with_after=True)
        app.analyze(self.before, "before.ndjson", cfg)
        for name in ("dashboard", "changes"):
            for svg in svgs(app.render_page(cfg, name)):
                root = ET.fromstring(svg)
                self.assertTrue(root.get("aria-label"), name)

    def test_no_banned_words_on_any_page(self):
        cfg = self.cfg(with_after=True)
        app.analyze(self.before, "before.ndjson", cfg)
        for name in ("dashboard", "trace", "actions", "changes"):
            html = app.render_page(cfg, name)
            for term in BANNED:
                self.assertNotIn(term, html, f"{name}: {term}")

    def test_approval_marks_are_kept_per_report(self):
        cfg = self.cfg()
        app.analyze(self.before, "before.ndjson", cfg)
        rid1 = cfg.view["rid"]
        app.analyze(self.before, "before.ndjson", cfg)
        self.assertEqual(cfg.view["rid"], rid1)  # 同じ結果なら、同じ印
        other = report.make_view(cfg.view["brief"], cfg.view["drafts"][:-1], cfg.view["trace"])
        self.assertNotEqual(other["rid"], rid1)  # 下書きが変われば、前の印は引き継がない

    def test_site_only_view_has_no_time_series(self):
        site = brief_mod.load_site(self.root / "site" / "before")
        brief = brief_mod.build_site_only_brief(site, "雪待荘")
        view = report.make_view(brief, [], build_trace(brief, []))
        dash = report.page_dashboard(view)
        self.assertNotIn("日ごとの、AIの動き", dash)
        self.assertIn("アクセスの記録は使っていません", dash)
        self.assertIn("ページごとの、本文の長さ", dash)  # 記録が無くても、サイトの情報からグラフを出す
        self.assertGreaterEqual(len(svgs(dash)), 1)
        self.assertIn("アクセスの記録があるときに", report.page_changes(view))


class FixSummaryTest(unittest.TestCase):
    def test_totals_are_flat_and_the_rate_rises(self):
        view = {"cmp": {"days": {"before": 2, "after": 1}},
                "agg": {"pages": {"/a": {"ai": {"404": 6}}, "/b": {"ai": {"200": 4}}}},
                "agg_after": {"pages": {"/a": {"ai": {"200": 5}}, "/b": {"ai": {"200": 5}}}},
                "drafts": [{"kind": "new_page", "target": "/a"}, {"kind": "new_page", "target": "/z", "demand_basis": "reading"}]}
        f = report._fix_summary(view)
        self.assertEqual((f["total_before"], f["total_after"]), (5.0, 10.0))
        self.assertEqual((f["rate_before"], f["rate_after"]), (40.0, 100.0))
        self.assertEqual(f["pages"], ["/a"])  # 続きの話題の提案（reading）は、数えない
        self.assertEqual((f["share_before"], f["share_after"]), (60.0, 50.0))
        self.assertEqual((f["proposal_read_before"], f["proposal_read_after"]), (0, 100.0))

    def test_other_pages_can_have_failures_too(self):
        view = {"cmp": {"days": {"before": 1, "after": 1}},
                "agg": {"pages": {"/a": {"ai": {"404": 2}}, "/b": {"ai": {"200": 1, "404": 1}}}},
                "agg_after": {"pages": {"/a": {"ai": {"200": 2}}, "/b": {"ai": {"200": 1, "404": 1}}}},
                "drafts": [{"kind": "redirect", "target": "/a"}]}
        f = report._fix_summary(view)
        names = [n for n, _p, _c in f["segs_after"]]
        self.assertIn("その他のページ宛（読めなかった）", names)  # 決め打ちで「全部読めた」としない


class ChartsTest(unittest.TestCase):
    def test_empty_data_does_not_crash(self):
        for svg in (charts.stacked_days([], "空"), charts.line_days([], "x", "空"), charts.hbars([], "空"), charts.before_after("空", 0, 0)):
            ET.fromstring(svg)

    def test_day_series_fills_missing_days(self):
        s = charts.day_series({"2026-09-07": {"ai_ok": 1}, "2026-09-10": {"ai_ok": 2}})
        self.assertEqual([x[0] for x in s], ["9/7", "9/8", "9/9", "9/10"])
        self.assertEqual(s[1][2], {})

    def test_share_bars_are_well_formed(self):
        ET.fromstring(charts.share_bars([("直す前", [("a", 30.7, "var(--warn)"), ("b", 69.3, "var(--ok)")]), ("直したあと", [])], "x"))

    def test_labels_are_escaped(self):
        svg = charts.hbars([("<script>x</script>", 1, 0)], "a&b")
        ET.fromstring(svg)
        self.assertNotIn("<script>", svg)


if __name__ == "__main__":
    unittest.main()
