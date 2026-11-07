"""ブラウザからログを入れて、レポートを返す小さなローカルサーバー（標準ライブラリのみ）。

127.0.0.1 だけで待ち受ける。アップロードされたログは、メモリ上で解析するだけで、ディスクに書かない。
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from urllib.parse import urlsplit

from . import advisor, ask_ai, brief as brief_mod, llm, logs, report, sample, sitecheck
from .aggregate import aggregate
from .compare import compare
from .trace import build_trace

MAX_BYTES = 50 * 1024 * 1024


def request_allowed(host, origin, port):
    """自分のページからの要求だけを通す。Host が違えば（DNSの付け替えなど）、Origin が自分のページでなければ（別のサイトからの送信）断る。"""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if (host or "") not in hosts:
        return False
    return origin is None or origin in {f"http://{h}" for h in hosts}

UPLOAD_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>足跡</title><style>
:root{--bg:#faf8f5;--card:#fff;--ink:#2b2622;--sub:#6f655c;--line:#d9d0c5;--accent:#b4532a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#1d1a17;--card:#27231f;--ink:#f2ece4;--sub:#b3a99e;--line:#4a423b;--accent:#e38b5f}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:640px;margin:0 auto;padding:56px 16px}h1{font-size:1.8rem;margin:0}
.lead{color:var(--sub);margin:4px 0 28px}
#drop{display:block;box-sizing:border-box;border:2px dashed var(--line);border-radius:16px;background:var(--card);padding:48px 16px;text-align:center;cursor:pointer}
#drop.over{border-color:var(--accent)}#drop b{display:block;font-size:1.15rem;margin-bottom:6px}
#drop .lead{display:block;margin:0}
#busy{display:none;text-align:center;padding:48px 0;font-size:1.1rem}
details{margin-top:28px;color:var(--sub);font-size:.92rem}
</style></head><body><main>
<h1>足跡</h1><p class="lead">AIに見つけてもらうための道しるべ</p>
<label id="drop"><input id="file" type="file" hidden><b>サイトのアクセス記録のファイルを、ここに落としてください</b><span class="lead">またはクリックして選びます。ファイルはこのパソコンの中で調べるだけで、外には送りません。</span></label>
<div id="busy">AIが何回、どのページを読みに来たか数えています…</div>
<details><summary>記録の取り方がわからないとき</summary><p>お使いのサーバー会社、またはCloudflareなどの配信サービスに、「アクセスログをください」と頼むのが近道です。
対応している形式は、Cloudflareのログ（.ndjson）と、nginx・Apacheのアクセスログ（.txt / .log）です。</p></details>
</main><script>
var drop=document.getElementById('drop'),input=document.getElementById('file'),busy=document.getElementById('busy');
function send(f){if(!f)return;drop.style.display='none';busy.style.display='block';
 fetch('/analyze',{method:'POST',headers:{'X-Ashiato':'1','X-Filename':encodeURIComponent(f.name)},body:f}).then(function(r){return r.text().then(function(t){return [r.ok,t]})})
 .then(function(a){if(a[0]){location.href='/dashboard'}else{busy.textContent='うまく読み込めませんでした。ファイルを確かめて、もう一度お試しください。'}}).catch(function(){busy.textContent='うまく読み込めませんでした。ファイルを確かめて、もう一度お試しください。'})}
input.addEventListener('change',function(){send(input.files[0])});
['dragenter','dragover'].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.add('over')})});
['dragleave','drop'].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.remove('over')})});
drop.addEventListener('drop',function(ev){send(ev.dataTransfer.files[0])});
</script></body></html>"""


AFTER_BLOCK = """<style>
#after{display:block;box-sizing:border-box;max-width:880px;margin:32px auto;border:2px dashed var(--line);border-radius:16px;
background:var(--card);padding:28px 16px;text-align:center;cursor:pointer;color:var(--ink)}
#after.over{border-color:var(--accent)}#after b{display:block;margin-bottom:4px}#after span{display:block;color:var(--sub);font-size:.92rem}
</style>
<label id="after"><input id="afterfile" type="file" hidden><b>直したあとのアクセス記録を入れると、前後を比べられます</b>
<span>ページを直してしばらくたってから、新しい記録をここに落としてください。このパソコンの中で調べるだけで、外には送りません。</span></label>
<script>
(function(){var z=document.getElementById('after'),i=document.getElementById('afterfile');
function go(f){if(!f)return;z.querySelector('b').textContent='前後を比べています…';
 fetch('/compare',{method:'POST',headers:{'X-Ashiato':'1','X-Filename':encodeURIComponent(f.name)},body:f}).then(function(r){return r.text().then(function(t){return [r.ok,t]})})
 .then(function(a){if(a[0]){location.href='/changes'}else{z.querySelector('b').textContent=a[1]}})
 .catch(function(){z.querySelector('b').textContent='うまく読み込めませんでした。もう一度お試しください。'})}
i.addEventListener('change',function(){go(i.files[0])});
['dragenter','dragover'].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.add('over')})});
['dragleave','drop'].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.remove('over')})});
z.addEventListener('drop',function(v){go(v.dataTransfer.files[0])});})();
</script>"""


