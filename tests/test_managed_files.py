import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_advisor_managed  # noqa: E402


class ManagedFilesTest(unittest.TestCase):
    def test_agent_body_is_the_advisor_prompt(self):
        text = (ROOT / "agents" / "ashiato-advisor.md").read_text(encoding="utf-8")
        body = re.split(r"^---\n", text, maxsplit=2, flags=re.M)[2].lstrip("\n")
        self.assertEqual(body, (ROOT / "prompts" / "advisor_ja.md").read_text(encoding="utf-8"))

    def test_agent_has_no_tools_and_no_web(self):
        text = (ROOT / "agents" / "ashiato-advisor.md").read_text(encoding="utf-8")
        self.assertIn("default_config: {enabled: false}", text)
        self.assertIn("{name: web_search, enabled: false}", text)
        self.assertIn("{name: web_fetch, enabled: false}", text)

    def test_session_budget_is_small(self):
        self.assertLessEqual(int(run_advisor_managed.BUDGET_CENTS), 500)

    def test_fix_request_lists_problems(self):
        t = run_advisor_managed.fix_request([{"draft": {"title": "X"}, "problems": ["根拠の行IDがありません"]}])
        self.assertIn("X", t)
        self.assertIn("根拠の行IDがありません", t)


if __name__ == "__main__":
    unittest.main()
