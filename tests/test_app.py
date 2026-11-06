import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gen_synthetic  # noqa: E402
from ashiato import app, logs  # noqa: E402


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        gen_synthetic.write_all(cls.root)
        cls.cfg = app.Config(cls.root / "site" / "before", "雪待荘", ROOT / "examples" / "ryokan" / "claude_response.json",
                             (str(cls.root / "after.ndjson"), None))
        cls.text = (cls.root / "before.ndjson").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_parse_text_matches_parse_file(self):
        a = logs.parse_text(self.text, "before.ndjson")
        b = logs.parse(self.root / "before.ndjson")
        self.assertEqual(a, b)
        n = (self.root / "before.nginx.txt").read_text(encoding="utf-8")
        self.assertEqual(logs.parse_text(n, "before.nginx.txt"), logs.parse(self.root / "before.nginx.txt"))

    def test_analyze_returns_full_report(self):
        html = app.analyze(self.text, "before.ndjson", self.cfg)
        for needle in ("次にやること", "調べた順番", "ページごとの様子", "直したあとの変化", "Claudeが書きました"):
            self.assertIn(needle, html)

    def test_before_only_has_no_comparison_until_after_is_added(self):
        cfg = app.Config(self.root / "site" / "before", "雪待荘", ROOT / "examples" / "ryokan" / "claude_response.json")
        with self.assertRaises(LookupError):  # 先に before を入れていない
            app.compare_after((self.root / "after.ndjson").read_text(encoding="utf-8"), "after.ndjson", cfg)
        html = app.analyze(self.text, "before.ndjson", cfg)
        self.assertNotIn("直したあとの変化", html)
        self.assertIn("直したあとのアクセス記録を入れると", html)
        html2 = app.compare_after((self.root / "after.ndjson").read_text(encoding="utf-8"), "after.ndjson", cfg)
        self.assertIn("直したあとの変化", html2)
        self.assertNotIn("直したあとのアクセス記録を入れると", html2)

    def test_live_mode_uses_claude_on_the_uploaded_log(self):
        saved = (ROOT / "examples" / "ryokan" / "claude_response.json").read_text(encoding="utf-8")

        class Msg:
            stop_reason = "end_turn"
            content = [type("B", (), {"type": "text", "text": saved})()]
            usage = type("U", (), {"input_tokens": 10, "output_tokens": 20})()

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return Msg()

        calls = []

        class Client:
            class messages:
                @staticmethod
                def stream(**kw):
                    calls.append(kw)
                    return Stream()

        cfg = app.Config(self.root / "site" / "before", "雪待荘", live=True, client=Client)
        html = app.analyze(self.text, "before.ndjson", cfg)
        self.assertEqual(len(calls), 1)  # 検証に通るので、出し直しは無い
        self.assertIsInstance(calls[0]["messages"][0]["content"], str)  # 送るのはブリーフ（文字列）だけ
        self.assertIn("Claudeが書きました", html)
        self.assertIn("1〜2分", app.upload_page(cfg))
        self.assertNotIn("1〜2分", app.upload_page(self.cfg))

    def test_report_has_approved_export(self):
        html = app.analyze(self.text, "before.ndjson", self.cfg)
        for needle in ("承認した下書き", "exp-text", "まとめてコピー", "サイトには何も書き込みません"):
            self.assertIn(needle, html)

    def test_response_for_other_log_is_not_used(self):
        # 行IDが合わない（別の名前のファイル）ときは、Claude の下書きを使わない
        html = app.analyze(self.text, "other.ndjson", self.cfg)
        self.assertNotIn("「アクセス」ページを新しく作る", html)

    def test_analyze_rejects_empty(self):
        with self.assertRaises(ValueError):
            app.analyze("", "x.ndjson", self.cfg)

    def test_upload_page_has_no_technical_words(self):
        for term in ("ユーザーエージェント", "ステータスコード"):
            self.assertNotIn(term, app.UPLOAD_PAGE)
        self.assertIn("数えています", app.UPLOAD_PAGE)

    def test_http_roundtrip(self):
        try:
            server = HTTPServer(("127.0.0.1", 0), app.make_handler(self.cfg))
        except PermissionError:
            self.skipTest("この環境ではポートを開けない")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            self.assertIn("足跡", urllib.request.urlopen(base + "/").read().decode())
            req = urllib.request.Request(base + "/analyze", data=self.text.encode(), method="POST",
                                         headers={"X-Filename": "before.ndjson"})
            self.assertIn("次にやること", urllib.request.urlopen(req).read().decode())
            bad = urllib.request.Request(base + "/analyze", data=b"not a log", method="POST", headers={"X-Filename": "x.ndjson"})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad)
            self.assertEqual(e.exception.code, 400)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
