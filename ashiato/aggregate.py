"""行をページ別・ボット別に集計する。Claude に渡すのはこの結果だけ（生ログは渡さない）。

数え方（docs/design.md）:
- AIの需要に数えるのは、AIのUAで、検証済みの行だけ。未検証は bots[...]["unverified"] に分けて出す。
  nginx 形式のように検証の可否が不明（None）の行は、数えたうえで "unknown_verification" に印を付ける。
- 「AIの回答から来た人」は、utm_source=chatgpt* かリファラが chatgpt.com で、200 で、人らしい行だけ。
- 資産（画像・CSS・/_next/ など）と API はページに入れない。robots.txt と sitemap.xml は別に扱う。
- scanner（脆弱性を探る自動アクセス）はページに入れず ignored に回す。
"""
from collections import Counter, defaultdict
from urllib.parse import parse_qs

from .classify import AI_KINDS, classify_ua, is_verified

ASSET_PREFIXES = ("/_next/", "/cdn-cgi/", "/static/", "/assets/", "/images/", "/img/", "/css/", "/js/")
ASSET_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".map", ".woff", ".woff2", ".ttf")
API_PREFIXES = ("/api/", "/graphql")
META_PATHS = ("/robots.txt", "/sitemap.xml")
EVIDENCE_LIMIT = 5


def path_type(path):
    if path in META_PATHS:
        return "meta"
    low = path.lower()
    if low.startswith(API_PREFIXES):
        return "api"
    if low.startswith(ASSET_PREFIXES) or low.endswith(ASSET_SUFFIXES):
        return "asset"
    return "page"


def is_ai_answer_visitor(row):
    if row["status"] != 200:
        return False
    utm = parse_qs(row["query"]).get("utm_source", [""])[0].lower()
    return utm.startswith("chatgpt") or "chatgpt.com" in row["referer"].lower()


def _bump(table, key, status):
    table[key][str(status)] += 1


def aggregate(rows):
    times = {}  # 根拠に使った行ID -> 時刻（画面で日時に直すため）

    def keep(store, key, r, limit=EVIDENCE_LIMIT):
        """根拠の行IDを、キーごとに最初の limit 件だけ残す。"""
        if len(store[key]) < limit:
            store[key].append(r["id"])
            times[r["id"]] = r["ts"]

    pages = defaultdict(lambda: {"human": 0, "search": 0, "ai_answer_visitors": 0,
                                 "ai": Counter(), "ai_by_bot": defaultdict(Counter), "evidence": defaultdict(list)})
    bots = {}
    ignored = {"scanner_requests": 0, "scanner_paths": Counter(), "non_page_requests": Counter(),
               "scanner_evidence": defaultdict(list)}
    for r in rows:
        name, kind = classify_ua(r["ua"])
        ptype = path_type(r["path"])
        verified = is_verified(r["category"])
        if kind in AI_KINDS or kind == "search":
            b = bots.setdefault(name, {"kind": kind, "requests": 0, "verified": 0, "unverified": 0,
                                       "unknown_verification": 0, "paths": Counter(), "statuses": Counter(),
                                       "evidence": defaultdict(list)})
            if verified is False:
                keep(b["evidence"], "unverified", r)
            if r["path"] == "/robots.txt":
                keep(b["evidence"], "robots", r)
            b["requests"] += 1
            b["verified" if verified else "unverified" if verified is False else "unknown_verification"] += 1
            b["paths"][r["path"]] += 1
            b["statuses"][str(r["status"])] += 1
        if kind == "scanner":
            ignored["scanner_requests"] += 1
            ignored["scanner_paths"][r["path"]] += 1
            keep(ignored["scanner_evidence"], r["path"], r, 2)
            continue
        if ptype != "page":
            ignored["non_page_requests"][ptype] += 1
            continue
        p = pages[r["path"]]
        if kind in AI_KINDS:
            if verified is False:
                continue  # 未検証のAI名乗りは需要に数えない（bots に出る）
            p["ai"][str(r["status"])] += 1
            _bump(p["ai_by_bot"], name, r["status"])
            keep(p["evidence"], str(r["status"]), r)
        elif kind == "search":
            p["search"] += 1
        elif kind == "human":
            if is_ai_answer_visitor(r):
                p["ai_answer_visitors"] += 1
                keep(p["evidence"], "ai_answer_visitor", r, 3)
            else:
                p["human"] += 1
                keep(p["evidence"], "human", r, 3)
    for b in bots.values():
        b["only_robots_txt"] = set(b["paths"]) <= {"/robots.txt"}
        b["paths"] = dict(b["paths"])
        b["statuses"] = dict(b["statuses"])
        b["evidence"] = dict(b["evidence"])
    return {
        "total_rows": len(rows),
        "evidence_times": times,
        "period": {"from": min(r["ts"] for r in rows)[:10], "to": max(r["ts"] for r in rows)[:10]} if rows else None,
        "pages": {path: {"human": p["human"], "search": p["search"], "ai_answer_visitors": p["ai_answer_visitors"],
                         "ai": dict(p["ai"]), "ai_by_bot": {k: dict(v) for k, v in p["ai_by_bot"].items()},
                         "evidence": dict(p["evidence"])} for path, p in sorted(pages.items())},
        "bots": dict(sorted(bots.items())),
        "ignored": {"scanner_requests": ignored["scanner_requests"], "scanner_paths": dict(ignored["scanner_paths"]),
                    "scanner_evidence": dict(ignored["scanner_evidence"]),
                    "non_page_requests": dict(ignored["non_page_requests"])},
    }
