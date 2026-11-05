"""直す前と直した後の、2つの集計を並べる。期間の日数が違うので、1日あたりで比べる。

読めた = 200番台と、転送されて読めた（300番台）。読めなかった = 400・500番台。
"""
from datetime import date


def _days(agg):
    p = agg["period"]
    return (date.fromisoformat(p["to"]) - date.fromisoformat(p["from"])).days + 1


def _counts(page):
    ok = sum(n for st, n in page["ai"].items() if st[0] in "23")
    failed = sum(n for st, n in page["ai"].items() if st[0] in "45")
    return ok, failed


def compare(before, after):
    db, da = _days(before), _days(after)
    rows = []
    for path in sorted(set(before["pages"]) | set(after["pages"])):
        b = _counts(before["pages"].get(path, {"ai": {}}))
        a = _counts(after["pages"].get(path, {"ai": {}}))
        if b[1] or a[1]:
            rows.append({"path": path, "before_ok_per_day": round(b[0] / db, 1), "before_failed_per_day": round(b[1] / db, 1),
                         "after_ok_per_day": round(a[0] / da, 1), "after_failed_per_day": round(a[1] / da, 1)})
    tot = lambda agg: [sum(_counts(p)[i] for p in agg["pages"].values()) for i in (0, 1)]  # noqa: E731
    (bo, bf), (ao, af) = tot(before), tot(after)
    visitors = lambda agg: sum(p["ai_answer_visitors"] for p in agg["pages"].values())  # noqa: E731
    return {"days": {"before": db, "after": da},
            "ok_per_day": {"before": round(bo / db, 1), "after": round(ao / da, 1)},
            "failed_per_day": {"before": round(bf / db, 1), "after": round(af / da, 1)},
            "ai_answer_visitors_per_day": {"before": round(visitors(before) / db, 1), "after": round(visitors(after) / da, 1)},
            "paths": rows}
