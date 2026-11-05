"""日本語のレポート画面（HTML 1枚）。承認・修正・却下はブラウザ内の印だけで、サイトには何も書き込まない。"""
from datetime import datetime, timedelta
from html import escape

KIND_LABEL = {"new_page": "ページを作る", "rewrite_page": "書き直す", "redirect": "転送を足す",
              "fix_config": "設定を見直す", "leave_alone": "手を付けない", "ignore": "無視してよい"}
PRIORITY_LABEL = {"high": "先にやる", "mid": "次にやる", "low": "余裕があれば"}
PRIORITY_ORDER = {"high": 0, "mid": 1, "low": 2}

CSS = """
:root{--bg:#faf8f5;--card:#fff;--ink:#2b2622;--sub:#6f655c;--line:#e6dfd6;--accent:#b4532a;--ok:#2f6b4f;--warn:#a1631a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#1d1a17;--card:#27231f;--ink:#f2ece4;--sub:#b3a99e;--line:#3a3430;--accent:#e38b5f;--ok:#7cc5a0;--warn:#e0a85c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.15rem;margin:36px 0 12px}
.sub{color:var(--sub);font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.tile b{display:block;font-size:2rem;line-height:1.2}.tile span{color:var(--sub);font-size:.88rem}
.tile.bad b{color:var(--warn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.card h3{margin:0 0 6px;font-size:1.05rem}.tag{display:inline-block;font-size:.78rem;border:1px solid var(--line);border-radius:99px;padding:0 10px;margin-right:6px;color:var(--sub)}
.tag.high{color:var(--accent);border-color:var(--accent)}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:inherit;font-size:.92rem}
.ev{color:var(--sub);font-size:.8rem;word-break:break-all}
.acts button{font:inherit;font-size:.9rem;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 14px;margin-right:6px;cursor:pointer}
.acts button[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.card.done-reject{opacity:.55}
.trace{padding-left:1.2em}.trace li{margin-bottom:14px}.verdict{color:var(--accent);font-size:.95rem}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}th{color:var(--sub);font-weight:400;font-size:.88rem}
"""

JS = """
document.querySelectorAll('.card[data-id]').forEach(function(card){
  var key='ashiato:'+card.dataset.id, buttons=card.querySelectorAll('button');
  function mark(v){buttons.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.v===v)});card.classList.toggle('done-reject',v==='reject')}
  try{mark(localStorage.getItem(key)||'')}catch(e){}
  buttons.forEach(function(b){b.addEventListener('click',function(){mark(b.dataset.v);try{localStorage.setItem(key,b.dataset.v)}catch(e){}})});
});
"""


def _tiles(brief):
    ai = sum(sum(p["ai"].values()) for p in brief["pages"].values())
    bad = sum(n for p in brief["pages"].values() for st, n in p["ai"].items() if st[0] in "45")
    visitors = sum(p["ai_answer_visitors"] for p in brief["pages"].values())
    return [("AIがページを読みに来た回数", ai, ""), ("そのうち、読めなかった回数", bad, "bad" if bad else ""),
            ("AIの回答から来たお客様", visitors, "")]


def _when(ts):
    """UTC の時刻文字列を、日本時間の「9月12日 14:03」に直す。"""
    t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=9)
    return f"{t.month}月{t.day}日 {t:%H:%M}"


def _evidence(d, times):
    ids = d["evidence"]
    whens = list(dict.fromkeys(_when(times[i]) for i in ids if i in times))
    head = "根拠: " + "、".join(whens[:3]) + (f" ほか{len(ids)}件の記録" if len(whens) > 3 or len(ids) > 3 else "") if whens else "根拠あり"
    return (f'<div class="ev">{escape(head)}<details><summary>記録番号</summary>'
            f'{escape(" ".join(map(str, ids)))}</details></div>')


def _card(i, d, times, actions=True):
    body = f"<pre>{escape(d['body'])}</pre>" if d["body"] else ""
    btn = ('<div class="acts"><button data-v="approve" aria-pressed="false">承認</button>'
           '<button data-v="edit" aria-pressed="false">修正する</button>'
           '<button data-v="reject" aria-pressed="false">却下</button></div>') if actions else ""
    return (f'<div class="card" data-id="{i}"><h3>{escape(d["title"])}</h3>'
            f'<span class="tag {d["priority"]}">{PRIORITY_LABEL[d["priority"]]}</span>'
            f'<span class="tag">{KIND_LABEL[d["kind"]]}</span><p>{escape(d["why"])}</p>{body}'
            f'{_evidence(d, times)}{btn}</div>')


