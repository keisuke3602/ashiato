"""Cloudflare Logpush（NDJSON）と nginx/Apache の combined 形式（行頭にドメイン名が付く形も）を、同じ形の行に揃える。

行: id, ts(UTC ISO), path, query, status, bytes, ua, referer, category
  id        "<ファイル名>:<行番号>"。助言の根拠として、画面とレポートに出す。
  category  Logpush の VerifiedBotCategory。nginx 形式には無いので None（検証の可否は不明）。
IP・Cookie は読まない・保持しない。
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

NGINX = re.compile(r'^(?:\S+ )?\S+ \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<uri>\S+) [^"]*" '
                   r'(?P<status>\d{3}) (?P<bytes>\d+|-) "(?P<ref>[^"]*)" "(?P<ua>[^"]*)"')


def _row(row_id, ts, uri, status, size, ua, referer, category):
    parts = urlsplit(uri)
    return {"id": row_id, "ts": ts, "path": parts.path or "/", "query": parts.query, "status": int(status),
            "bytes": int(size), "ua": ua, "referer": referer, "category": category}


def parse_logpush(path):
    path = Path(path)
    yield from _logpush_lines(path.name, path.read_text(encoding="utf-8"))


def _logpush_lines(name, text):
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        yield _row(f"{name}:{n}", r["EdgeStartTimestamp"], r["ClientRequestURI"], r["EdgeResponseStatus"],
                   r.get("EdgeResponseBytes", 0), r.get("ClientRequestUserAgent", ""),
                   r.get("ClientRequestReferer", ""), r.get("VerifiedBotCategory", ""))


def parse_nginx(path):
    path = Path(path)
    yield from _nginx_lines(path.name, path.read_text(encoding="utf-8"))


def _nginx_lines(name, text):
    for n, line in enumerate(text.splitlines(), 1):
        m = NGINX.match(line)
        if not m:
            continue
        t = datetime.strptime(m["time"], "%d/%b/%Y:%H:%M:%S %z").astimezone(timezone.utc)
        ref = "" if m["ref"] == "-" else m["ref"]
        size = 0 if m["bytes"] == "-" else m["bytes"]
        yield _row(f"{name}:{n}", t.strftime("%Y-%m-%dT%H:%M:%SZ"), m["uri"], m["status"], size,
                   m["ua"], ref, None)


def parse(path):
    """拡張子で形式を選ぶ。.ndjson は Logpush、それ以外は combined 形式。"""
    return list(parse_logpush(path) if str(path).endswith(".ndjson") else parse_nginx(path))


def parse_text(text, name):
    """ファイルを作らずに、文字列から読む（アップロードされたログを、ディスクに書かないため）。"""
    lines = _logpush_lines if name.endswith(".ndjson") else _nginx_lines
    return list(lines(name, text))
