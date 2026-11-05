"""ブラウザからログを入れて、レポートを返す小さなローカルサーバー（標準ライブラリのみ）。

127.0.0.1 だけで待ち受ける。アップロードされたログは、メモリ上で解析するだけで、ディスクに書かない。
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import advisor, brief as brief_mod, logs, report, sample
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
#drop{border:2px dashed var(--line);border-radius:16px;background:var(--card);padding:48px 16px;text-align:center;cursor:pointer}
#drop.over{border-color:var(--accent)}#drop b{display:block;font-size:1.15rem;margin-bottom:6px}
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


class Config:
    """サーバーを起動するときに決める物。ログそのものは持たない。"""

    def __init__(self, site_dir, site_name, response_path=None, after=None):
        self.site_dir, self.site_name = Path(site_dir), site_name
        self.response_text = Path(response_path).read_text(encoding="utf-8") if response_path else None
        self.after = after  # (ログのパス, サイト情報のフォルダ) または None


def analyze(text, filename, cfg):
    """アップロードされたログの中身から、レポートのHTMLを作る。"""
    rows = logs.parse_text(text, filename)
    if not rows:
        raise ValueError("読めるアクセス記録がありませんでした")
    agg = aggregate(rows)
    brief = brief_mod.build_brief(agg, brief_mod.load_site(cfg.site_dir), cfg.site_name)
    if cfg.response_text:
        drafts, _rejected = advisor.accept(cfg.response_text, brief)  # この記録に当てはまらない下書きは使わない
    else:
        drafts = sample.sample_drafts(brief)
    cmp = None
    if cfg.after:
        after_path = Path(cfg.after[0])
        cmp = compare(agg, aggregate(logs.parse_text(after_path.read_text(encoding="utf-8"), after_path.name)))
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
            self._send(200, UPLOAD_PAGE) if self.path in ("/", "/index.html") else self._send(404, "ページがありません")

        def do_POST(self):
            if self.path != "/analyze":
                return self._send(404, "ページがありません")
            size = int(self.headers.get("Content-Length", 0))
            if size > MAX_BYTES:
                return self._send(413, "ファイルが大きすぎます（50MBまで）")
            from urllib.parse import unquote
            name = Path(unquote(self.headers.get("X-Filename", "upload.txt"))).name
            try:
                html = analyze(self.rfile.read(size).decode("utf-8"), name, cfg)
            except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
                return self._send(400, "読み込めませんでした。Cloudflareのログ（.ndjson）か、nginx・Apacheのアクセスログを選んでください。")
            self._send(200, html)

        def log_message(self, *args):  # 受け取った内容を、端末にも残さない
            pass
    return Handler


def serve(cfg, port=8765):
    server = HTTPServer(("127.0.0.1", port), make_handler(cfg))
    print(f"足跡: http://127.0.0.1:{port}/ を開いてください（止めるときは Ctrl+C）")
    server.serve_forever()
