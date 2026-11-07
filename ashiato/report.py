"""日本語のレポート画面（HTML 1枚）。承認・修正・却下はブラウザ内の印だけで、サイトには何も書き込まない。"""
import hashlib
import json
import re
from datetime import datetime, timedelta
from html import escape

from . import charts
from .pages_table import LABELS, page_rows
from .sitecheck import THIN_WORDS

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
.howto{color:var(--sub);font-size:.92rem;margin:8px 0}
.exp textarea{width:100%;box-sizing:border-box;min-height:140px;font:inherit;font-size:.88rem;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);padding:10px}
.exp button{font:inherit;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:8px;padding:6px 16px;cursor:pointer;margin-top:8px}
.acts button[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.card.done-reject{opacity:.55}
.st{font-size:.8rem;border-radius:99px;padding:1px 10px;border:1px solid var(--line);white-space:nowrap;display:inline-block}.st0,.st1{color:var(--warn);border-color:var(--warn)}.st3{color:var(--ok);border-color:var(--ok)}
.trace{padding-left:1.2em}.trace li{margin-bottom:14px}.verdict{color:var(--accent);font-size:.95rem}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}th{color:var(--sub);font-weight:400;font-size:.88rem}
"""

JS = r"""
function refresh(){var box=document.getElementById('exp-text'),n=document.getElementById('exp-n');if(!box)return;var out=[],c=0;
  document.querySelectorAll('.card[data-id]').forEach(function(card){var a=card.querySelector('button[data-v=approve]');
    if(a&&a.getAttribute('aria-pressed')==='true'){c++;var pre=card.querySelector('pre'),hw=card.querySelector('.howto');out.push('■ '+card.querySelector('h3').textContent+'\n'+card.querySelector('p').textContent+(pre?'\n\n'+pre.textContent:'')+(hw?'\n\n'+hw.textContent:''))}});
  box.value=out.join('\n\n----------\n\n');n.textContent=c}
