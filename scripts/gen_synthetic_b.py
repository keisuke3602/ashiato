#!/usr/bin/env python3
"""合成データB（読書ノート共有サービス「かきわけ」、架空）を生成する。実ログは使わない。乱数は固定シード。

使い方: python3 scripts/gen_synthetic_b.py [出力先（既定: data/synthetic/readnote）]

ほぼ健全なサイトで、はっきりした穴が2つ。ページ中心で、AIボットは全体の少数派。
  穴1: /help/export-kindle が存在せず、AIが繰り返し取りに来て404 → 新しいページを下書きする
  穴2: /pricing だけ、一部のAIボットが429で断られている（人は200）→ サイト側の設定を見直す
出力: before.ndjson（28日分）, site/（pages.json, robots.txt, sitemap.xml）, expected.json
データAと同じ形式。Logpush NDJSON は IP・Cookie・国を含めない。
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_synthetic as a  # noqa: E402

SEED = 20261104
HOST = "kakiwake.example"
START, DAYS = date(2026, 9, 7), 28

PAGE_BYTES = {
    "/": 22000, "/features": 26000, "/pricing": 19000, "/extension": 15000, "/about": 12000,
    "/blog/reading-notes-habit": 30000, "/blog/kindle-highlights-tips": 28000,
    "/blog/ai-and-reading": 31000, "/blog/spaced-review": 27000,
    "/help/getting-started": 17000, "/robots.txt": 120, "/sitemap.xml": 900,
}
HUMAN_PATHS = {"/": 30, "/features": 14, "/pricing": 10, "/extension": 12, "/about": 3,
               "/blog/reading-notes-habit": 9, "/blog/kindle-highlights-tips": 8,
               "/blog/ai-and-reading": 6, "/blog/spaced-review": 4, "/help/getting-started": 6}
AI_PATHS = {"/": 4, "/features": 6, "/pricing": 6, "/extension": 4, "/about": 1,
            "/blog/reading-notes-habit": 10, "/blog/kindle-highlights-tips": 9,
            "/blog/ai-and-reading": 8, "/blog/spaced-review": 4, "/help/getting-started": 3,
            "/help/export-kindle": 7, "/sitemap.xml": 1}
CHATGPT_USER_PATHS = {"/help/export-kindle": 5, "/pricing": 3, "/features": 2, "/blog/kindle-highlights-tips": 2}
AI_ANSWER_PATHS = {"/features": 35, "/blog/kindle-highlights-tips": 35, "/extension": 30}
SEARCH_PATHS = {"/": 5, "/features": 4, "/pricing": 3, "/extension": 3, "/blog/reading-notes-habit": 4,
                "/blog/kindle-highlights-tips": 4, "/blog/ai-and-reading": 3, "/blog/spaced-review": 2,
                "/help/getting-started": 2, "/sitemap.xml": 1}
# 穴2: これらのAIボットは /pricing で断られる（サイト側の保護が強すぎる）
BLOCKED_ON_PRICING = {"GPTBot", "OAI-SearchBot", "ClaudeBot"}
CLAUDEBOT = (a.CLAUDEBOT[0], a.CLAUDEBOT[1], 5)
AI_ACTORS = {"GPTBot", "OAI-SearchBot", "PerplexityBot", "ChatGPT-User", "ClaudeBot"}


def status_and_base(path, actor):
    if path == "/help/export-kindle":
        return 404, 700
    if path == "/pricing" and actor in BLOCKED_ON_PRICING:
        return 429, 400
    if path in PAGE_BYTES:
        return 200, PAGE_BYTES[path]
    if path in a.ASSET_BYTES:
        return 200, a.ASSET_BYTES[path]
    return 404, 700


def event(rng, ts, uri, ua, cat, actor, ref="", status=None):
    resolved, base = status_and_base(uri.split("?")[0], actor)
    return {"ts": ts.astimezone(a.UTC), "uri": uri, "ua": ua, "cat": cat, "actor": actor, "ref": ref,
            "status": resolved if status is None else status, "bytes": int(base * rng.uniform(0.9, 1.1))}


def generate(rng):
    ev = []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        weekend = day.weekday() >= 5
        for _ in range(a.count(rng, 120 if weekend else 165)):
            t = a.jst_time(rng, day, a.HUMAN_HOUR)
            ua = rng.choice(a.HUMAN_UAS)
            ref = rng.choices(["", "https://www.google.com/", "https://x.com/"], weights=[50, 40, 10])[0]
            ev.append(event(rng, t, a.weighted(rng, HUMAN_PATHS), ua, "", "human", ref))
            if rng.random() < 0.35:
                ev.append(event(rng, t + timedelta(seconds=rng.uniform(0.2, 3)), rng.choice(a.ASSETS), ua, "", "human", ref))
        for _ in range(a.count(rng, 3.0)):
            p = a.weighted(rng, AI_ANSWER_PATHS)
            ev.append(event(rng, a.jst_time(rng, day, a.HUMAN_HOUR), f"{p}?utm_source=chatgpt.com",
                            rng.choice(a.HUMAN_UAS), "", "ai-answer-visitor", "https://chatgpt.com/"))
        for name, (ua, cat, mean) in a.BOTS.items():
            start = a.jst_time(rng, day)
            ev.append(event(rng, start - timedelta(seconds=3), "/robots.txt", ua, a.pick_cat(rng, cat), name))
            for t in a.burst(rng, start, a.count(rng, mean * 0.8), 1, 6):
                ev.append(event(rng, t, a.weighted(rng, AI_PATHS), ua, a.pick_cat(rng, cat), name))
        ua, cat, mean = a.CHATGPT_USER
        for _ in range(a.count(rng, mean + 1)):
            ev.append(event(rng, a.jst_time(rng, day, a.HUMAN_HOUR), a.weighted(rng, CHATGPT_USER_PATHS),
                            ua, a.pick_cat(rng, cat), "ChatGPT-User"))
        ua, cat, mean = CLAUDEBOT
        start = a.jst_time(rng, day)
        ev.append(event(rng, start - timedelta(seconds=3), "/robots.txt", ua, cat, "ClaudeBot"))
        for t in a.burst(rng, start, a.count(rng, mean), 1, 6):
            ev.append(event(rng, t, a.weighted(rng, AI_PATHS), ua, cat, "ClaudeBot"))
        for name, (ua, cat, mean) in a.SEARCH_BOTS.items():
            for t in a.burst(rng, a.jst_time(rng, day), a.count(rng, mean * 1.5), 2, 8):
                ev.append(event(rng, t, a.weighted(rng, SEARCH_PATHS), ua, cat, name))
        for _ in range(a.count(rng, 9)):
            ev.append(event(rng, a.jst_time(rng, day), rng.choice(a.NOISE_PATHS), rng.choice(a.NOISE_UAS), "", "noise"))
    ev.sort(key=lambda e: e["ts"])
    return ev


def to_logpush(e):
    return {"ClientRequestHost": HOST, "ClientRequestMethod": "GET", "ClientRequestURI": e["uri"],
            "ClientRequestReferer": e["ref"], "ClientRequestUserAgent": e["ua"],
            "EdgeResponseBytes": e["bytes"], "EdgeResponseStatus": e["status"],
            "EdgeStartTimestamp": e["ts"].strftime("%Y-%m-%dT%H:%M:%SZ"), "VerifiedBotCategory": e["cat"]}


def site_snapshot():
    titles = {"/": "かきわけ", "/features": "機能", "/pricing": "料金", "/extension": "ブラウザ拡張",
              "/about": "かきわけについて", "/blog/reading-notes-habit": "読書ノートを続けるコツ",
              "/blog/kindle-highlights-tips": "Kindleのハイライトを活かす", "/blog/ai-and-reading": "AI時代の読書",
              "/blog/spaced-review": "間隔をあけた復習", "/help/getting-started": "はじめてのかきわけ"}
    pages = [{"path": p, "title": t, "in_sitemap": True} for p, t in titles.items()]
    robots = "User-agent: *\nAllow: /\n\nSitemap: https://%s/sitemap.xml\n" % HOST
    sitemap = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
               + "".join(f"  <url><loc>https://{HOST}{p['path']}</loc></url>\n" for p in pages) + "</urlset>\n")
    return pages, robots, sitemap


def expected(ev):
    def n(actors, uri, status=None):
        return sum(1 for e in ev if e["actor"] in actors and e["uri"].split("?")[0] == uri
                   and (status is None or e["status"] == status))
    pages = [e for e in ev if e["uri"].split("?")[0] in PAGE_BYTES or e["uri"].split("?")[0] == "/help/export-kindle"]
    return {
        "hole_1_export_kindle_missing": {"ai_404": n(AI_ACTORS, "/help/export-kindle", 404),
                                         "ai_other": n(AI_ACTORS, "/help/export-kindle") - n(AI_ACTORS, "/help/export-kindle", 404),
                                         "human": n({"human"}, "/help/export-kindle")},
        "hole_2_pricing_blocked": {"blocked_429": n(BLOCKED_ON_PRICING, "/pricing", 429),
                                   "blocked_non429": n(BLOCKED_ON_PRICING, "/pricing") - n(BLOCKED_ON_PRICING, "/pricing", 429),
                                   "unblocked_ai_200": n({"PerplexityBot", "ChatGPT-User"}, "/pricing", 200),
                                   "human_pricing_200": n({"human"}, "/pricing", 200),
                                   "human_pricing_total": n({"human"}, "/pricing")},
        "healthy_blog": {"ai_200": sum(n(AI_ACTORS, p, 200) for p in PAGE_BYTES if p.startswith("/blog/")),
                         "ai_non200": sum(n(AI_ACTORS, p) - n(AI_ACTORS, p, 200) for p in PAGE_BYTES if p.startswith("/blog/"))},
        "ai_share": {"ai_requests": sum(1 for e in ev if e["actor"] in AI_ACTORS), "total": len(ev)},
        "page_share": {"page_requests": len(pages), "total": len(ev)},
        "totals": {"before": len(ev)},
    }


def write_all(out):
    ev = generate(random.Random(SEED))
    out.mkdir(parents=True, exist_ok=True)
    (out / "before.ndjson").write_text("".join(json.dumps(to_logpush(e), ensure_ascii=False) + "\n" for e in ev), encoding="utf-8")
    pages, robots, sitemap = site_snapshot()
    site = out / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (site / "robots.txt").write_text(robots, encoding="utf-8")
    (site / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (out / "expected.json").write_text(json.dumps(expected(ev), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_all(Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/readnote"))
