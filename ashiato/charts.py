"""簡易なグラフ（SVG）。外部のライブラリは使わない。色は画面の CSS 変数（--ok / --warn / --accent / --sub）に従う。

どのグラフにも、読み上げ用の説明（aria-label と <title>）を付ける。データが空でも落ちない。
"""
import math
from datetime import date, timedelta
from html import escape

W = 920


def _nice_max(v):
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


def _svg(w, h, label, body):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}" '
            f'xmlns="http://www.w3.org/2000/svg" style="max-width:{w}px;height:auto"><title>{escape(label)}</title>{body}</svg>')


def _axes(left, top, pw, ph, vmax, ticks=(0, 0.5, 1)):
    out = []
    for t in ticks:
        y = top + ph - ph * t
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" stroke="var(--line)" stroke-width="1"/>')
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="var(--sub)">{vmax * t:g}</text>')
    return "".join(out)


def day_series(daily, start=None, end=None):
    """{日付: {...}} を、日付の抜けを0で埋めた (ラベル, 日付, 値の辞書) の並びにする。"""
    if not daily and not (start and end):
        return []
    days = sorted(daily)
    a = date.fromisoformat(start or days[0])
    b = date.fromisoformat(end or days[-1])
    out, d = [], a
    while d <= b:
        iso = d.isoformat()
        out.append((f"{d.month}/{d.day}", iso, daily.get(iso, {})))
        d += timedelta(days=1)
    return out


def _xlabels(labels, left, pw, y, step=7):
    n = len(labels)
    if not n:
        return ""
    bw = pw / n
    idx = sorted({0, n - 1, *range(0, n, step)})
    return "".join(f'<text x="{left + bw * (i + .5):.1f}" y="{y}" font-size="11" text-anchor="middle" fill="var(--sub)">{escape(labels[i])}</text>'
                   for i in idx)


def stacked_days(series, label, split_after=None, split_text="直した"):
    """日ごとの、読めた（緑）と読めなかった（橙）の積み上げ棒。split_after: この番号の日のあとに、縦の区切りを入れる。"""
    left, top, pw, ph = 44, 14, W - 44 - 12, 190
    totals = [v.get("ai_ok", 0) + v.get("ai_failed", 0) for _, _, v in series]
    vmax = _nice_max(max(totals, default=0))
    n = max(len(series), 1)
    bw = pw / n
    bars = []
    for i, (_, iso, v) in enumerate(series):
        ok, bad = v.get("ai_ok", 0), v.get("ai_failed", 0)
        x = left + bw * i + bw * .12
        w = bw * .76
        h_ok, h_bad = ph * ok / vmax, ph * bad / vmax
        bars.append(f'<rect x="{x:.1f}" y="{top + ph - h_ok:.1f}" width="{w:.1f}" height="{h_ok:.1f}" fill="var(--ok)"><title>{escape(iso)} 読めた {ok}回</title></rect>')
        bars.append(f'<rect x="{x:.1f}" y="{top + ph - h_ok - h_bad:.1f}" width="{w:.1f}" height="{h_bad:.1f}" fill="var(--warn)"><title>{escape(iso)} 読めなかった {bad}回</title></rect>')
    split = ""
    if split_after is not None and 0 <= split_after < len(series) - 1:
        x = left + bw * (split_after + 1)
        split = (f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + ph}" stroke="var(--accent)" stroke-dasharray="4 3"/>'
                 f'<text x="{x + 4:.1f}" y="{top + 11}" font-size="11" fill="var(--accent)">{escape(split_text)}</text>')
    legend = (f'<rect x="{left}" y="{top + ph + 28}" width="10" height="10" fill="var(--ok)"/><text x="{left + 14}" y="{top + ph + 37}" font-size="11" fill="var(--sub)">読めた</text>'
              f'<rect x="{left + 60}" y="{top + ph + 28}" width="10" height="10" fill="var(--warn)"/><text x="{left + 74}" y="{top + ph + 37}" font-size="11" fill="var(--sub)">読めなかった</text>')
    body = _axes(left, top, pw, ph, vmax) + "".join(bars) + split + _xlabels([s[0] for s in series], left, pw, top + ph + 16) + legend
    return _svg(W, top + ph + 44, label, body)