var cp=document.getElementById('exp-copy');if(cp)cp.addEventListener('click',function(){var box=document.getElementById('exp-text');box.select();try{navigator.clipboard.writeText(box.value)}catch(e){document.execCommand('copy')}cp.textContent='コピーしました'});
document.querySelectorAll('.card[data-id]').forEach(function(card){
  var key='ashiato:'+(typeof RID==='undefined'?'':RID+':')+card.dataset.id, buttons=card.querySelectorAll('button');
  function mark(v){buttons.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.v===v)});card.classList.toggle('done-reject',v==='reject');refresh()}
  try{mark(localStorage.getItem(key)||'')}catch(e){}
  buttons.forEach(function(b){b.addEventListener('click',function(){mark(b.dataset.v);try{localStorage.setItem(key,b.dataset.v)}catch(e){}})});
});
"""


def _tiles(brief):
    ai = sum(sum(p["ai"].values()) for p in brief["pages"].values())
    bad = sum(n for p in brief["pages"].values() for st, n in p["ai"].items() if st[0] in "45")
    visitors = sum(p["ai_answer_visitors"] for p in brief["pages"].values())
    return [("AIがページを読みに来た回数", ai, ""), ("そのうち、読めなかった回数", bad, "bad" if bad else ""),
            ("AIの回答から来た人（回）", visitors, "")]


def _site_tiles(brief):
    c = brief["site_check"]
    return [("調べたページ数", c["page_list"]["count"], ""),
            ("AIを断っている設定", len(c["ai_bots_blocked_in_robots"]), "bad" if c["ai_bots_blocked_in_robots"] else ""),
            ("本文が短いページ", len(c["thin_pages"]), "")]


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


BASIS_TAG = {"guessed": "AIが探していた", "reading": "続きの話題の候補"}


def _basis(d, brief):
    """需要にもとづく下書きの、「なぜ」の一行。数字は、Claudeではなく、ブリーフから出す。"""
    basis, demand = d.get("demand_basis"), (brief or {}).get("demand") or {}
    if basis == "guessed":
        g = next((x for x in demand.get("guessed_missing", []) if x["path"] == d["target"]), None)
        return f'<p class="basis">AIが、このアドレスを{g["count"]:,}回、探しました（{escape("、".join(g["bots"]))}）。</p>' if g else ""
    if basis == "reading":
        based = [r for r in demand.get("reading", []) if r["path"] in d.get("based_on", [])]
        if not based:
            return ""
        parts = "、".join(f'{escape(r["path"])}（AIが{r["ai_reads"]:,}回読み、AIの回答から来た人のアクセスが{r["ai_answer_visitors"]:,}回）' for r in based)
        return f'<p class="basis">AIがよく読んでいるページの、続きの話題の提案です。元のページ: {parts}。AIがこのページを探した記録があるわけではありません。</p>'
    return ""


def _card(i, d, times, actions=True, brief=None):
    body = f"<pre>{escape(d['body'])}</pre>" if d["body"] else ""
    howto = f'<p class="howto"><b>反映のしかた:</b> {escape(d["howto"])}</p>' if d.get("howto") else ""
    btn = ('<div class="acts"><button data-v="approve" aria-pressed="false">承認</button>'
           '<button data-v="edit" aria-pressed="false">修正する</button>'
           '<button data-v="reject" aria-pressed="false">却下</button></div>') if actions else ""
    tag = f'<span class="tag">{BASIS_TAG[d["demand_basis"]]}</span>' if d.get("demand_basis") in BASIS_TAG else ""
    pri = f'<span class="tag {d["priority"]}">{PRIORITY_LABEL[d["priority"]]}</span>' if actions else ""  # 無視してよいものに「余裕があれば」は付けない
    return (f'<div class="card" data-id="{i}"><h3>{escape(d["title"])}</h3>{pri}'
            f'<span class="tag">{KIND_LABEL[d["kind"]]}</span>{tag}<p>{escape(d["why"])}</p>{_basis(d, brief)}{body}{howto}'
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
            + row('AIの回答から来た人（回、1日）', c['ai_answer_visitors_per_day'])
            + f'</table><details><summary>読めなかったページ別</summary><table><tr><th>ページ</th><th>直す前（1日）</th><th>直したあと（1日）</th></tr>{paths}</table></details></div>')


def _pages(rows):
    body = "".join(f'<tr><td>{escape(r["path"])}</td><td><span class="st st{LABELS.index(r["status"])}">{escape(r["status"])}</span></td>'
                   f'<td>{r["ai_ok"]:,}</td><td>{r["ai_failed"]:,}</td><td>{r["ai_answer_visitors"]:,}</td><td>{r["human"]:,}</td></tr>'
                   for r in rows)
    return ('<h2>ページごとの様子</h2><div class="card" style="overflow-x:auto"><table><tr><th>ページ</th><th>AIから見て</th>'
            f'<th>読めた回数</th><th>読めなかった回数</th><th>AIの回答から来た人（回）</th><th>人のアクセス（回）</th></tr>{body}</table></div>')


def _ai_answers(a):
    if not a:
        return ""
    cards = []
    for it in a["items"]:
        cited = "あなたのサイトが、出典に入っていました。" if it["site_cited"] else "あなたのサイトは、出典に入っていませんでした。"
        named = "答えの中に、店名が出ていました。" if it["site_named"] else "答えの中に、店名は出ていませんでした。"
        doms = "、".join(it["cited_domains"]) or "（出典なし）"
        cards.append(f'<div class="card"><h3>{escape(it["question"])}</h3><p>{escape(it["answer"])}</p>'
                     f'<p class="sub">{cited}{named}<br>出典のサイト: {escape(doms)}</p>'
                     f'<div class="ev">記録番号: {escape(" ".join(it["evidence"]))}</div></div>')
    return (f'<h2>AIは、お客様の質問に、どう答えるか</h2><p class="sub">{escape(a["note"])}</p>' + "".join(cards))


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
    site_only = brief.get("mode") == "site_only"
    tiles = "".join(f'<div class="tile {c}"><b>{n:,}</b><span>{escape(t)}</span></div>' for t, n, c in (_site_tiles(brief) if site_only else _tiles(brief)))
    note = ('<p class="sub">※ これは見本の下書きです。実際の助言はClaudeが書きます。</p>' if sample else
            '<p class="sub">下書きはClaudeが書きました。公開する前に、必ず内容を確認してください。</p>'
            if any(d.get("source") == "claude" for d in drafts) else "")
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>足跡 {escape(brief['site_name'])}</title><style>{CSS}</style></head><body><main>
<h1>{escape(brief['site_name'])} のAI足跡</h1>
<div class="sub">{"サイトの公開ページをもとにしています（アクセスの記録は使っていません）。" if site_only else escape(p['from']) + " 〜 " + escape(p['to']) + " のアクセスをもとにしています。"}承認するまで、サイトには何も反映されません。</div>
{note}<div class="tiles">{tiles}</div>
{_pages(page_rows(brief)) if brief.get("site_pages") and not site_only else ""}
{_ai_answers(brief.get("ai_answers"))}
{_trace(trace, times)}
<h2>次にやること（{len(acts)}件）</h2>
{''.join(_card(i, d, times, brief=brief) for i, d in enumerate(acts)) or '<p class="sub">今回は、対応が必要なものはありません。</p>'}
<div class="exp"><h2>承認した下書き（<span id="exp-n">0</span>件）</h2>
<p class="sub">承認したものだけが、ここに集まります。コピーして、ご自分でサイトに反映してください。足跡は、サイトには何も書き込みません。</p>
<textarea id="exp-text" readonly placeholder="「承認」を押すと、ここに下書きが入ります"></textarea><br><button id="exp-copy">まとめてコピー</button></div>
{_compare(compare)}
<h2>手を付けなくてよいこと</h2>
{_healthy(healthy)}
{''.join(_card(100 + i, d, times, actions=False) for i, d in enumerate(ignored))}
</main><script>{JS}</script></body></html>"""


