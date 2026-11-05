"""「調べた順番」: ブリーフの目印を、問題の大きい順に並べた作業の記録。

事実（回数・根拠）はブリーフから、判断は Claude の下書きから取る。演出はしない:
対応する下書きが無い手順に、判断を付け足さない。
"""
ACTIONS = ("new_page", "rewrite_page", "redirect", "fix_config")


def _verdict(drafts, target, kinds=ACTIONS):
    for d in drafts:
        if d["target"] == target and d["kind"] in kinds:
            return d["title"]
    return ""


def build_trace(brief, drafts):
    s, steps = brief["signals"], []
    total_ai = sum(sum(p["ai"].values()) for p in brief["pages"].values())
    steps.append({"title": "全体を数える", "finding": f"{brief['total_requests']:,}件のアクセスのうち、AIがページを読んだのは{total_ai:,}回でした。",
                  "verdict": "", "evidence": []})
    for e in s["ai_errors"]:
        who = "、".join(e["bots"])
        steps.append({"title": f"{e['path']} が読めなかった理由を調べる",
                      "finding": f"{who} が{e['count']}回読みに来て、読めませんでした。",
                      "verdict": _verdict(drafts, e["path"]), "evidence": e["evidence"]})
    for r in s["robots_blocks"]:
        steps.append({"title": f"{r['bot']} の動きを調べる",
                      "finding": f"{r['requests']}回来ましたが、案内ファイル（robots.txt）で断られていて、ページは読まれていません。"
                                 if r["only_robots_txt"] else f"{r['requests']}回来ています。案内ファイルでは断られています。",
                      "verdict": _verdict(drafts, "/robots.txt"), "evidence": r["evidence"]})
    for p in s["pages_ai_never_fetched"]:
        v = _verdict(drafts, p["path"])
        if v:
            steps.append({"title": f"{p['path']} をAIが読まない理由を調べる",
                          "finding": f"お客様は{p['human']}回読んでいますが、AIは一度も読みに来ていません。",
                          "verdict": v, "evidence": p["evidence"]})
    for u in s["unverified_ai_claims"]:
        steps.append({"title": f"{u['bot']} を名乗るアクセスを確かめる",
                      "finding": f"{u['bot']} を名乗る{u['verified'] + u['unverified']}回のうち、本物と確認できたのは{u['verified']}回です。"
                                 f"確認できない{u['unverified']}回は、AIが読んだ回数に数えません。",
                      "verdict": "", "evidence": u["evidence"]})
    if s["noise"]["requests"]:
        steps.append({"title": "AIとは関係のないアクセスを分ける",
                      "finding": f"サイトの弱点を探す自動のアクセスが{s['noise']['requests']}回ありました。調べる対象から外します。",
                      "verdict": "", "evidence": s["noise"]["evidence"]})
    if s["healthy_pages"]:
        steps.append({"title": "問題なく読まれているページを確かめる",
                      "finding": f"{len(s['healthy_pages'])}ページは、AIが読みに来て、すべて読めています。手を付けません。",
                      "verdict": "", "evidence": [i for h in s["healthy_pages"] for i in h["evidence"][:1]]})
    return steps
