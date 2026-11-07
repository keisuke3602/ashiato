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

    def test_nginx_format_with_leading_virtual_host(self):
        # 行頭にドメイン名が付く形式（レンタルサーバーのマニュアルにある形）。内容は合成した例
        std = '203.0.113.9 - - [11/Jul/2026:12:09:17 +0900] "GET /access HTTP/1.1" 404 512 "-" "GPTBot/1.2"'
        vh = "example.test " + std
        a, b = logs.parse_text(std, "a.txt"), logs.parse_text(vh, "b.txt")
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertEqual((a[0]["path"], a[0]["status"], a[0]["ua"]), (b[0]["path"], b[0]["status"], b[0]["ua"]))

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

    def test_howto_is_shown_and_validated(self):
        from ashiato import drafts as dr
        d = {"kind": "redirect", "target": "/a", "title": "t", "why": "w", "body": "b", "priority": "high",
             "evidence": ["x:1"], "howto": "サーバーの .htaccess に貼る"}
        self.assertEqual(dr.validate(d, {"x:1"}), [])
        self.assertTrue(dr.validate(dict(d, howto=5), {"x:1"}))
        self.assertTrue(dr.validate(dict(d, howto="ステータスコードを見る"), {"x:1"}))
        self.assertEqual(dr.validate({k: v for k, v in d.items() if k != "howto"}, {"x:1"}), [])  # 古い返答も有効

    def test_site_only_diagnosis_without_logs(self):
        import json
        resp = json.dumps([
            {"kind": "fix_config", "target": "/robots.txt", "title": "ClaudeBot の断りを確かめる", "why": "案内ファイルで断られています。",
             "body": "Disallow を消す", "howto": "robots.txt を開き、この行を消す", "priority": "mid", "evidence": ["site:robots.txt:ClaudeBot"]},
            {"kind": "rewrite_page", "target": "/meals", "title": "お食事を充実させる", "why": "本文が短いです。",
             "body": "", "priority": "low", "evidence": ["site:page:/meals"]}], ensure_ascii=False)

        class Msg:
            stop_reason = "end_turn"
            content = [type("B", (), {"type": "text", "text": resp})()]
            usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return Msg()

        class Client:
            class messages:
                @staticmethod
                def stream(**kw):
                    return Stream()

        site_dir = self.root / "site" / "before"
        with self.assertRaises(LookupError):  # --live が無いと診断できない
            app.diagnose_site("", app.Config(site_dir, "雪待荘"))
        cfg = app.Config(site_dir, "雪待荘", live=True, client=Client)
        html = app.diagnose_site("", cfg)
        for needle in ("サイトの公開ページをもとにしています", "アクセスの記録は使っていません", "ClaudeBot の断りを確かめる", "調べた順番"):
            self.assertIn(needle, html)
        self.assertNotIn("AIがページを読みに来た回数", html)  # ログの数字は出さない
        self.assertIn("アクセスの記録が取れない", app.upload_page(cfg))
        self.assertNotIn("アクセスの記録が取れない", app.upload_page(self.cfg))

    def test_site_diagnosis_with_ai_answers(self):
        import json
        site_dir = self.root / "site" / "before"
        seen = []

        class B:
            def __init__(self, **kw): self.__dict__.update(kw)

        resp = json.dumps([{"kind": "rewrite_page", "target": "/meals", "title": "お食事を充実させる", "why": "AIの答えに出ていません。",
                            "body": "", "priority": "low", "evidence": ["ai:Q1", "site:page:/meals"]}], ensure_ascii=False)

        class Client:
            class messages:
                @staticmethod
                def create(**kw):
                    seen.append(kw)
                    if "tools" not in kw:
                        return B(stop_reason="end_turn", content=[B(type="text", text='["q1","q2","q3"]')])
                    return B(stop_reason="end_turn", content=[B(type="text", text="答え", citations=[B(url="https://other.test/a")])])

                @staticmethod
                def stream(**kw):
                    seen.append(kw)

                    class S:
                        def __enter__(self): return self
                        def __exit__(self, *a): return False
                        def get_final_message(self):
                            return B(stop_reason="end_turn", content=[B(type="text", text=resp)], usage=B(input_tokens=1, output_tokens=1))
                    return S()

        cfg = app.Config(site_dir, "雪待荘", live=True, client=Client)
        html = app.diagnose_site(json.dumps({"url": "", "ask_ai": True, "business": "温泉地の旅館"}), cfg)
        self.assertIn("AIは、お客様の質問に、どう答えるか", html)
        self.assertIn("Claudeにウェブ検索をさせた結果です", html)
        self.assertIn("あなたのサイトは、出典に入っていませんでした", html)
        self.assertIn("お食事を充実させる", html)  # ai:Q1 を根拠にした下書きが検証に通る
        no_ai = app.diagnose_site(json.dumps({"url": "", "ask_ai": False}), cfg)
        self.assertNotIn("AIは、お客様の質問に、どう答えるか", no_ai)

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
                                         headers={"X-Filename": "before.ndjson", "X-Ashiato": "1"})
            self.assertIn("次にやること", urllib.request.urlopen(req).read().decode())
            self.assertIn("<svg", urllib.request.urlopen(base + "/dashboard").read().decode())  # 調べたあとは、複数ページの画面が出る
            self.assertIn("承認した下書き", urllib.request.urlopen(base + "/actions").read().decode())
            bad =urllib.request.Request(base + "/analyze", data=b"not a log", method="POST",
                                      headers={"X-Filename": "x.ndjson", "X-Ashiato": "1"})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad)
            self.assertEqual(e.exception.code, 400)
            # 自分のページの印が無い。本文を読む前に断るので、小さい本文を送る（大きいと、送信の途中で接続が閉じられる）
            nohdr = urllib.request.Request(base + "/analyze", data=b"x", method="POST", headers={"X-Filename": "before.ndjson"})
            with self.assertRaises(urllib.error.HTTPError) as e2:
                urllib.request.urlopen(nohdr)
            self.assertEqual(e2.exception.code, 403)
            evil = urllib.request.Request(base + "/", headers={"Origin": "http://evil.example"})  # 別のサイトから
            with self.assertRaises(urllib.error.HTTPError) as e3:
                urllib.request.urlopen(evil)
            self.assertEqual(e3.exception.code, 403)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