# ---- 複数ページの画面（ローカルサーバー用）。1枚のレポート（render_report）は、そのまま残す ----

APP_CSS = """
header.top{background:var(--card);border-bottom:1px solid var(--line)}
.bar{max-width:980px;margin:0 auto;padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;color:var(--ink);text-decoration:none;font-size:1.1rem}.site{color:var(--sub);font-size:.9rem}
nav.tabs{display:flex;gap:4px;flex-wrap:wrap;margin-left:auto}
nav.tabs a{color:var(--sub);text-decoration:none;padding:6px 12px;border-radius:8px;font-size:.92rem}
nav.tabs a:hover{color:var(--ink)}nav.tabs a[aria-current=page]{background:var(--accent);color:#fff}
.badge{display:inline-block;min-width:1.3em;margin-left:6px;padding:0 6px;border-radius:99px;background:var(--ok);color:#fff;font-size:.75rem;text-align:center}.badge:empty{display:none}
main.wide{max-width:980px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.chart h3{margin:0 0 2px;font-size:1rem}.chart p.sub{margin:0 0 8px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.cta{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.tiles+.cta{margin-top:12px}
.basis{color:var(--sub);font-size:.9rem;margin:6px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.grid2 table{font-size:.92rem}
.grid2 th:nth-child(2),.grid2 td:nth-child(2){white-space:nowrap}
a.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;border-radius:8px;padding:8px 16px}
"""

NAV = [("dashboard", "ダッシュボード"), ("trace", "調べた順番"), ("actions", "次にやること"), ("changes", "直したあとの変化")]
BADGE_JS = ("(function(){var n=document.getElementById('nav-n');if(!n)return;try{var c=0,p='ashiato:'+RID+':';"
            "for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);if(k.indexOf(p)===0&&localStorage.getItem(k)==='approve')c++}"
            "n.textContent=c||''}catch(e){}})();")


