import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ashiato import brief as brief_mod, sitecheck  # noqa: E402

ROBOTS = "User-agent: *\nAllow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n"
HOME = "<html><head><title>雪待荘</title></head><body><h1>ようこそ</h1><script>var a=1</script><p>" + "あ" * 400 + "</p></body></html>"
THIN = "<html><head><title>お食事</title></head><body><p>短い</p></body></html>"
SITEMAP = "<urlset><url><loc>https://x.test/</loc></url><url><loc>https://x.test/meals</loc></url></urlset>"


def fake_get(table):
    def get(url):
        if url in table:
            return 200, table[url]
        return 404, ""
    return get


class SiteCheckTest(unittest.TestCase):
    def test_site_check_from_synthetic_snapshot(self):
        site = brief_mod.load_site(ROOT / "data" / "synthetic" / "ryokan" / "site" / "before")
        c = sitecheck.site_check(site)
        self.assertEqual([b["bot"] for b in c["ai_bots_blocked_in_robots"]], ["ClaudeBot"])  # 仕込んだ設定ミス
        self.assertTrue(c["robots_has_sitemap_line"]["value"])
        self.assertFalse(c["all_bots_blocked_in_robots"]["blocked"])
        self.assertTrue(any(t["path"] == "/meals" for t in c["thin_pages"]))  # 本文が短いページ
        self.assertEqual(c["page_list"]["count"], len(site["pages"]))

    def test_site_check_ids_are_known_to_the_brief(self):
        site = {"pages": [{"path": "/", "title": "a", "h1": "b", "words": 10, "in_sitemap": False}], "robots_txt": ROBOTS}
        b = {"signals": {}, "site_check": sitecheck.site_check(site)}
        ids = brief_mod.known_ids(b)
        for i in ("site:robots.txt:ClaudeBot", "site:sitemap:/", "site:page:/", "site:pages"):
            self.assertIn(i, ids)

    def test_fetch_site_builds_the_same_shape(self):
        table = {"https://x.test/robots.txt": ROBOTS + "Sitemap: https://x.test/sitemap.xml\n",
                 "https://x.test/sitemap.xml": SITEMAP, "https://x.test/": HOME, "https://x.test/meals": THIN}
        site = sitecheck.fetch_site("x.test", get=fake_get(table))
        self.assertEqual({p["path"] for p in site["pages"]}, {"/", "/meals"})
        home = next(p for p in site["pages"] if p["path"] == "/")
        self.assertEqual((home["title"], home["h1"], home["in_sitemap"]), ("雪待荘", "ようこそ", True))
        self.assertGreaterEqual(home["words"], 150)  # script の中身は数えない
        meals = next(p for p in site["pages"] if p["path"] == "/meals")
        self.assertLess(meals["words"], sitecheck.THIN_WORDS)
        self.assertIn("ClaudeBot", site["robots_txt"])

    def test_fetch_site_without_sitemap_reads_top_page(self):
        site = sitecheck.fetch_site("https://x.test", get=fake_get({"https://x.test/": HOME}))
        self.assertEqual([p["path"] for p in site["pages"]], ["/"])
        self.assertFalse(site["pages"][0]["in_sitemap"])

    def test_fetch_site_errors_and_scheme(self):
        with self.assertRaises(ValueError):
            sitecheck.fetch_site("https://x.test", get=fake_get({}))
        with self.assertRaises(ValueError):
            sitecheck._get("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