LIVE_BUSY = "AIが何回、どのページを読みに来たか数えて、Claudeが原因を考えています。1〜2分かかります…"


SITE_BLOCK = """<div id="siteform" style="margin-top:36px;padding-top:24px;border-top:1px solid var(--line)">
<b>アクセスの記録が取れない・わからない方へ</b>
<p class="lead" style="margin:4px 0 10px">サイトのアドレスを入れると、公開されているページから、AIに読まれやすい状態かを調べます（記録は要りません）。</p>
<input id="siteurl" type="text" placeholder="https://example.com" style="width:70%;box-sizing:border-box;font:inherit;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)">
<p style="margin:10px 0 4px"><label><input id="askai" type="checkbox"> AIの答えも確かめる（お客様が聞きそうな質問に、AIがどう答えるか。追加で数分かかります）</label></p>
<input id="biz" type="text" placeholder="事業の説明（例: 北陸の温泉地にある小さな旅館）" style="width:70%;box-sizing:border-box;font:inherit;padding:8px;margin-bottom:8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)"><br>
<button id="sitego" style="font:inherit;padding:8px 16px;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:8px;cursor:pointer">調べる</button>
<button id="sitedemo" style="font:inherit;padding:8px 16px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;cursor:pointer">デモ用の架空のサイトで試す</button>
</div><script>
(function(){var u=document.getElementById('siteurl'),busy=document.getElementById('busy');
function go(url){busy.textContent='サイトのページを読んで、Claudeが原因を考えています。数分かかります…';busy.style.display='block';document.getElementById('siteform').style.display='none';document.getElementById('drop').style.display='none';
 var body=JSON.stringify({url:url,ask_ai:document.getElementById('askai').checked,business:document.getElementById('biz').value});
 fetch('/site',{method:'POST',headers:{'X-Ashiato':'1'},body:body}).then(function(r){return r.text().then(function(t){return [r.ok,t]})})
 .then(function(a){if(a[0]){location.href='/dashboard'}else{busy.textContent=a[1]}}).catch(function(){busy.textContent='うまく読み込めませんでした。'})}
document.getElementById('sitego').addEventListener('click',function(){if(u.value.trim())go(u.value.trim())});
document.getElementById('sitedemo').addEventListener('click',function(){go('')});})();
</script>"""


def upload_page(cfg):
    if not cfg.live:
        return UPLOAD_PAGE
    return UPLOAD_PAGE.replace("AIが何回、どのページを読みに来たか数えています…", LIVE_BUSY).replace("</main>", SITE_BLOCK + "</main>", 1)


class Config:
    """サーバーを起動するときに決める物。ログそのものは持たない（直前に調べた集計だけを、メモリに持つ）。"""

    def __init__(self, site_dir, site_name, response_path=None, after=None, live=False, client=None):
        self.site_dir, self.site_name = Path(site_dir), site_name
        self.live = live  # True: 入れたログごとに、Claude API で下書きを作る（料金がかかる）
        self.client = client  # テスト用に差し替える。None なら anthropic.Anthropic()
        self.response_text = Path(response_path).read_text(encoding="utf-8") if response_path else None
        self.after = after  # (ログのパス, サイト情報のフォルダ) または None（起動時に固定の比較先を渡す、デモ用）
        self.last = None  # 直前にアップロードされたログの (集計, ブリーフ, 下書き)。ディスクには書かない
        self.view = None  # 画面に出すもの（複数ページ）。メモリ上だけ。report.make_view の結果


def analyze(text, filename, cfg):
    """アップロードされたログの中身から、レポートのHTMLを作る。"""
    rows = logs.parse_text(text, filename)
    if not rows:
        raise ValueError("読めるアクセス記録がありませんでした")
    agg = aggregate(rows)
    brief = brief_mod.build_brief(agg, brief_mod.load_site(cfg.site_dir), cfg.site_name)
    if cfg.live:
        _text, ok, _rejected, _in, _out = llm.advise(brief, cfg.client)  # 検証に通った下書きだけを使う
        drafts = ok
    elif cfg.response_text:
        drafts, _rejected = advisor.accept(cfg.response_text, brief)  # この記録に当てはまらない下書きは使わない
    else:
        drafts = sample.sample_drafts(brief)
    cfg.last = (agg, brief, drafts)
    cmp, agg_after = None, None
    if cfg.after:
        after_path = Path(cfg.after[0])
        agg_after = aggregate(logs.parse_text(after_path.read_text(encoding="utf-8"), after_path.name))
        cmp = compare(agg, agg_after)
    trace = build_trace(brief, drafts)
    cfg.view = report.make_view(brief, drafts, trace, cmp, agg, agg_after)
    html = report.render_report(brief, drafts, cmp, trace)
    return html if cmp else html.replace("</body>", AFTER_BLOCK + "</body>", 1)


