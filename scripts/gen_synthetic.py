#!/usr/bin/env python3
"""合成データ（旅館「雪待荘」、架空）を生成する。実ログは使わない。乱数は固定シード。

使い方: python3 scripts/gen_synthetic.py [出力先（既定: data/synthetic/ryokan）]

出力:
  before.ndjson / before.nginx.txt   28日分。仕込み7つ（docs/design.md）を含む
  after.ndjson  / after.nginx.txt    14日分。1と2が直り、5（/meals）が書き直された状態。仮説にもとづくシナリオ（下の SCENARIO_*）。
                                      シナリオ: AIの要求が増え、新しいURLの探索は続く。実際の効果を示すものではない
  site/{before,after}/               サイトの現在のページ（robots.txt, sitemap.xml, pages.json）
  expected.json                      仕込みの正解（テストの基準）

Logpush NDJSON は IP・Cookie・国を含めない。nginx形式のIPは文書用の範囲（RFC 5737）。
VerifiedBotCategory の値は docs/design.md の暫定の仮定（検証失敗は空）に従う。
"""
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SEED = 20261102
HOST = "yukimachi-so.example"
JST = timezone(timedelta(hours=9))
UTC = timezone.utc
BEFORE_START, BEFORE_DAYS = date(2026, 9, 7), 28
AFTER_START, AFTER_DAYS = date(2026, 10, 19), 14
# シナリオ（仮説。実際の効果ではない）。直す前（fixed=False）には、影響しない（倍率1、パスの表も同じ）。
# 1) 母数の増加: ChatGPT の利用が全体に増えるので、どのドメインへのAIの要求も、全体に増える。
# 2) 提案の効果: 探されたページが存在するようになり、書き直した /meals も読まれ始めるので、そのページ宛の要求は、全体の増加より大きく増える。
SCENARIO_MARKET_GROWTH = 1.15
SCENARIO_PROPOSAL_EXTRA_PER_DAY = 4  # 提案したページ宛の、上乗せ（1日の平均件数）
PROPOSAL_PAGES = {"/access": 5, "/plans/winter": 2, "/meals": 3}
# シナリオ（仮説）: 直したあとも、AIは新しいURLを推測して取りに来続ける（読めなかった要求は、減るが、消えない）。
SCENARIO_NEW_GUESSES_PER_DAY = 3
NEW_GUESSES = {"/faq": 5, "/gallery": 3, "/plans/summer": 2, "/news": 2}

PAGE_BYTES = {
    "/": 18000, "/rooms": 24000, "/plan/winter": 21000, "/plan/summer": 20000,
    "/onsen": 19000, "/meals": 1300, "/blog/matsuri-2026": 32000,
    "/contact": 9000, "/robots.txt": 120, "/sitemap.xml": 900,
}
ASSETS = ["/images/hero.jpg", "/images/room1.jpg", "/images/onsen.jpg", "/css/site.css", "/favicon.ico"]
ASSET_BYTES = {"/images/hero.jpg": 240000, "/images/room1.jpg": 180000, "/images/onsen.jpg": 210000,
               "/css/site.css": 14000, "/favicon.ico": 1500}

CAT_CRAWLER, CAT_ASSISTANT, CAT_SEARCH = ("AI Crawler", "AI Assistant", "Search Engine Crawler")

# name -> (UA, VerifiedBotCategory, 1日の平均件数, パスの重み)
AI_PATHS = {"/": 5, "/rooms": 4, "/plan/winter": 4, "/plans/winter": 4, "/plan/summer": 3,
            "/onsen": 3, "/blog/matsuri-2026": 10, "/access": 8, "/contact": 2, "/sitemap.xml": 1}
