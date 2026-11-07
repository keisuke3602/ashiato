"""需要（AIが探したのに無かったURLと、よく読まれているページ）にもとづく下書きの、検証と表示のテスト。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
from ashiato import advisor, brief as brief_mod, drafts, logs, report  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402


class DemandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen_synthetic.write_all(out)
        agg = aggregate(logs.parse_text((out / "before.ndjson").read_text(encoding="utf-8"), "before.ndjson"))
        cls.site = brief_mod.load_site(out / "site" / "before")
        cls.brief = brief_mod.build_brief(agg, cls.site, "雪待荘")
        cls.known = brief_mod.known_ids(cls.brief)
        cls.reading = {r["path"]: r for r in cls.brief["demand"]["reading"]}
        cls.guessed = {g["path"]: g for g in cls.brief["demand"]["guessed_missing"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def draft(self, **kw):
        base = {"kind": "new_page", "target": "/access", "title": "t", "why": "w", "body": "", "priority": "high",
                "evidence": list(self.guessed["/access"]["evidence"][:2])}
        return dict(base, **kw)

    def follow_up(self, **kw):
        base = {"target": "/blog/matsuri-guide", "priority": "low", "demand_basis": "reading", "based_on": ["/blog/matsuri-2026"],
                "evidence": self.reading["/blog/matsuri-2026"]["evidence"][:2]}
        return self.draft(**dict(base, **kw))

    def check(self, d):
        return advisor.check_against_brief(d, self.brief)

    def test_demand_comes_from_the_requests(self):
        self.assertEqual({p: g["count"] for p, g in self.guessed.items()}, {"/access": 163, "/plans/winter": 56})
        self.assertEqual(self.guessed["/plans/winter"]["words"], ["plans", "winter"])
        top = self.brief["demand"]["reading"][0]
        self.assertEqual((top["path"], top["ai_reads"], top["ai_answer_visitors"]), ("/blog/matsuri-2026", 156, 11))
        for item in self.brief["demand"]["guessed_missing"] + self.brief["demand"]["reading"]:
            self.assertTrue(set(item["evidence"]) <= self.known)  # 根拠の行IDは、ブリーフにあるものだけ
            self.assertTrue(item["evidence"])

    def test_guessed_draft_is_accepted_only_for_a_guessed_path(self):
        self.assertEqual(self.check(self.draft(demand_basis="guessed")), [])
        self.assertTrue(self.check(self.draft(target="/faq", demand_basis="guessed")))

    def test_reading_draft_is_accepted_when_tied_to_a_read_page(self):
        self.assertEqual(self.check(self.follow_up()), [])

    def test_reading_draft_is_refused_when_the_ties_are_wrong(self):
        self.assertTrue(self.check(self.follow_up(kind="redirect")))  # new_page だけ
        self.assertTrue(self.check(self.follow_up(target="/onsen")))  # 既にあるページ
        self.assertTrue(self.check(self.follow_up(based_on=["/nowhere"])))  # 読まれていないページ
        self.assertTrue(self.check(self.follow_up(based_on=[])))
        other = self.reading["/plan/winter"]["evidence"][:1]
        self.assertTrue(self.check(self.follow_up(evidence=other)))  # 根拠が、元のページのものではない

    def test_invented_page_without_a_record_is_refused(self):
        invented = self.draft(target="/faq")  # 根拠は /access の行で、/faq は探されていない
        self.assertTrue(self.check(invented))
        from_site = self.draft(target="/faq", evidence=["site:pages"])  # サイトの公開ページを根拠にした提案は、通る
        self.assertEqual(self.check(from_site), [])

    def test_unknown_basis_and_site_only(self):
        self.assertTrue(self.check(self.draft(demand_basis="hunch")))
        site_only = brief_mod.build_site_only_brief(self.site, "雪待荘")
        self.assertTrue(advisor.check_against_brief(self.draft(demand_basis="guessed"), site_only))

    def test_validate_checks_the_optional_fields(self):
        self.assertEqual(drafts.validate(self.follow_up(), self.known), [])
        self.assertTrue(drafts.validate(self.draft(demand_basis="hunch"), self.known))
        self.assertTrue(drafts.validate(self.follow_up(based_on="/blog/matsuri-2026"), self.known))

    def test_card_shows_numbers_from_the_brief_not_from_claude(self):
        guessed = report._card(0, self.draft(demand_basis="guessed", why="163回"), {}, brief=self.brief)
        self.assertIn("AIが探していた", guessed)
        self.assertIn("このアドレスを163回、探しました", guessed)
        reading = report._card(0, self.follow_up(why="ここに数字は書かない"), {}, brief=self.brief)
        self.assertIn("続きの話題の候補", reading)
        self.assertIn("156回読み", reading)
        self.assertIn("11人", reading)
        self.assertIn("探した記録があるわけではありません", reading)
        self.assertNotIn("basis", report._card(0, self.draft(), {}, brief=self.brief))  # 需要の印が無い下書きには、出さない


if __name__ == "__main__":
    unittest.main()