def line_days(series, key, label, color="var(--accent)"):
    """日ごとの値の折れ線（AIの回答から来たお客様など）。"""
    left, top, pw, ph = 44, 14, W - 44 - 12, 120
    vals = [v.get(key, 0) for _, _, v in series]
    vmax = _nice_max(max(vals, default=0))
    n = max(len(series), 1)
    bw = pw / n
    pts = [(left + bw * (i + .5), top + ph - ph * val / vmax) for i, val in enumerate(vals)]
    poly = f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{color}" stroke-width="2"/>' if len(pts) > 1 else ""
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"><title>{escape(series[i][1])} {vals[i]}</title></circle>' for i, (x, y) in enumerate(pts))
    body = _axes(left, top, pw, ph, vmax) + poly + dots + _xlabels([s[0] for s in series], left, pw, top + ph + 16)
    return _svg(W, top + ph + 24, label, body)


def hbars(rows, label):
    """横棒。rows: (名前, 読めた, 読めなかった)。"""
    left, rh = 150, 28
    vmax = _nice_max(max((a + b for _, a, b in rows), default=0))
    pw = W - left - 70
    body = []
    for i, (name, ok, bad) in enumerate(rows):
        y = 8 + i * rh
        wo, wb = pw * ok / vmax, pw * bad / vmax
        nm = name if len(name) <= 18 else name[:17] + "…"
        body.append(f'<text x="{left - 8}" y="{y + 15}" font-size="12" text-anchor="end" fill="var(--ink)">{escape(nm)}</text>')
        body.append(f'<rect x="{left}" y="{y}" width="{wo:.1f}" height="18" fill="var(--ok)"><title>{escape(name)} 読めた {ok}回</title></rect>')
        body.append(f'<rect x="{left + wo:.1f}" y="{y}" width="{wb:.1f}" height="18" fill="var(--warn)"><title>{escape(name)} 読めなかった {bad}回</title></rect>')
        body.append(f'<text x="{left + wo + wb + 6:.1f}" y="{y + 14}" font-size="12" fill="var(--sub)">{ok + bad:,}</text>')
    return _svg(W, 16 + max(len(rows), 1) * rh, label, "".join(body))


def before_after(title, before, after, lower_is_better=False):
    """直す前と直したあとの2本の棒。"""
    w, h, top, ph = 300, 200, 36, 120
    vmax = _nice_max(max(before, after))
    good = "var(--ok)"
    bars = []
    for i, (name, v, color) in enumerate((("直す前", before, "var(--sub)"), ("直したあと", after, good))):
        bh = ph * v / vmax
        x = 50 + i * 110
        bars.append(f'<rect x="{x}" y="{top + ph - bh:.1f}" width="80" height="{bh:.1f}" fill="{color}"/>')
        bars.append(f'<text x="{x + 40}" y="{top + ph - bh - 6:.1f}" font-size="14" font-weight="600" text-anchor="middle" fill="var(--ink)">{v:g}</text>')
        bars.append(f'<text x="{x + 40}" y="{top + ph + 18}" font-size="12" text-anchor="middle" fill="var(--sub)">{name}</text>')
    head = f'<text x="{w / 2}" y="20" font-size="13" text-anchor="middle" fill="var(--ink)">{escape(title)}</text>'
    base = f'<line x1="30" y1="{top + ph}" x2="{w - 30}" y2="{top + ph}" stroke="var(--line)"/>'
    return _svg(w, h, f"{title}: 直す前 {before:g}、直したあと {after:g}", head + base + "".join(bars))


def share_bars(rows, label):
    """割合の横棒（100%）。rows: (名前, [(区分の名前, 割合%, 色), ...])。割合が小さい区分は、数字を出さない。"""
    left, rh, pw = 90, 44, W - 90 - 20
    body, legend, seen = [], [], []
    for i, (name, segs) in enumerate(rows):
        y = 10 + i * rh
        body.append(f'<text x="{left - 8}" y="{y + 21}" font-size="12" text-anchor="end" fill="var(--ink)">{escape(name)}</text>')
        x = left
        for seg, pct, color in segs:
            w = pw * pct / 100
            body.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" fill="{color}"><title>{escape(name)} {escape(seg)} {pct:g}%</title></rect>')
            if w > 46:
                body.append(f'<text x="{x + w / 2:.1f}" y="{y + 20}" font-size="12" font-weight="600" text-anchor="middle" fill="#fff">{pct:g}%</text>')
            x += w
            if (seg, color) not in seen:
                seen.append((seg, color))
    ly = 10 + len(rows) * rh + 4
    lx = left
    for seg, color in seen:
        legend.append(f'<rect x="{lx}" y="{ly}" width="10" height="10" fill="{color}"/><text x="{lx + 14}" y="{ly + 9}" font-size="11" fill="var(--sub)">{escape(seg)}</text>')
        lx += 14 + 12 * len(seg) + 18
    return _svg(W, ly + 22, label, "".join(body) + "".join(legend))