def make_view(brief, drafts, trace, cmp=None, agg=None, agg_after=None):
    """画面に出すものを、ひとまとめにする（メモリ上だけ）。rid は、下書きが変わったら変わる（承認の印を、前の結果と混ぜない）。"""
    rid = hashlib.sha1(json.dumps(drafts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
    return {"brief": brief, "drafts": drafts, "trace": trace, "cmp": cmp, "agg": agg, "agg_after": agg_after, "rid": rid}


def _layout(view, active, body, scripts=""):
    tabs = ""
    for key, text in NAV:
        cur = ' aria-current="page"' if key == active else ""
        badge = '<span class="badge" id="nav-n"></span>' if key == "actions" else ""
        tabs += f'<a href="/{key}"{cur}>{text}{badge}</a>'
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>足跡 {escape(view["brief"]["site_name"])}</title><style>{CSS}{APP_CSS}</style></head><body>'
            f'<header class="top"><div class="bar"><a class="brand" href="/">足跡</a><span class="site">{escape(view["brief"]["site_name"])}</span>'
            f'<nav class="tabs">{tabs}<a href="/">新しく調べる</a></nav></div></header><main class="wide">{body}</main>'
            f'<script>var RID={json.dumps(view["rid"])};{BADGE_JS}</script>{scripts}</body></html>')


def _acts(drafts):
    return sorted([d for d in drafts if d["kind"] not in ("leave_alone", "ignore")], key=lambda d: PRIORITY_ORDER[d["priority"]])


def _bot_rows(brief):
    tot = {}
    for page in brief["pages"].values():
        for bot, counts in page["ai_by_bot"].items():
            ok = sum(n for st, n in counts.items() if st[0] in "23")
            bad = sum(n for st, n in counts.items() if st[0] in "45")
            a, b = tot.get(bot, (0, 0))
            tot[bot] = (a + ok, b + bad)
    return sorted(((k, a, b) for k, (a, b) in tot.items()), key=lambda r: -(r[1] + r[2]))[:8]


def _chart_card(title, note, svg):
    return f'<div class="chart"><h3>{escape(title)}</h3><p class="sub">{escape(note)}</p>{svg}</div>'


def _demand(brief, limit=6):
    """どんなページが求められているか。AIが探したのに無かったページと、AIがよく読んでいるページ。ブリーフの事実だけから作る（判断はしない）。"""
    sig = brief.get("signals", {})
    redirects = {r["from"]: r["to"] for r in sig.get("redirect_candidates", [])}
    missing = {}
    for e in sig.get("ai_errors", []):
        if e["status"] == 404 and not e["in_site"]:
            m = missing.setdefault(e["path"], {"count": 0, "bots": set()})
            m["count"] += e["count"]
            m["bots"].update(e["bots"])
    lost = sorted(((path, m["count"], sorted(m["bots"])) for path, m in missing.items()), key=lambda r: -r[1])[:limit]
    kinds = {name: b.get("kind") for name, b in brief.get("bots", {}).items()}
    assistant = {}  # 探した回数のうち、お客様の質問に答えるために、その場で取りに来たAIの分
    for path, _n, _bots in lost:
        by_bot = brief["pages"].get(path, {}).get("ai_by_bot", {})
        counts = {bot: sum(n for st, n in c.items() if st == "404") for bot, c in by_bot.items() if kinds.get(bot) == "ai_assistant"}
        assistant[path] = {bot: n for bot, n in counts.items() if n}
    read = sorted(((path, sum(p["ai"].get(st, 0) for st in p["ai"] if st[0] in "23"), p["ai_answer_visitors"])
                   for path, p in brief["pages"].items()), key=lambda r: -r[1])
    read = [r for r in read if r[1] > 0][:limit]
    return lost, read, redirects, assistant


def _demand_panel(brief):
    lost, read, redirects, assistant = _demand(brief)
    if not lost and not read:
        return ""
    def lost_row(path, n, bots):
        hint = f'<span class="st st3">転送で足りる（{escape(redirects[path])}）</span>' if path in redirects else '<span class="st st0">新しく作る候補</span>'
        who = assistant.get(path)
        by = (f'<div class="ev">お客様の質問に答えるために来たAI（{escape("、".join(who))}）: {sum(who.values()):,}回</div>' if who else "")
        return f"<tr><td>{escape(path)}{by}</td><td>{n:,}</td><td>{hint}</td></tr>"
    left = ("<div class=\"chart\"><h3>AIが探したのに、無かったページ</h3><p class=\"sub\">AIが取りに来て、見つからなかったアドレスです。AIが推測したものか、古いリンクの名残かは、記録だけでは区別できません。回数が多いほど、求められている目安です。お客様の質問に答えるために来たAIは、実際にお客様が聞いた結果なので、より強い手がかりです。</p>"
            "<table><tr><th>アドレス</th><th>探した回数</th><th>見立て</th></tr>" + "".join(lost_row(*r) for r in lost) + "</table></div>") if lost else ""
    right = ("<div class=\"chart\"><h3>AIがよく読んでいるページ</h3><p class=\"sub\">いま求められている話題の目安です。ここに近い話題が、次のページの手がかりになります。</p>"
             "<table><tr><th>ページ</th><th>AIが読めた回数</th><th>AIの回答から来た人（回）</th></tr>"
             + "".join(f"<tr><td>{escape(path)}</td><td>{n:,}</td><td>{v:,}</td></tr>" for path, n, v in read) + "</table></div>") if read else ""
    return ('<h2>どんなページが求められているか</h2><div class="grid2">' + left + right + '</div>'
            '<p class="sub">AIが取りに来た回数からの目安です。AIが回答に使ったかどうかまでは、アクセスの記録からは分かりません。</p>')


def page_dashboard(view):
    brief, agg = view["brief"], view["agg"]
    site_only = brief.get("mode") == "site_only"
    p = brief["period"] or {"from": "", "to": ""}
    sub = ("サイトの公開ページをもとにしています（アクセスの記録は使っていません）。" if site_only
           else escape(p["from"]) + " 〜 " + escape(p["to"]) + " のアクセスをもとにしています。") + "承認するまで、サイトには何も反映されません。"
    note = ('<p class="sub">下書きはClaudeが書きました。公開する前に、必ず内容を確認してください。</p>'
            if any(d.get("source") == "claude" for d in view["drafts"]) else "")
    tiles = "".join(f'<div class="tile {c}"><b>{n:,}</b><span>{escape(t)}</span></div>' for t, n, c in (_site_tiles(brief) if site_only else _tiles(brief)))
    charts_html = ""
    if not site_only and agg and agg.get("daily"):
        series = charts.day_series(agg["daily"], agg["period"]["from"], agg["period"]["to"])
        charts_html += _chart_card("日ごとの、AIの動き", "AIがページを読みに来た回数を、1日ごとに数えました。緑は読めた回数、橙は読めなかった回数です。",
                                   charts.stacked_days(series, "日ごとのAIの読み取り回数（読めた・読めなかった）"))
        bots = _bot_rows(brief)
        if bots:
            charts_html += _chart_card("どのAIが来ているか", "AIの名前ごとの回数です（本物と確かめられたものだけ）。",
                                       charts.hbars(bots, "AIの名前ごとの読み取り回数"))
        charts_html += _chart_card("AIの回答から来た人（1日ごと）", "AIの回答を見て、サイトに来た人のアクセスの回数です。人数ではなく、回数です。",
                                   charts.line_days(series, "answer_visitors", "AIの回答から来た人のアクセス回数（日ごと）"))
    if site_only and brief.get("site_pages"):
        rows = [(pg["path"], pg["words"], 0) if pg["words"] >= THIN_WORDS else (pg["path"], 0, pg["words"])
                for pg in sorted(brief["site_pages"], key=lambda x: -x["words"])[:12]]
        charts_html += _chart_card("ページごとの、本文の長さ", f"読み取れた語数です。橙は、短いページ（{THIN_WORDS}語未満）です。日本語は、文字数の半分も見て数えています。",
                                   charts.hbars(rows, "ページごとの本文の語数。橙は短いページ"))
    n = len(_acts(view["drafts"]))
    cta = (f'<div class="card cta"><div><b>次にやること（{n}件）</b><div class="sub">Claudeが、根拠つきの下書きを用意しました。</div></div>'
           f'<a class="btn" href="/actions">見る</a></div>')
    demand = "" if site_only else _demand_panel(brief)
    body = (f'<h1>{escape(brief["site_name"])} のAI足跡</h1><div class="sub">{sub}</div>{note}<div class="tiles">{tiles}</div>{cta}{charts_html}{demand}'
            f'{_pages(page_rows(brief)) if brief.get("site_pages") and not site_only else ""}{_ai_answers(brief.get("ai_answers"))}')
    return _layout(view, "dashboard", body)


def page_trace(view):
    times = view["brief"].get("evidence_times", {})
    body = _trace(view["trace"], times) + '<div class="card cta"><span>調べた結果から、次にやることを用意しました。</span><a class="btn" href="/actions">次にやること</a></div>'
    return _layout(view, "trace", body)


def page_actions(view):
    drafts, times = view["drafts"], view["brief"].get("evidence_times", {})
    acts = _acts(drafts)
    healthy = [d for d in drafts if d["kind"] == "leave_alone"]
    ignored = [d for d in drafts if d["kind"] == "ignore"]
    body = (f'<h1>次にやること（{len(acts)}件）</h1><p class="sub">承認・修正・却下は、この画面の中の印だけです。サイトには何も書き込みません。</p>'
            + (''.join(_card(i, d, times, brief=view["brief"]) for i, d in enumerate(acts)) or '<p class="sub">今回は、対応が必要なものはありません。</p>')
            + '<div class="exp"><h2>承認した下書き（<span id="exp-n">0</span>件）</h2>'
              '<p class="sub">承認したものだけが、ここに集まります。コピーして、ご自分でサイトに反映してください。足跡は、サイトには何も書き込みません。</p>'
              '<textarea id="exp-text" readonly placeholder="「承認」を押すと、ここに下書きが入ります"></textarea><br><button id="exp-copy">まとめてコピー</button></div>'
            + '<h2>手を付けなくてよいこと</h2>' + _healthy(healthy)
            + ''.join(_card(100 + i, d, times, actions=False) for i, d in enumerate(ignored)))
    return _layout(view, "actions", body, scripts=f"<script>{JS}</script>")


def _ai_counts(agg, paths=None):
    """AIの要求の、(読めた回数, 読めなかった回数)。paths を渡すと、そのページ宛だけ。"""
    ok = bad = 0
    for path, p in agg["pages"].items():
        if paths is not None and path not in paths:
            continue
        for st, n in p["ai"].items():
            if st[0] in "23":
                ok += n
            elif st[0] in "45":
                bad += n
    return ok, bad


def _fix_summary(view):
    """直す前と直したあとの、AIの要求の合計と、読めた割合。提案したページ宛の割合。事実の計算だけ。"""
    cmp, b, a = view["cmp"], view["agg"], view["agg_after"]
    (bo, bb), (ao, ab) = _ai_counts(b), _ai_counts(a)
    db, da = cmp["days"]["before"], cmp["days"]["after"]
    targets = [d["target"] for d in view["drafts"] if d["kind"] in ("new_page", "redirect", "rewrite_page")
               and d.get("target") and d.get("demand_basis") != "reading"]
    pages = [t for t in dict.fromkeys(targets) if sum(_ai_counts(b, {t})) + sum(_ai_counts(a, {t}))]
    (bpo, bpb), (apo, apb) = _ai_counts(b, set(pages)), _ai_counts(a, set(pages))
    pct = lambda x, y: round(100 * x / y, 1) if y else 0  # noqa: E731
    def segs(po, pb, o, b_):
        """提案したページ宛（読めた・読めなかった）と、その他のページ宛（読めた・読めなかった）の割合（%）。0の区分は出さない。"""
        total = o + b_
        parts = [("提案したページ宛（読めなかった）", pb, "var(--warn)"), ("提案したページ宛（読めた）", po, "var(--accent)"),
                 ("その他のページ宛（読めた）", o - po, "var(--ok)"), ("その他のページ宛（読めなかった）", b_ - pb, "var(--sub)")]
        return [(name, pct(n, total), color) for name, n, color in parts if n]
    return {"total_before": round((bo + bb) / db, 1), "total_after": round((ao + ab) / da, 1),
            "rate_before": pct(bo, bo + bb), "rate_after": pct(ao, ao + ab),
            "pages": pages, "share_before": pct(bpo + bpb, bo + bb), "share_after": pct(apo + apb, ao + ab),
            "proposal_read_before": pct(bpo, bpo + bpb), "proposal_read_after": pct(apo, apo + apb),
            "segs_before": segs(bpo, bpb, bo, bb), "segs_after": segs(apo, apb, ao, ab)}


def page_changes(view, after_block=""):
    brief, cmp = view["brief"], view["cmp"]
    head = '<h1>直したあとの変化</h1>'
    if brief.get("mode") == "site_only":
        return _layout(view, "changes", head + '<p class="sub">アクセスの記録があるときに、直す前と直したあとを比べられます。いまは、サイトの公開ページだけを調べています。</p>')
    if not cmp:
        return _layout(view, "changes", head + '<p class="sub">ページを直したあとのアクセス記録を入れると、直す前と、グラフで比べられます。</p>' + after_block)
    agg, after = view["agg"], view["agg_after"]
    out = head + f'<p class="sub">直す前（{cmp["days"]["before"]}日分）と、直したあと（{cmp["days"]["after"]}日分）を、1日あたりで比べています。</p>'
    if agg and after and agg.get("daily") is not None and after.get("daily") is not None:
        b = charts.day_series(agg["daily"], agg["period"]["from"], agg["period"]["to"])
        a = charts.day_series(after["daily"], after["period"]["from"], after["period"]["to"])
        out += _chart_card("日ごとの、AIの動き（直す前から、直したあとまで）", "点線のところで、ページを直しました。緑は読めた回数、橙は読めなかった回数です。",
                           charts.stacked_days(b + a, "日ごとのAIの読み取り回数。直す前と直したあと", split_after=len(b) - 1, split_text="この間に直した"))
    if agg and after:
        f = _fix_summary(view)
        out += ('<div class="grid3">'
                + f'<div class="chart">{charts.before_after("AIの要求の合計（回、1日）", f["total_before"], f["total_after"])}</div>'
                + f'<div class="chart">{charts.before_after("AIが読めた割合（%）", f["rate_before"], f["rate_after"])}</div></div>'
                + '<p class="sub">AIが来る回数そのものは、ほぼ変わっていません。変わったのは、読めた割合です。</p>')
        if f["pages"]:
            names = "、".join(escape(p) for p in f["pages"])
            out += _chart_card("提案したページ宛の要求", f"AIの提案で作った・直したページ（{names}）宛の要求が、AIの要求全体に占める割合です。",
                               charts.share_bars([("直す前", f["segs_before"]), ("直したあと", f["segs_after"])], "提案したページ宛の要求の割合。直す前と直したあと"))
            out += (f'<p class="sub">直す前は、AIの要求の{f["share_before"]:g}%が、提案したページ宛で、そのうち読めたのは{f["proposal_read_before"]:g}%でした。'
                    f'直したあとは、{f["share_after"]:g}%が、同じページ宛で、そのうち読めたのは{f["proposal_read_after"]:g}%でした。</p>')
    out += ('<div class="grid3">'
            + f'<div class="chart">{charts.before_after("AIが読めなかった回数（1日）", cmp["failed_per_day"]["before"], cmp["failed_per_day"]["after"])}</div>'
            + f'<div class="chart">{charts.before_after("AIが読めた回数（1日）", cmp["ok_per_day"]["before"], cmp["ok_per_day"]["after"])}</div>'
            + f'<div class="chart">{charts.before_after("AIの回答から来た人（回、1日）", cmp["ai_answer_visitors_per_day"]["before"], cmp["ai_answer_visitors_per_day"]["after"])}</div></div>')
    table = _compare(cmp).replace("<h2>直したあとの変化</h2>", "<h2>数字で見る</h2>")
    table = re.sub(r'<p class="sub">直す前（.*?</p>', "", table, count=1)  # 同じ説明が、ページの上にある
    out += table
    return _layout(view, "changes", out)


PAGES = {"dashboard": page_dashboard, "trace": page_trace, "actions": page_actions, "changes": page_changes}
