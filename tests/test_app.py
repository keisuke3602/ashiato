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
