"""文書（台本、README）に書いた数字と主張が、データと保存した返答から導けること。
合わなければ落ちる。「GitHub の内容とデモが一致する」ことを、テストで守る。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
from ashiato import logs, report  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402
from ashiato.brief import build_brief, load_site  # noqa: E402
from ashiato.compare import compare  # noqa: E402

ACTIONS = {"new_page", "redirect", "fix_config", "rewrite_page"}
# 合成データA（docs/design.md の仕込み7つ）に対して、保存した返答が出すべき判断。4と7は、どちらも「無視してよい」。
PLANTED_ACTIONS = {("new_page", "/access"), ("redirect", "/plans/winter"), ("fix_config", "/robots.txt"), ("rewrite_page", "/meals")}


class DocsClaimsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen_synthetic.write_all(out)
        parse = lambda n: logs.parse_text((out / f"{n}.ndjson").read_text(encoding="utf-8"), f"{n}.ndjson")  # noqa: E731
        cls.before, cls.after = aggregate(parse("before")), aggregate(parse("after"))
        cls.brief = build_brief(cls.before, load_site(out / "site" / "before"), "雪待荘")
        cls.compare = compare(cls.before, cls.after)
        cls.demo = (ROOT / "docs" / "demo.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.response = json.loads((ROOT / "examples" / "ryokan" / "claude_response.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def numbers(self):
        (_, ai, _), (_, bad, _), (_, visitors, _) = report._tiles(self.brief)
        failed = self.compare["failed_per_day"]
        return [f"{ai}回", f"{bad}回", f"{visitors}回", f"{bad / ai * 100:.1f}%", f"{failed['before']:g} → {failed['after']:g}"]

    def missing(self, doc):
        return [n for n in self.numbers() if n not in doc]

    def test_demo_numbers_come_from_the_data(self):
        self.assertEqual(self.missing(self.demo), [])

    def test_the_check_can_fail(self):
        # 検査が、本当に落ちることの確認（数字を変えた文書では、見つかる）
        altered = self.demo.replace("713回", "714回").replace("7.8 → 0", "7.9 → 0")
        self.assertEqual(set(self.missing(altered)), {self.numbers()[0], self.numbers()[4]})

    def test_saved_response_covers_the_planted_findings(self):
        main = {(d["kind"], d["target"]) for d in self.response if d["kind"] in ACTIONS and d.get("demand_basis") != "reading"}
        self.assertEqual(main, PLANTED_ACTIONS)  # 仕込みの1,2,5,6。ほかに、記録に根拠のない作業が無いこと
        healthy = " ".join(d["title"] + d["why"] for d in self.response if d["kind"] == "leave_alone")
        self.assertIn("雪まつり", healthy)  # 仕込み3（雪まつりの記事は、健全）
        ignored = " ".join(d["title"] + d["why"] for d in self.response if d["kind"] == "ignore")
        self.assertIn("管理", ignored)  # 仕込み4
        self.assertIn("名乗", ignored)  # 仕込み7
        self.assertEqual(sum(1 for d in self.response if d["kind"] == "ignore"), 2)

    def test_demand_proposals_are_tied_to_read_pages_and_capped(self):
        extra = [d for d in self.response if d.get("demand_basis") == "reading"]
        self.assertLessEqual(len(extra), 2)  # 続きの話題の提案は、最大2件
        reading = {r["path"]: r for r in self.brief["demand"]["reading"]}
        for d in extra:
            self.assertEqual(d["kind"], "new_page")
            self.assertTrue(set(d["based_on"]) <= set(reading))
            self.assertTrue(set(d["evidence"]) <= {i for b in d["based_on"] for i in reading[b]["evidence"]})
            self.assertIn("探した記録があるわけではありません", d["why"])  # 提案であることを、書いている

    def test_readme_count_matches_the_saved_response(self):
        self.assertIn(f"{len(self.response)}件", self.readme)

    def test_claims_keep_their_conditions(self):
        for name, doc in (("README", self.readme), ("台本", self.demo)):
            if "7つの問題すべて" in doc or "7つ" in doc and "対応していました" in doc:
                self.assertIn("実サイトでの正解率ではない", doc.replace("ありません", "ない"), f"{name}: 条件の記述が消えている")


if __name__ == "__main__":
    unittest.main()