# 実サイトの集計で分かったこと: VerifiedBotCategory はAIか検索かの判定に使えない。
# OAI-SearchBot は Search Engine Crawler、PerplexityBot は大半が未検証、ChatGPT-User は同じUAが
# 未検証と AI Assistant の両方に出る。カテゴリが辞書のものは、その重みで1リクエストごとに決める。
BOTS = {
    "GPTBot": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.4; +https://openai.com/gptbot)",
               CAT_CRAWLER, 14),
    "OAI-SearchBot": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
                      CAT_SEARCH, 10),
    "PerplexityBot": ("Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
                      {"": 85, CAT_SEARCH: 15}, 4),
}
CHATGPT_USER = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
                {"": 50, CAT_ASSISTANT: 50}, 3)
CLAUDEBOT = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
             CAT_CRAWLER)
SEARCH_BOTS = {
    "Googlebot": ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", CAT_SEARCH, 8),
    "Bingbot": ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", CAT_SEARCH, 4),
}
SEARCH_PATHS = {"/": 5, "/rooms": 4, "/plan/winter": 4, "/plan/summer": 3, "/onsen": 3, "/meals": 2,
                "/blog/matsuri-2026": 3, "/contact": 1, "/sitemap.xml": 1}
# 本物（検証済み）の書式とは括弧の位置が違うGPTBotのUA。実サイトでは常に未検証だった書式。
SPOOF_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.4; +https://openai.com/gptbot"
NOISE_UAS = ["python-requests/2.31.0", "zgrab/0.x", "curl/8.4.0", "Go-http-client/1.1"]
NOISE_PATHS = ["/wp-login.php", "/.env", "/xmlrpc.php", "/wp-admin/", "/.git/config", "/phpmyadmin/"]
HUMAN_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
]
HUMAN_PATHS = {"/": 30, "/rooms": 15, "/plan/winter": 10, "/plan/summer": 8, "/onsen": 10, "/meals": 6,
               "/blog/matsuri-2026": 6, "/contact": 4, "/access": 3}
HUMAN_HOUR = [1, 1, .5, .5, .5, 1, 2, 3, 3, 3, 3, 3, 4, 4, 3, 3, 3, 4, 5, 7, 9, 10, 8, 4]
AI_ANSWER_PATHS = {"/plan/winter": 50, "/blog/matsuri-2026": 25, "/onsen": 25}


def resolve(path, fixed):
    """（ステータス, 基準バイト数）。サイトの状態（旧/新）に応じて決める。"""
    if path == "/access":
        return (200, 15000) if fixed else (404, 700)
    if path == "/plans/winter":
        return (301, 300) if fixed else (404, 700)
    if path == "/meals" and fixed:
        return 200, 16000  # シナリオ: 書き直して、文章が増えた
    if path in PAGE_BYTES:
        return 200, PAGE_BYTES[path]
    if path in ASSET_BYTES:
        return 200, ASSET_BYTES[path]
    return 404, 700


def weighted(rng, table):
    return rng.choices(list(table), weights=list(table.values()))[0]


def pick_cat(rng, cat):
    return weighted(rng, cat) if isinstance(cat, dict) else cat


def event(rng, ts, uri, ua, cat, actor, fixed, ref="", status=None):
    resolved, base = resolve(uri.split("?")[0], fixed)
    status = resolved if status is None else status
    return {"ts": ts.astimezone(UTC), "uri": uri, "ua": ua, "cat": cat, "actor": actor, "ref": ref,
            "status": status, "bytes": int(base * rng.uniform(0.9, 1.1))}


def jst_time(rng, day, hour_weights=None):
    hour = rng.choices(range(24), weights=hour_weights)[0] if hour_weights else rng.randrange(24)
    return datetime(day.year, day.month, day.day, hour, rng.randrange(60), rng.randrange(60), tzinfo=JST)


def count(rng, mean):
    return max(0, round(rng.gauss(mean, mean * 0.3)))


def burst(rng, start, n, lo, hi):
    t = start
    for _ in range(n):
        yield t
        t += timedelta(seconds=rng.uniform(lo, hi))


