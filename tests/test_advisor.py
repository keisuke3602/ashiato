import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ashiato import advisor  # noqa: E402

BRIEF = {"site_name": "x", "site_pages": [{"path": "/rooms"}],
         "signals": {"redirect_candidates": [{"from": "/old", "to": "/rooms", "evidence": ["a:1"]}]},
         "pages": {"p": {"evidence": {"404": ["a:1", "a:2"]}}}}


def draft(kind, target, **kw):
    return dict({"kind": kind, "target": target, "title": "t", "why": "w", "body": "b", "priority": "high",
                 "evidence": ["a:1"]}, **kw)


class AdvisorTest(unittest.TestCase):
    def run_accept(self, *drafts):
        return advisor.accept(json.dumps(list(drafts)), BRIEF)

    def test_build_request_has_prompt_and_brief_only(self):
        r = advisor.build_request(BRIEF)
        self.assertIn("根拠", r["system"])
        self.assertEqual(json.loads(r["user"]), BRIEF)

    def test_accepts_matching_kinds_and_marks_source(self):
        ok, bad = self.run_accept(draft("redirect", "/old"), draft("new_page", "/access"), draft("rewrite_page", "/rooms"))
        self.assertEqual(len(ok), 3)
        self.assertEqual(bad, [])
        self.assertTrue(all(d["source"] == "claude" for d in ok))

    def test_rejects_redirect_without_candidate(self):
        ok, bad = self.run_accept(draft("redirect", "/help/export-kindle"))
        self.assertEqual(ok, [])
        self.assertIn("new_page", bad[0]["problems"][0])

    def test_rejects_new_page_for_existing_and_rewrite_for_missing(self):
        ok, bad = self.run_accept(draft("new_page", "/rooms"), draft("rewrite_page", "/nowhere"))
        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 2)

    def test_rejects_unknown_evidence(self):
        ok, bad = self.run_accept(draft("new_page", "/access", evidence=["zzz:9"]))
        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 1)


if __name__ == "__main__":
    unittest.main()


class SavedClaudeResponsesTest(unittest.TestCase):
    """examples/ にある Claude の返答が、今のブリーフ・検証でも通ること（データの作り方が変わると気づける）。"""

    def check(self, gen, site_sub, name, example):
        import tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from ashiato import brief as brief_mod, logs
        from ashiato.aggregate import aggregate
        with tempfile.TemporaryDirectory() as d:
            gen.write_all(Path(d))
            brief = brief_mod.build_brief(aggregate(logs.parse(Path(d) / "before.ndjson")),
                                          brief_mod.load_site(Path(d) / site_sub), name)
        text = (Path(__file__).resolve().parent.parent / "examples" / example / "claude_response.json").read_text(encoding="utf-8")
        ok, rejected = advisor.accept(text, brief)
        self.assertEqual(rejected, [])
        self.assertTrue(ok)
        return ok

    def test_ryokan(self):
        import gen_synthetic
        kinds = {(d["kind"], d["target"]) for d in self.check(gen_synthetic, "site/before", "雪待荘", "ryokan")}
        self.assertTrue({("new_page", "/access"), ("redirect", "/plans/winter"), ("fix_config", "/robots.txt"),
                         ("rewrite_page", "/meals")} <= kinds)

    def test_readnote(self):
        import gen_synthetic_b
        ok = self.check(gen_synthetic_b, "site", "かきわけ", "readnote")
        actions = [(d["kind"], d["target"]) for d in ok if d["kind"] in ("new_page", "rewrite_page", "redirect", "fix_config")]
        self.assertEqual(sorted(actions), [("fix_config", "/pricing"), ("new_page", "/help/export-kindle")])
