"""ローカルのサーバーと、サイトの取得の、安全面のテスト（ポートを開けなくても動く）。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ashiato import app, sitecheck  # noqa: E402


def fake_resolver(*addrs):
    return lambda host, port: [(2, 1, 6, "", (a, 0)) for a in addrs]


class RequestAllowedTest(unittest.TestCase):
    def test_own_page_is_allowed(self):
        self.assertTrue(app.request_allowed("127.0.0.1:8765", None, 8765))
        self.assertTrue(app.request_allowed("127.0.0.1:8765", "http://127.0.0.1:8765", 8765))
        self.assertTrue(app.request_allowed("localhost:8765", "http://localhost:8765", 8765))

    def test_other_site_is_refused(self):
        self.assertFalse(app.request_allowed("127.0.0.1:8765", "http://evil.example", 8765))
        self.assertFalse(app.request_allowed("127.0.0.1:8765", "null", 8765))
        self.assertFalse(app.request_allowed("127.0.0.1:8765", "http://127.0.0.1:9999", 8765))

    def test_rebound_host_is_refused(self):
        self.assertFalse(app.request_allowed("evil.example:8765", None, 8765))
        self.assertFalse(app.request_allowed(None, None, 8765))
        self.assertFalse(app.request_allowed("127.0.0.1:9999", None, 8765))


class HandlerGuardTest(unittest.TestCase):
    def handler(self, headers):
        cfg = app.Config("x", "y")
        h = app.make_handler(cfg).__new__(app.make_handler(cfg))
        h.headers = headers
        h.server = type("S", (), {"server_address": ("127.0.0.1", 8765)})()
        h.sent = []
        h._send = lambda code, body, ctype=None: h.sent.append(code)
        return h

    def test_post_needs_the_pages_own_mark(self):
        h = self.handler({"Host": "127.0.0.1:8765"})
        self.assertFalse(h._guard(post=True))
        self.assertEqual(h.sent, [403])
        h = self.handler({"Host": "127.0.0.1:8765", "X-Ashiato": "1"})
        self.assertTrue(h._guard(post=True))
        self.assertEqual(h.sent, [])

    def test_get_from_another_origin_is_refused(self):
        h = self.handler({"Host": "127.0.0.1:8765", "Origin": "http://evil.example"})
        self.assertFalse(h._guard())
        self.assertEqual(h.sent, [403])

    def test_pages_send_the_mark(self):
        cfg = app.Config("x", "y", live=True)
        html = app.upload_page(cfg) + app.AFTER_BLOCK
        self.assertGreaterEqual(html.count("X-Ashiato"), 3)  # /analyze, /compare, /site


class PublicHostTest(unittest.TestCase):
    def test_internal_addresses_are_not_public(self):
        for a in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fe80::1", "::ffff:127.0.0.1"):
            self.assertFalse(sitecheck.is_public_host("h.test", fake_resolver(a)), a)

    def test_public_address_is_public(self):
        self.assertTrue(sitecheck.is_public_host("h.test", fake_resolver("93.184.216.34")))

    def test_any_internal_answer_refuses(self):
        self.assertFalse(sitecheck.is_public_host("h.test", fake_resolver("93.184.216.34", "10.0.0.5")))

    def test_unresolvable_is_not_public(self):
        def boom(host, port):
            raise OSError("no such host")
        self.assertFalse(sitecheck.is_public_host("h.test", boom))
        self.assertFalse(sitecheck.is_public_host("h.test", fake_resolver()))


class FetchBlockTest(unittest.TestCase):
    def test_loopback_url_is_blocked_before_any_request(self):
        with self.assertRaises(sitecheck.BlockedAddress):
            sitecheck._get("http://127.0.0.1:9/")

    def test_other_schemes_are_refused(self):
        with self.assertRaises(ValueError):
            sitecheck._get("file:///etc/passwd")

    def test_fetch_site_reports_blocked_address(self):
        with self.assertRaises(sitecheck.BlockedAddress):
            sitecheck.fetch_site("http://127.0.0.1:9/")

    def test_redirect_to_internal_address_is_blocked(self):
        h = sitecheck._SafeRedirect()
        with self.assertRaises(sitecheck.BlockedAddress):
            h.redirect_request(None, None, 302, "Found", {}, "http://169.254.169.254/latest/meta-data/")


if __name__ == "__main__":
    unittest.main()