def generate(rng, start_day, days, fixed):
    ev = []
    for d in range(days):
        day = start_day + timedelta(days=d)
        weekend = day.weekday() >= 5
        # 人
        for _ in range(count(rng, 62 if weekend else 48)):
            t = jst_time(rng, day, HUMAN_HOUR)
            ua = rng.choice(HUMAN_UAS)
            ref = rng.choices(["", "https://www.google.com/", "https://www.instagram.com/"], weights=[45, 40, 15])[0]
            ev.append(event(rng, t, weighted(rng, HUMAN_PATHS), ua, "", "human", fixed, ref))
            for _ in range(rng.choice([0, 1, 1, 2])):
                ev.append(event(rng, t + timedelta(seconds=rng.uniform(0.2, 3)), rng.choice(ASSETS), ua, "", "human", fixed, ref))
        # AIの回答から来た人（utm_source とリファラ）
        for _ in range(count(rng, 2.5 if fixed else 1.4)):
            p = weighted(rng, AI_ANSWER_PATHS)
            ev.append(event(rng, jst_time(rng, day, HUMAN_HOUR), f"{p}?utm_source=chatgpt.com", rng.choice(HUMAN_UAS),
                            "", "ai-answer-visitor", fixed, "https://chatgpt.com/"))
        # utm_source 付きでも人の訪問ではないリクエスト（実サイトでは大半。403・504・302）
        for _ in range(count(rng, 3.5)):
            ev.append(event(rng, jst_time(rng, day), f"{weighted(rng, AI_ANSWER_PATHS)}?utm_source=chatgpt.com",
                            rng.choice(HUMAN_UAS), "", "utm-not-human", fixed, status=rng.choice([403, 403, 403, 504, 302])))
        # AIボット（バースト）
        for name, (ua, cat, mean) in BOTS.items():
            start = jst_time(rng, day)
            ev.append(event(rng, start - timedelta(seconds=3), "/robots.txt", ua, pick_cat(rng, cat), name, fixed))
            for t in burst(rng, start, count(rng, mean * (SCENARIO_MARKET_GROWTH if fixed else 1)), 1, 6):
                ev.append(event(rng, t, weighted(rng, AI_PATHS), ua, pick_cat(rng, cat), name, fixed))
        if fixed:  # シナリオ: 提案したページ宛の要求が、全体の増加に上乗せされる
            for _ in range(count(rng, SCENARIO_PROPOSAL_EXTRA_PER_DAY)):
                bot = rng.choice(list(BOTS))
                ev.append(event(rng, jst_time(rng, day, HUMAN_HOUR), weighted(rng, PROPOSAL_PAGES), BOTS[bot][0], pick_cat(rng, BOTS[bot][1]), bot, fixed))
        if fixed:  # シナリオ: 新しく探されるURL（サイトにまだ無い）
            for _ in range(count(rng, SCENARIO_NEW_GUESSES_PER_DAY)):
                bot = rng.choice(list(BOTS))
                ev.append(event(rng, jst_time(rng, day, HUMAN_HOUR), weighted(rng, NEW_GUESSES), BOTS[bot][0], pick_cat(rng, BOTS[bot][1]), bot, fixed))
        ua, cat, mean = CHATGPT_USER
        for _ in range(count(rng, mean * (SCENARIO_MARKET_GROWTH if fixed else 1))):
            ev.append(event(rng, jst_time(rng, day, HUMAN_HOUR), weighted(rng, {"/plan/winter": 4, "/access": 4, "/blog/matsuri-2026": 2, "/onsen": 2}),
                            ua, pick_cat(rng, cat), "ChatGPT-User", fixed))
        # 仕込み6: ClaudeBot は robots.txt で拒否され、robots.txt しか取らない
        for _ in range(rng.choice([1, 2])):
            ev.append(event(rng, jst_time(rng, day), "/robots.txt", CLAUDEBOT[0], CLAUDEBOT[1], "ClaudeBot", fixed))
        # 従来の検索ボット
        for name, (ua, cat, mean) in SEARCH_BOTS.items():
            start = jst_time(rng, day)
            for t in burst(rng, start, count(rng, mean), 2, 8):
                ev.append(event(rng, t, weighted(rng, SEARCH_PATHS), ua, cat, name, fixed))
        # 仕込み4: 未知のボットが探る
        for _ in range(count(rng, 7)):
            ev.append(event(rng, jst_time(rng, day), rng.choice(NOISE_PATHS), rng.choice(NOISE_UAS), "", "noise", fixed))
    # 仕込み7: GPTBotを名乗るスクレイパー（検証に失敗＝カテゴリ空）。週に1回ほどのバースト
    for d in range(0, days, 7 if days >= 28 else 5):
        day = start_day + timedelta(days=d)
        for t in burst(rng, jst_time(rng, day), 40, 0.2, 0.8):
            ev.append(event(rng, t, weighted(rng, {"/": 2, "/rooms": 3, "/plan/winter": 3, "/plan/summer": 3, "/onsen": 3, "/meals": 3}),
                            SPOOF_UA, "", "spoof-gptbot", fixed))
    ev.sort(key=lambda e: e["ts"])
    return ev


