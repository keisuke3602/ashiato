import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ashiato import ask_ai, brief as brief_mod  # noqa: E402


def block(**kw):
    return type("B", (), kw)()


class FakeClient:
    """質問づくりと、検索つきの答えを返す偽のクライアント。呼び出しを記録する。"""

    def __init__(self, pause_once=False):
        self.calls, self.pause_once, self._paused = [], pause_once, False
        outer = self

        class Messages:
            @staticmethod
            def create(**kw):
                outer.calls.append(kw)
                if "tools" not in kw:  # 質問づくり
                    return type("M", (), {"stop_reason": "end_turn", "content": [block(type="text", text='["雪の日に行ける温泉は？","駅から近い宿は？","食事が良い宿は？"]')]})()
                if outer.pause_once and not outer._paused:
                    outer._paused = True
                    return type("M", (), {"stop_reason": "pause_turn", "content": [block(type="text", text="検索中。")]})()
                res = block(type="web_search_tool_result", content=[block(url="https://other.test/a"), block(url="https://yuki.test/x")])
                txt = block(type="text", text="雪待荘がおすすめです。", citations=[block(url="https://other.test/a")])
                return type("M", (), {"stop_reason": "end_turn", "content": [res, txt]})()
        self.messages = Messages


class AskAiTest(unittest.TestCase):
    def test_check_builds_facts_with_evidence_ids(self):
        c = FakeClient()
        r = ask_ai.check_ai_answers(c, "雪待荘", domain="yuki.test")
        self.assertEqual([i["evidence"] for i in r["items"]], [["ai:Q1"], ["ai:Q2"], ["ai:Q3"]])
        first = r["items"][0]
        self.assertTrue(first["site_cited"])  # 出典に自社のドメインがある
        self.assertTrue(first["site_named"])  # 答えに名前が出る
        self.assertIn("other.test", first["cited_domains"])
        self.assertIn("他のAIの答えとは限りません", r["note"])
        tools = [k["tools"][0]["type"] for k in c.calls if "tools" in k]
        self.assertEqual(set(tools), {"web_search_20260209"})

    def test_site_not_cited_when_domain_differs(self):
        r = ask_ai.check_ai_answers(FakeClient(), "別の宿", domain="nothing.test")
        self.assertFalse(r["items"][0]["site_cited"])
        self.assertFalse(r["items"][0]["site_named"])

    def test_pause_turn_continues(self):
        c = FakeClient(pause_once=True)
        answer, urls = ask_ai.ask(c, "質問")
        self.assertIn("検索中", answer)
        self.assertIn("雪待荘", answer)
        self.assertEqual(len([k for k in c.calls if "tools" in k]), 2)

    def test_ids_are_known_to_the_brief(self):
        r = ask_ai.check_ai_answers(FakeClient(), "雪待荘", domain="yuki.test")
        self.assertEqual(brief_mod.known_ids({"ai_answers": r}), {"ai:Q1", "ai:Q2", "ai:Q3"})


if __name__ == "__main__":
    unittest.main()
