"""集計結果とサイトの情報から、Claude に渡す「ブリーフ」を作る。生ログは含めない。

ブリーフ = 期間・ページ別/ボット別の集計 + 事実の目印（signals）。signals は事実の抜き出しだけで、
「何を書くか・無視するか」の判断は Claude がする。根拠の行IDは、ブリーフに入っているものだけが使える。
"""
import json
from difflib import SequenceMatcher
from pathlib import Path

from .classify import AI_KINDS

HEALTHY_MIN_FETCHES = 20


def load_site(site_dir):
    site_dir = Path(site_dir)
    return {"pages": json.loads((site_dir / "pages.json").read_text(encoding="utf-8")),
            "robots_txt": (site_dir / "robots.txt").read_text(encoding="utf-8")}


def blocked_agents(robots_txt):
    """robots.txt で全体を拒否されているUA名（小文字）。'*' も含む。"""
    blocked, group, in_rules = set(), [], False
    for line in robots_txt.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            group, in_rules = [], False
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                group, in_rules = [], False
            group.append(value.lower())
        elif key in ("disallow", "allow"):
            in_rules = True
            if key == "disallow" and value == "/":
                blocked.update(group)
    return blocked


def _signals(agg, site):
    site_paths = {p["path"] for p in site["pages"]}
    pages = agg["pages"]
    ai_errors = []
    for path, p in pages.items():
        for status, count in p["ai"].items():
            if status[0] in "45":
                ai_errors.append({"path": path, "status": int(status), "count": count, "in_site": path in site_paths,
                                  "bots": sorted(b for b, st in p["ai_by_bot"].items() if status in st),
                                  "evidence": p["evidence"].get(status, [])})
    redirect_candidates = []
    for e in ai_errors:
        if e["status"] != 404 or e["in_site"]:
            continue
        best = max(site_paths, key=lambda sp: SequenceMatcher(None, e["path"], sp).ratio())
        ratio = SequenceMatcher(None, e["path"], best).ratio()
        if ratio >= 0.8:
            target = pages.get(best, {})
            redirect_candidates.append({"from": e["path"], "to": best, "similarity": round(ratio, 2),
                                        "to_ai_answer_visitors": target.get("ai_answer_visitors", 0),
                                        "evidence": e["evidence"]})
    not_fetched = [{"path": sp["path"], "title": sp.get("title", ""), "words": sp.get("words"),
                    "human": pages.get(sp["path"], {}).get("human", 0),
                    "evidence": pages.get(sp["path"], {}).get("evidence", {}).get("human", [])}
                   for sp in site["pages"]
                   if not pages.get(sp["path"], {}).get("ai") and pages.get(sp["path"], {}).get("human", 0) > 0]
    blocked = blocked_agents(site["robots_txt"])
    robots_blocks = [{"bot": name, "requests": b["requests"], "only_robots_txt": b["only_robots_txt"],
                      "evidence": b["evidence"].get("robots", [])}
                     for name, b in agg["bots"].items() if b["kind"] in AI_KINDS and name.lower() in blocked]
    unverified = [{"bot": name, "unverified": b["unverified"], "verified": b["verified"],
                   "evidence": b["evidence"].get("unverified", [])}
                  for name, b in agg["bots"].items() if b["kind"] in AI_KINDS and b["unverified"] > 0]
    healthy = [{"path": path, "ai_fetches": sum(p["ai"].values()), "evidence": p["evidence"].get("200", [])}
               for path, p in pages.items()
               if sum(p["ai"].values()) >= HEALTHY_MIN_FETCHES and set(p["ai"]) <= {"200"}]
    ig = agg["ignored"]
    noise = {"requests": ig["scanner_requests"], "paths": dict(sorted(ig["scanner_paths"].items(), key=lambda kv: -kv[1])[:6]),
             "evidence": [i for ids in ig["scanner_evidence"].values() for i in ids][:8]}
    return {"ai_errors": sorted(ai_errors, key=lambda e: -e["count"]), "redirect_candidates": redirect_candidates,
            "pages_ai_never_fetched": not_fetched, "robots_blocks": robots_blocks, "unverified_ai_claims": unverified,
            "healthy_pages": healthy, "noise": noise, "robots_blocks_all_bots": "*" in blocked}


def build_brief(agg, site, site_name):
    return {"site_name": site_name, "period": agg["period"], "total_requests": agg["total_rows"],
            "site_pages": site["pages"], "robots_txt": site["robots_txt"],
            "pages": agg["pages"], "bots": agg["bots"], "evidence_times": agg["evidence_times"], "signals": _signals(agg, site)}


def known_ids(brief):
    """ブリーフの中に出てくる根拠の行ID。下書きの根拠はこの中から選ぶ。"""
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "evidence":
                    if isinstance(v, list):
                        found.update(v)
                    elif isinstance(v, dict):
                        for ids in v.values():
                            found.update(ids)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(brief)
    return found