def to_logpush(e):
    return {"ClientRequestHost": HOST, "ClientRequestMethod": "GET", "ClientRequestURI": e["uri"],
            "ClientRequestReferer": e["ref"], "ClientRequestUserAgent": e["ua"],
            "EdgeResponseBytes": e["bytes"], "EdgeResponseStatus": e["status"],
            "EdgeStartTimestamp": e["ts"].strftime("%Y-%m-%dT%H:%M:%SZ"), "VerifiedBotCategory": e["cat"]}


def to_nginx(rng, e):
    if e["actor"] in ("human", "ai-answer-visitor", "utm-not-human"):
        ip = f"198.51.100.{rng.randrange(1, 255)}"
    elif e["actor"] in ("noise", "spoof-gptbot"):
        ip = f"203.0.113.{rng.randrange(1, 255)}"
    else:
        ip = "192.0.2." + str(10 + sorted(set(BOTS) | set(SEARCH_BOTS) | {"ChatGPT-User", "ClaudeBot"}).index(e["actor"]))
    t = e["ts"].astimezone(JST).strftime("%d/%b/%Y:%H:%M:%S +0900")
    ref = e["ref"] or "-"
    return f'{ip} - - [{t}] "GET {e["uri"]} HTTP/1.1" {e["status"]} {e["bytes"]} "{ref}" "{e["ua"]}"'


def site_snapshot(fixed):
    pages = [
        {"path": "/", "title": "雪待荘", "h1": "雪待荘へようこそ", "words": 420, "in_sitemap": True},
        {"path": "/rooms", "title": "お部屋", "h1": "お部屋のご案内", "words": 610, "in_sitemap": True},
        {"path": "/plan/winter", "title": "冬の宿泊プラン", "h1": "冬の宿泊プラン", "words": 540, "in_sitemap": True},
        {"path": "/plan/summer", "title": "夏の宿泊プラン", "h1": "夏の宿泊プラン", "words": 500, "in_sitemap": True},
        {"path": "/onsen", "title": "温泉", "h1": "かけ流しの温泉", "words": 480, "in_sitemap": True},
        {"path": "/meals", "title": "お食事", "h1": "お食事", "words": 45, "in_sitemap": True},
        {"path": "/blog/matsuri-2026", "title": "町の雪まつり2026", "h1": "町の雪まつり2026", "words": 1300, "in_sitemap": True},
        {"path": "/contact", "title": "お問い合わせ", "h1": "お問い合わせ", "words": 150, "in_sitemap": True},
    ]
    if fixed:
        pages[5] = {"path": "/meals", "title": "お食事", "h1": "お食事", "words": 420, "in_sitemap": True}  # シナリオ: 書き直した
        pages.append({"path": "/access", "title": "アクセス", "h1": "アクセス", "words": 380, "in_sitemap": True})
    robots = "User-agent: *\nAllow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n\nSitemap: https://%s/sitemap.xml\n" % HOST
    sitemap = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
               + "".join(f"  <url><loc>https://{HOST}{p['path']}</loc></url>\n" for p in pages) + "</urlset>\n")
    return pages, robots, sitemap


