"""助言者（Claude）への入力を作り、返答を検証して下書きにする。Claude を呼ぶ部分は、ここには入れない。

呼び出しの方式（Managed Agents / Agent SDK / 保存した返答の読み込み）は、この関数の外で差し替える。
どの方式でも、Claude に渡すのは build_request の結果だけ（ブリーフ + 指示文）。生ログは渡さない。
"""
import json
from pathlib import Path

from . import drafts as drafts_mod
from .brief import known_ids

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "advisor_ja.md"


def build_request(brief):
    """{"system": 指示文, "user": ブリーフ（JSON文字列）}。"""
    return {"system": PROMPT_PATH.read_text(encoding="utf-8"),
            "user": json.dumps(brief, ensure_ascii=False, indent=1)}


def check_against_brief(draft, brief):
    """下書きの種類が、ブリーフの事実と食い違っていないか。問題の一覧を返す（空なら問題なし）。"""
    s, site = brief["signals"], {p["path"] for p in brief["site_pages"]}
    cands = {c["from"] for c in s.get("redirect_candidates", [])}
    kind, target = draft["kind"], draft["target"]
    if kind == "redirect" and target not in cands:
        return [f"{target} には転送先の候補がありません。転送ではなく new_page にしてください"]
    if kind == "new_page" and target in site:
        return [f"{target} はサイトに既にあります。new_page ではなく rewrite_page にしてください"]
    if kind == "rewrite_page" and target not in site:
        return [f"{target} はサイトにありません。rewrite_page ではなく new_page にしてください"]
    return []


def accept(response_text, brief):
    """Claude の返答を検証する。(保存してよい下書き, 拒否された下書きと理由) を返す。
    拒否の理由は、そのまま Claude に返して、直させる。"""
    valid, rejected = drafts_mod.parse_response(response_text, known_ids(brief))
    ok = []
    for d in valid:
        problems = check_against_brief(d, brief)
        (rejected.append({"draft": d, "problems": problems}) if problems else ok.append(dict(d, source="claude")))
    return ok, rejected
