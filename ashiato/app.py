"""ブラウザからログを入れて、レポートを返す小さなローカルサーバー（標準ライブラリのみ）。

127.0.0.1 だけで待ち受ける。アップロードされたログは、メモリ上で解析するだけで、ディスクに書かない。
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import advisor, brief as brief_mod, llm, logs, report, sample
from .aggregate import aggregate
from .compare import compare
from .trace import build_trace

MAX_BYTES = 50 * 1024 * 1024

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
 fetch('/analyze',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f}).then(function(r){return r.text()})
 .then(function(h){document.open();document.write(h);document.close()}).catch(function(){busy.textContent='うまく読み込めませんでした。ファイルを確かめて、もう一度お試しください。'})}
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
 fetch('/compare',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f}).then(function(r){return r.text().then(function(t){return [r.ok,t]})})
 .then(function(a){if(a[0]){document.open();document.write(a[1]);document.close()}else{z.querySelector('b').textContent=a[1]}})
 .catch(function(){z.querySelector('b').textContent='うまく読み込めませんでした。もう一度お試しください。'})}
i.addEventListener('change',function(){go(i.files[0])});
['dragenter','dragover'].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.add('over')})});
['dragleave','drop'].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.remove('over')})});
z.addEventListener('drop',function(v){go(v.dataTransfer.files[0])});})();
</script>"""


LIVE_BUSY = "AIが何回、どのページを読みに来たか数えて、Claudeが原因を考えています。1〜2分かかります…"


def upload_page(cfg):
    return UPLOAD_PAGE.replace("AIが何回、どのページを読みに来たか数えています…", LIVE_BUSY) if cfg.live else UPLOAD_PAGE


class Config:
    """サーバーを起動するときに決める物。ログそのものは持たない（直前に調べた集計だけを、メモリに持つ）。"""

    def __init__(self, site_dir, site_name, response_path=None, after=None, live=False, client=None):
        self.site_dir, self.site_name = Path(site_dir), site_name
        self.live = live  # True: 入れたログごとに、Claude API で下書きを作る（料金がかかる）
        self.client = client  # テスト用に差し替える。None なら anthropic.Anthropic()
        self.response_text = Path(response_path).read_text(encoding="utf-8") if response_path else None
        self.after = after  # (ログのパス, サイト情報のフォルダ) または None（起動時に固定の比較先を渡す、デモ用）
        self.last = None  # 直前にアップロードされたログの (集計, ブリーフ, 下書き)。ディスクには書かない


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
    cmp = None
    if cfg.after:
        after_path = Path(cfg.after[0])
        cmp = compare(agg, aggregate(logs.parse_text(after_path.read_text(encoding="utf-8"), after_path.name)))
    html = report.render_report(brief, drafts, cmp, build_trace(brief, drafts))
    return html if cmp else html.replace("</body>", AFTER_BLOCK + "</body>", 1)


def compare_after(text, filename, cfg):
    """直前に調べたログ（直す前）と、いま入れたログ（直したあと）を比べたレポートのHTMLを作る。"""
    if cfg.last is None:
        raise LookupError("先に、直す前のアクセス記録を入れてください")
    rows = logs.parse_text(text, filename)
    if not rows:
        raise ValueError("読めるアクセス記録がありませんでした")
    agg, brief, drafts = cfg.last
    cmp = compare(agg, aggregate(rows))
    return report.render_report(brief, drafts, cmp, build_trace(brief, drafts))


def make_handler(cfg):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(200, upload_page(cfg)) if self.path in ("/", "/index.html") else self._send(404, "ページがありません")

        def do_POST(self):
            if self.path not in ("/analyze", "/compare"):
                return self._send(404, "ページがありません")
            size = int(self.headers.get("Content-Length", 0))
            if size > MAX_BYTES:
                return self._send(413, "ファイルが大きすぎます（50MBまで）")
            from urllib.parse import unquote
            name = Path(unquote(self.headers.get("X-Filename", "upload.txt"))).name
            try:
                run = analyze if self.path == "/analyze" else compare_after
                html = run(self.rfile.read(size).decode("utf-8"), name, cfg)
            except LookupError as e:
                return self._send(409, str(e))
            except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
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
