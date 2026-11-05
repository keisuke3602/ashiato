"""見本の下書き。Claude ではなく、決まった規則で作る（画面の開発と、API キー無しの確認用）。

画面には「見本」と出す。実際の助言は Claude が prompts/advisor_ja.md に従って書く。
"""


def _label(path):
    return path.strip("/").replace("/", " ・ ").replace("-", " ") or "トップ"


def sample_drafts(brief):
    s, name, out = brief["signals"], brief["site_name"], []
    cand = {c["from"]: c for c in s["redirect_candidates"]}
    for e in s["ai_errors"]:
        if e["status"] == 404 and e["path"] in cand:
            c = cand[e["path"]]
            out.append({"kind": "redirect", "target": e["path"], "priority": "high", "evidence": e["evidence"],
                        "title": f"古いアドレス {e['path']} を新しいアドレス {c['to']} に転送する",
                        "why": f"AIが {e['path']} を{e['count']}回読みに来ましたが、ページが無く読めませんでした。"
                               f"同じ内容のページは {c['to']} にあります。転送を足せば、読めるようになります。",
                        "body": f"{e['path']} → {c['to']}（恒久的な転送）"})
        elif e["status"] == 404 and not e["in_site"]:
            out.append({"kind": "new_page", "target": e["path"], "priority": "high", "evidence": e["evidence"],
                        "title": f"{e['path']} のページを作る",
                        "why": f"AIが {e['path']} を{e['count']}回読みに来ましたが、ページが無く読めませんでした。"
                               f"AIが探している内容に答えるページを用意すると、{name}を紹介してもらいやすくなります。",
                        "body": f"【下書き】{_label(e['path'])}\n\n（ここに、{name}の実際の情報を入れてください。"
                                f"場所・手順・料金など、お客様がよく聞くことから書き始めます。）"})
        elif e["status"] in (403, 429) or e["status"] >= 500:
            out.append({"kind": "fix_config", "target": e["path"], "priority": "high", "evidence": e["evidence"],
                        "title": f"{e['path']} が一部のAIにだけ断られています",
                        "why": f"{', '.join(e['bots'])} が {e['path']} を{e['count']}回読みに来ましたが、すべて断られました。"
                               f"サイトの守りの設定が強すぎる可能性があります。人の訪問は通っています。",
                        "body": f"サイトの守りの設定で、{', '.join(e['bots'])} を {e['path']} に限って許可するか、"
                                f"制限の強さを見直してください。"})
    for r in s["robots_blocks"]:
        out.append({"kind": "fix_config", "target": "/robots.txt", "priority": "high", "evidence": r["evidence"],
                    "title": f"{r['bot']} がサイト全体を断られています",
                    "why": f"{r['bot']} は{r['requests']}回来ましたが、案内ファイルで断られているため、設定の確認以外は何も読めていません。"
                           f"意図した設定か確認してください。",
                    "body": f"User-agent: {r['bot']}\nDisallow: /\n\n↑ 意図していなければ、この2行を消します。"})
    for p in s["pages_ai_never_fetched"]:
        if p.get("words") is not None and p["words"] < 100:
            out.append({"kind": "rewrite_page", "target": p["path"], "priority": "low", "evidence": p["evidence"],
                        "title": f"{p['path']} の内容を充実させる",
                        "why": f"お客様は読んでいますが、AIは一度も読みに来ていません。ページの文字が少なく（{p['words']}語）、"
                               f"AIに紹介される材料が足りない可能性があります。",
                        "body": "（写真の説明、メニューの内容、アレルギー対応など、聞かれることを足します。）"})
    for h in s["healthy_pages"]:
        out.append({"kind": "leave_alone", "target": h["path"], "priority": "low", "evidence": h["evidence"],
                    "title": f"{h['path']} は、このままで大丈夫です",
                    "why": f"AIが{h['ai_fetches']}回読みに来て、すべて問題なく読めています。手を付ける必要はありません。",
                    "body": ""})
    if s["noise"]["requests"]:
        out.append({"kind": "ignore", "target": "", "priority": "low", "evidence": s["noise"]["evidence"],
                    "title": "無視してよいアクセス",
                    "why": f"サイトの弱点を探す自動のアクセスが{s['noise']['requests']}回ありました。AIとは関係ないので、気にしなくて大丈夫です。",
                    "body": ""})
    for u in s["unverified_ai_claims"]:
        out.append({"kind": "ignore", "target": "", "priority": "low", "evidence": u["evidence"],
                    "title": f"{u['bot']} を名乗る、本物と確認できないアクセス",
                    "why": f"{u['bot']} を名乗るアクセスのうち{u['unverified']}回は、本物かどうか確認できませんでした。"
                           f"AIが読んだ回数には数えていません。",
                    "body": ""})
    return [dict(d, source="sample") for d in out if d["evidence"]]
