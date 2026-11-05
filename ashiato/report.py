"""日本語のレポート画面（HTML 1枚）。承認・修正・却下はブラウザ内の印だけで、サイトには何も書き込まない。"""
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


def _card(i, d, actions=True):
    ev = " ".join(escape(str(x)) for x in d["evidence"])
    body = f"<pre>{escape(d['body'])}</pre>" if d["body"] else ""
    btn = ('<div class="acts"><button data-v="approve" aria-pressed="false">承認</button>'
           '<button data-v="edit" aria-pressed="false">修正する</button>'
           '<button data-v="reject" aria-pressed="false">却下</button></div>') if actions else ""
    return (f'<div class="card" data-id="{i}"><h3>{escape(d["title"])}</h3>'
            f'<span class="tag {d["priority"]}">{PRIORITY_LABEL[d["priority"]]}</span>'
            f'<span class="tag">{KIND_LABEL[d["kind"]]}</span><p>{escape(d["why"])}</p>{body}'
            f'<p class="ev">根拠の記録: {ev}</p>{btn}</div>')


def render_report(brief, drafts):
    acts = sorted([d for d in drafts if d["kind"] not in ("leave_alone", "ignore")], key=lambda d: PRIORITY_ORDER[d["priority"]])
    rest = [d for d in drafts if d["kind"] in ("leave_alone", "ignore")]
    sample = any(d.get("source") == "sample" for d in drafts)
    p = brief["period"] or {"from": "", "to": ""}
    tiles = "".join(f'<div class="tile {c}"><b>{n:,}</b><span>{escape(t)}</span></div>' for t, n, c in _tiles(brief))
    note = ('<p class="sub">※ これは見本の下書きです。実際の助言はClaudeが書きます。</p>' if sample else "")
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>足跡 {escape(brief['site_name'])}</title><style>{CSS}</style></head><body><main>
<h1>{escape(brief['site_name'])} のAI足跡</h1>
<div class="sub">{escape(p['from'])} 〜 {escape(p['to'])} のアクセスをもとにしています。承認するまで、サイトには何も反映されません。</div>
{note}<div class="tiles">{tiles}</div>
<h2>次にやること（{len(acts)}件）</h2>
{''.join(_card(i, d) for i, d in enumerate(acts)) or '<p class="sub">今回は、対応が必要なものはありません。</p>'}
<h2>手を付けなくてよいこと（{len(rest)}件）</h2>
{''.join(_card(100 + i, d, actions=False) for i, d in enumerate(rest))}
</main><script>{JS}</script></body></html>"""
