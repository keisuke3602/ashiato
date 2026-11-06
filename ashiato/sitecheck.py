"""目2: サイトの公開ページから、AIが読める状態かを調べる（アクセスログが無くても使える）。

事実を集めるだけ。何を直すかの判断は Claude がする。根拠の目印は "site:..." で始まる（ログの行IDと区別する）。
サイトの情報は、load_site と同じ形 {"pages": [...], "robots_txt": "..."} に揃える。
  fetch_site(url): 持ち主のサイトの公開ページを取りに行って、その形にする（robots.txt、sitemap.xml、各ページ。最大 MAX_PAGES）。
取得はコードがする。Claude はサイトに触れない。
"""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .brief import blocked_agents
from .classify import AI_KINDS, UA_TABLE

THIN_WORDS = 150
MAX_PAGES = 40
MAX_BYTES = 1_000_000
AI_BOTS = [name for _, name, kind in UA_TABLE if kind in AI_KINDS]


def site_check(site):
    """サイトの情報から、AIの読みやすさに関わる事実を取り出す。"""
    robots = site["robots_txt"]
    blocked = blocked_agents(robots)
    pages = site["pages"]
    blocks = [{"bot": name, "evidence": [f"site:robots.txt:{name}"]} for name in AI_BOTS if name.lower() in blocked]
    return {
        "ai_bots_blocked_in_robots": blocks,
        "all_bots_blocked_in_robots": {"blocked": "*" in blocked, "evidence": ["site:robots.txt:*"]},
        "robots_has_sitemap_line": {"value": bool(re.search(r"^\s*sitemap\s*:", robots, re.I | re.M)),
                                    "evidence": ["site:robots.txt:sitemap"]},
        "pages_not_in_sitemap": [{"path": p["path"], "title": p.get("title", ""), "evidence": [f"site:sitemap:{p['path']}"]}
                                 for p in pages if p.get("in_sitemap") is False],
        "thin_pages": [{"path": p["path"], "title": p.get("title", ""), "words": p["words"], "evidence": [f"site:page:{p['path']}"]}
                       for p in pages if isinstance(p.get("words"), int) and p["words"] < THIN_WORDS],
        "pages_without_title_or_heading": [{"path": p["path"], "evidence": [f"site:page:{p['path']}"]}
                                           for p in pages if not p.get("title") or not p.get("h1")],
        "page_list": {"count": len(pages), "paths": [p["path"] for p in pages], "evidence": ["site:pages"]},
    }


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.h1, self.text, self._in, self._skip = "", "", [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in ("title", "h1") and not getattr(self, tag):
            self._in = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag == self._in:
            self._in = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in:
            setattr(self, self._in, (getattr(self, self._in) + data).strip())
        self.text.append(data)


def _words(text):
    text = " ".join(text.split())
    return max(len(text.split()), len(text) // 2)  # 日本語は空白が少ないので、文字数の半分も見る


def _get(url):
    """(状態コード, 本文)。http/https だけ。サイズと時間に上限がある。"""
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("http か https のアドレスを入れてください")
    req = Request(url, headers={"User-Agent": "ashiato/0.1 (site check, run by the site owner)"})
    with urlopen(req, timeout=10) as r:  # noqa: S310
        return r.status, r.read(MAX_BYTES).decode("utf-8", errors="replace")


def fetch_site(url, get=_get, max_pages=MAX_PAGES):
    """公開ページから、load_site と同じ形のサイトの情報を作る。"""
    parts = urlsplit(url if "://" in url else "https://" + url)
    if not parts.netloc:
        raise ValueError("サイトのアドレスが読み取れません")
    origin = f"{parts.scheme}://{parts.netloc}"

    def fetch(u):
        try:
            status, body = get(u)
            return body if status == 200 else ""
        except Exception:
            return ""

    robots = fetch(origin + "/robots.txt")
    sm_urls = re.findall(r"^\s*sitemap\s*:\s*(\S+)", robots, re.I | re.M) or [origin + "/sitemap.xml"]
    locs = []
    for u in sm_urls[:3]:
        locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", fetch(u))
    paths = []
    for loc in locs:
        sp = urlsplit(loc)
        if sp.netloc == parts.netloc and (sp.path or "/") not in paths:
            paths.append(sp.path or "/")
    in_sitemap = set(paths)
    if "/" not in paths:
        paths.insert(0, "/")
    pages = []
    for path in paths[:max_pages]:
        html = fetch(origin + path)
        if not html:
            continue
        p = _Page()
        p.feed(html)
        pages.append({"path": path, "title": p.title, "h1": p.h1, "words": _words(" ".join(p.text)),
                      "in_sitemap": path in in_sitemap})
    if not pages:
        raise ValueError("サイトのページを読み込めませんでした。アドレスを確かめてください")
    return {"pages": pages, "robots_txt": robots}