def expected(before, after):
    def n(ev, actors, uri, status=None, cat_any=True):
        return sum(1 for e in ev if e["actor"] in actors and e["uri"].split("?")[0] == uri
                   and (status is None or e["status"] == status))
    ai = {"GPTBot", "OAI-SearchBot", "PerplexityBot", "ChatGPT-User"}
    return {
        "1_access_missing": {"ai_404_before": n(before, ai, "/access", 404), "ai_404_after": n(after, ai, "/access", 404),
                             "ai_200_after": n(after, ai, "/access", 200)},
        "2_moved_no_redirect": {"ai_404_old_path_before": n(before, ai, "/plans/winter", 404),
                                "ai_301_old_path_after": n(after, ai, "/plans/winter", 301),
                                "ai_answer_visitors_new_path_before": n(before, {"ai-answer-visitor"}, "/plan/winter", 200)},
        "3_healthy": {"ai_200": n(before, ai, "/blog/matsuri-2026", 200), "ai_non200": n(before, ai, "/blog/matsuri-2026") - n(before, ai, "/blog/matsuri-2026", 200)},
        "4_noise": {"requests": sum(1 for e in before if e["actor"] == "noise"),
                    "non404": sum(1 for e in before if e["actor"] == "noise" and e["status"] != 404)},
        "5_thin_page": {"ai_fetches_meals": n(before, ai, "/meals"), "human_fetches_meals": n(before, {"human"}, "/meals")},
        "6_robots_block": {"claudebot_requests": sum(1 for e in before if e["actor"] == "ClaudeBot"),
                           "claudebot_non_robots": sum(1 for e in before if e["actor"] == "ClaudeBot" and e["uri"] != "/robots.txt")},
        "7_spoofed_gptbot": {"requests": sum(1 for e in before if e["actor"] == "spoof-gptbot"),
                             "verified_category_nonempty": sum(1 for e in before if e["actor"] == "spoof-gptbot" and e["cat"])},
        "8_utm_requests": {"human_200": sum(1 for e in before if e["actor"] == "ai-answer-visitor" and e["status"] == 200),
                           "not_human": sum(1 for e in before if e["actor"] == "utm-not-human"),
                           "not_human_200": sum(1 for e in before if e["actor"] == "utm-not-human" and e["status"] == 200)},
        "totals": {"before": len(before), "after": len(after)},
    }


def write_all(out):
    rng = random.Random(SEED)
    before = generate(rng, BEFORE_START, BEFORE_DAYS, fixed=False)
    after = generate(rng, AFTER_START, AFTER_DAYS, fixed=True)
    out.mkdir(parents=True, exist_ok=True)
    for name, ev in (("before", before), ("after", after)):
        (out / f"{name}.ndjson").write_text("".join(json.dumps(to_logpush(e), ensure_ascii=False) + "\n" for e in ev), encoding="utf-8")
        (out / f"{name}.nginx.txt").write_text("".join(to_nginx(rng, e) + "\n" for e in ev), encoding="utf-8")
        pages, robots, sitemap = site_snapshot(name == "after")
        site = out / "site" / name
        site.mkdir(parents=True, exist_ok=True)
        (site / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (site / "robots.txt").write_text(robots, encoding="utf-8")
        (site / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (out / "expected.json").write_text(json.dumps(expected(before, after), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_all(Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/ryokan"))
