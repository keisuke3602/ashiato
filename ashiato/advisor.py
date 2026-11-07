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


def _check_demand(draft, brief, site):
    """需要にもとづく下書き（demand_basis）と、アクセス記録があるときの new_page を、ブリーフの事実と照らす。
    記録に根拠のない、思いつきのページ提案は通さない。"""
    demand = brief.get("demand")
    basis = draft.get("demand_basis")
    if demand is None:  # アクセス記録が無いとき（サイトの公開ページだけ）は、ここでは見ない
        return [f"demand_basis は、アクセスの記録があるときだけ使えます"] if basis else []
    guessed = {g["path"] for g in demand["guessed_missing"]}
    reading = {r["path"]: r for r in demand["reading"]}
    kind, target = draft["kind"], draft["target"]
    if basis == "guessed":
        if target not in guessed:
            return [f"{target} は、AIが探して無かったアドレスの一覧にありません。demand_basis を guessed にできません"]
        return []
    if basis == "reading":
        if kind != "new_page":
            return ["demand_basis が reading のときは、kind を new_page にしてください"]
        if target in site:
            return [f"{target} はサイトに既にあります。reading にもとづく new_page は、まだ無いページにしてください"]
        based = draft.get("based_on")
        if not based or not isinstance(based, list) or any(b not in reading for b in based):
            return ["based_on には、AIがよく読んでいるページ（demand.reading）のパスを入れてください"]
        allowed = {i for b in based for i in reading[b]["evidence"]}
        if any(i not in allowed for i in draft["evidence"]):
            return ["evidence は、based_on のページの根拠の行IDだけにしてください"]
        return []
    if basis is not None:
        return [f"demand_basis が不正です: {basis}"]
    if kind == "new_page" and target not in guessed and not all(str(i).startswith("site:") for i in draft["evidence"]):
        return [f"{target} の new_page には、AIが探した記録（demand.guessed_missing）か、demand_basis: reading か、サイトの公開ページ（site:...）の根拠が要ります"]
    return []


def check_against_brief(draft, brief):
    """下書きの種類が、ブリーフの事実と食い違っていないか。問題の一覧を返す（空なら問題なし）。"""
    s, site = brief["signals"], {p["path"] for p in brief["site_pages"]}
    cands = {c["from"] for c in s.get("redirect_candidates", [])}
    kind, target = draft["kind"], draft["target"]
    problems = _check_demand(draft, brief, site)
    if problems:
        return problems
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