def diagnose_site(body, cfg):
    """アクセスの記録が無いときの診断。body は、アドレスの文字列、または {"url","ask_ai","business"} の JSON。
    url が空なら、起動時に渡されたサイトの情報（デモ用の保存済み）を使う。ask_ai が真なら、AIの答えも確かめる。"""
    if not cfg.live:
        raise LookupError("サイトの診断には、起動時に --live（Claude API）が必要です")
    opts = json.loads(body) if body.lstrip().startswith("{") else {"url": body}
    url = str(opts.get("url", "")).strip()
    site = sitecheck.fetch_site(url) if url else brief_mod.load_site(cfg.site_dir)
    name = cfg.site_name if not url else url
    brief = brief_mod.build_site_only_brief(site, name)
    if opts.get("ask_ai"):
        client = cfg.client
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        domain = urlsplit(url if "://" in url else "https://" + url).netloc if url else ""
        brief["ai_answers"] = ask_ai.check_ai_answers(client, cfg.site_name, domain, str(opts.get("business", "")).strip())
    _text, drafts, _rejected, _in, _out = llm.advise(brief, cfg.client)
    cfg.last = None  # 前後の比較は、アクセスの記録があるときだけ
    trace = build_trace(brief, drafts)
    cfg.view = report.make_view(brief, drafts, trace)
    return report.render_report(brief, drafts, None, trace)


def compare_after(text, filename, cfg):
    """直前に調べたログ（直す前）と、いま入れたログ（直したあと）を比べたレポートのHTMLを作る。"""
    if cfg.last is None:
        raise LookupError("先に、直す前のアクセス記録を入れてください")
    rows = logs.parse_text(text, filename)
    if not rows:
        raise ValueError("読めるアクセス記録がありませんでした")
    agg, brief, drafts = cfg.last
    agg_after = aggregate(rows)
    cmp = compare(agg, agg_after)
    trace = build_trace(brief, drafts)
    cfg.view = report.make_view(brief, drafts, trace, cmp, agg, agg_after)
    return report.render_report(brief, drafts, cmp, trace)


def render_page(cfg, name):
    """複数ページの画面の1枚を作る。まだ何も調べていなければ None（入口に戻す）。"""
    if cfg.view is None or name not in report.PAGES:
        return None
    if name == "changes":
        return report.page_changes(cfg.view, AFTER_BLOCK)
    return report.PAGES[name](cfg.view)


def make_handler(cfg):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _guard(self, post=False):
            """自分のページ以外からの要求を断る。POST は、自分のページだけが付ける印（X-Ashiato）も要る。
            別のサイトからは、この印を付けた送信ができない（事前確認で止まる）。"""
            port = self.server.server_address[1]
            if not request_allowed(self.headers.get("Host"), self.headers.get("Origin"), port):
                self._send(403, "この要求は受け付けません")
                return False
            if post and self.headers.get("X-Ashiato") != "1":
                self._send(403, "この要求は受け付けません")
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            if self.path in ("/", "/index.html"):
                return self._send(200, upload_page(cfg))
            name = self.path.strip("/")
            if name in report.PAGES:
                html = render_page(cfg, name)
                if html is None:  # まだ何も調べていない
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self._send(200, html)
            self._send(404, "ページがありません")

        def do_POST(self):
            if not self._guard(post=True):
                return
            if self.path not in ("/analyze", "/compare", "/site"):
                return self._send(404, "ページがありません")
            try:
                size = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._send(400, "要求の形が正しくありません")
            if size < 0:
                return self._send(400, "要求の形が正しくありません")
            if size > MAX_BYTES:
                return self._send(413, "ファイルが大きすぎます（50MBまで）")
            from urllib.parse import unquote
            name = Path(unquote(self.headers.get("X-Filename", "upload.txt"))).name
            try:
                body = self.rfile.read(size).decode("utf-8")
                html = (diagnose_site(body, cfg) if self.path == "/site"
                        else (analyze if self.path == "/analyze" else compare_after)(body, name, cfg))
            except LookupError as e:
                return self._send(409, str(e))
            except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as e:
                if self.path == "/site" and isinstance(e, ValueError) and not isinstance(e, UnicodeDecodeError):
                    return self._send(400, str(e))
                return self._send(400, "読み込めませんでした。Cloudflareのログ（.ndjson）か、nginx・Apacheのアクセスログを選んでください。")
            except Exception as e:  # Claude API への接続・認証・応答の失敗（キーの中身は出さない）
                if not cfg.live:
                    raise
                return self._send(502, f"Claudeに接続できませんでした（{type(e).__name__}）。キーとネットワークを確かめて、もう一度お試しください。")
            self._send(200, html)

        def log_message(self, *args):  # 受け取った内容を、端末にも残さない
            pass
    return Handler


def serve(cfg, port=8765):
    server = HTTPServer(("127.0.0.1", port), make_handler(cfg))
    print(f"足跡: http://127.0.0.1:{port}/ を開いてください（止めるときは Ctrl+C）")
    server.serve_forever()