def _healthy(healthy):
    if not healthy:
        return ""
    items = "".join(f"<li>{escape(d['target'] or d['title'])} <span class=\"ev\">記録番号: {escape(' '.join(map(str, d['evidence'])))}</span></li>"
                    for d in healthy)
    count = f"（{len(healthy)}件）" if all(d["target"] for d in healthy) else ""
    return (f'<div class="card"><h3>問題なく読まれているページ{count}</h3>'
            f'<p>AIが読みに来て、すべて読めています。このままで大丈夫です。</p>'
            f'<details><summary>ページの一覧</summary><ul>{items}</ul></details></div>')


def _compare(c):
    if not c:
        return ""
    def row(label, d):
        return f'<tr><td>{escape(label)}</td><td>{d["before"]:g}</td><td>{d["after"]:g}</td></tr>'
    paths = "".join(f'<tr><td>{escape(r["path"])}</td><td>{r["before_failed_per_day"]:g}</td><td>{r["after_failed_per_day"]:g}</td></tr>' for r in c["paths"])
    return (f'<h2>直したあとの変化</h2><div class="card"><p class="sub">直す前（{c["days"]["before"]}日分）と、直したあと（{c["days"]["after"]}日分）を、1日あたりで比べています。</p>'
            f'<table><tr><th></th><th>直す前</th><th>直したあと</th></tr>'
            + row('AIが読めた回数（1日）', c['ok_per_day']) + row('AIが読めなかった回数（1日）', c['failed_per_day'])
            + row('AIの回答から来たお客様（1日）', c['ai_answer_visitors_per_day'])
            + f'</table><details><summary>読めなかったページ別</summary><table><tr><th>ページ</th><th>直す前（1日）</th><th>直したあと（1日）</th></tr>{paths}</table></details></div>')


def _trace(steps, times):
    if not steps:
        return ""
    items = []
    for st in steps:
        verdict = f'<div class="verdict">Claudeの判断: {escape(st["verdict"])}</div>' if st["verdict"] else ""
        ev = _evidence({"evidence": st["evidence"]}, times) if st["evidence"] else ""
        items.append(f'<li><b>{escape(st["title"])}</b><div>{escape(st["finding"])}</div>{verdict}{ev}</li>')
    return ('<h2>調べた順番</h2><p class="sub">集計をもとに、問題の大きい順に確かめた記録です。回数と根拠は記録から、判断はClaudeが書いたものです。</p>'
            f'<ol class="trace">{"".join(items)}</ol>')


def render_report(brief, drafts, compare=None, trace=None):
    acts = sorted([d for d in drafts if d["kind"] not in ("leave_alone", "ignore")], key=lambda d: PRIORITY_ORDER[d["priority"]])
    healthy = [d for d in drafts if d["kind"] == "leave_alone"]
    ignored = [d for d in drafts if d["kind"] == "ignore"]
    times = brief.get("evidence_times", {})
    sample = any(d.get("source") == "sample" for d in drafts)
    p = brief["period"] or {"from": "", "to": ""}
    tiles = "".join(f'<div class="tile {c}"><b>{n:,}</b><span>{escape(t)}</span></div>' for t, n, c in _tiles(brief))
    note = ('<p class="sub">※ これは見本の下書きです。実際の助言はClaudeが書きます。</p>' if sample else
            '<p class="sub">下書きはClaudeが書きました。公開する前に、必ず内容を確認してください。</p>'
            if any(d.get("source") == "claude" for d in drafts) else "")
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>足跡 {escape(brief['site_name'])}</title><style>{CSS}</style></head><body><main>
<h1>{escape(brief['site_name'])} のAI足跡</h1>
<div class="sub">{escape(p['from'])} 〜 {escape(p['to'])} のアクセスをもとにしています。承認するまで、サイトには何も反映されません。</div>
{note}<div class="tiles">{tiles}</div>
{_trace(trace, times)}
<h2>次にやること（{len(acts)}件）</h2>
{''.join(_card(i, d, times) for i, d in enumerate(acts)) or '<p class="sub">今回は、対応が必要なものはありません。</p>'}
{_compare(compare)}
<h2>手を付けなくてよいこと</h2>
{_healthy(healthy)}
{''.join(_card(100 + i, d, times, actions=False) for i, d in enumerate(ignored))}
</main><script>{JS}</script></body></html>"""
