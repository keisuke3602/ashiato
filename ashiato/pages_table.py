"""全体のページ一覧: 「読まれている / ページがない / 一部のAIに断られている / 読まれていない」。"""

LABELS = ("ページがない", "一部のAIに断られている", "読まれていない", "読まれている")


def _page_status(p, in_site):
    failed = {st: n for st, n in p["ai"].items() if st[0] in "45"}
    ok = sum(n for st, n in p["ai"].items() if st[0] in "23")
    if failed and "404" in failed and not in_site and not ok:
        return LABELS[0]
    if failed:
        return LABELS[1] if ok or in_site else LABELS[0]
    if ok:
        return LABELS[3]
    return LABELS[2]


def page_rows(brief):
    site = {p["path"] for p in brief["site_pages"]}
    empty = {"ai": {}, "human": 0, "ai_answer_visitors": 0}
    paths = sorted(site | {path for path, p in brief["pages"].items() if any(st[0] in "45" for st in p["ai"])})
    rows = []
    for path in paths:
        p = brief["pages"].get(path, empty)
        rows.append({"path": path, "status": _page_status(p, path in site),
                     "ai_ok": sum(n for st, n in p["ai"].items() if st[0] in "23"),
                     "ai_failed": sum(n for st, n in p["ai"].items() if st[0] in "45"),
                     "ai_answer_visitors": p["ai_answer_visitors"], "human": p["human"]})
    return sorted(rows, key=lambda r: (LABELS.index(r["status"]), -r["ai_failed"], -r["ai_ok"], r["path"]))
