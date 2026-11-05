"""Claude の下書きを検証・保存する。根拠の行IDが無い、またはブリーフに無いIDを使う下書きは拒否する。"""
import json
import re
from pathlib import Path

KINDS = ("new_page", "rewrite_page", "redirect", "fix_config", "leave_alone", "ignore")
PRIORITIES = ("high", "mid", "low")
REQUIRED = ("kind", "target", "title", "why", "body", "priority", "evidence")
BANNED_TERMS = ("ユーザーエージェント", "ステータスコード", "User-Agent")  # 画面に出す文には使わない


def validate(draft, known):
    """問題の一覧を返す。空なら有効。"""
    problems = [f"{k} がありません" for k in REQUIRED if k not in draft]
    if problems:
        return problems
    if draft["kind"] not in KINDS:
        problems.append(f"kind が不正です: {draft['kind']}")
    if draft["priority"] not in PRIORITIES:
        problems.append(f"priority が不正です: {draft['priority']}")
    ev = draft["evidence"]
    if not isinstance(ev, list) or not ev:
        problems.append("根拠の行IDがありません")
    else:
        unknown = [i for i in ev if i not in known]
        if unknown:
            problems.append(f"ブリーフに無い行IDです: {', '.join(map(str, unknown[:3]))}")
    for field in ("title", "why"):
        for term in BANNED_TERMS:
            if term in str(draft[field]):
                problems.append(f"{field} に画面に出せない語があります: {term}")
    return problems


def parse_response(text, known):
    """Claude の返答（JSON配列。```で囲まれていてもよい）を、(有効な下書き, 拒否された下書きと理由) に分ける。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    data = json.loads(m.group(1) if m else text)
    if isinstance(data, dict):
        data = data.get("drafts", [])
    valid, rejected = [], []
    for d in data:
        problems = validate(d, known)
        (rejected if problems else valid).append({"draft": d, "problems": problems} if problems else d)
    return valid, rejected


def save(drafts, known, out_dir):
    """保存。1件でも無効なら何も書かずに ValueError。"""
    for d in drafts:
        problems = validate(d, known)
        if problems:
            raise ValueError(f"保存を拒否しました（{d.get('title', '?')}）: {'; '.join(problems)}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "drafts.json"
    path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
