#!/usr/bin/env python3
"""ブラウザでログを入れて、レポートを見る（このパソコンの中だけで動く）。

使い方: python3 scripts/serve.py <サイト情報のフォルダ> <サイト名> [--response Claudeの返答のJSON]
          [--after 直したあとのログ] [--port 8765]
--live: 入れたログごとに Claude API で下書きを作る（キーは環境変数 ANTHROPIC_API_KEY。料金がかかる）。
--response なしなら見本の下書き、ありなら Claude の返答のうち、入れたログに当てはまるものを使う。
前後の比較: 画面に、まず直す前のログを入れ、出てきたレポートの下の欄に、直したあとのログを入れると比較が出る。
  --after を付けると、比較先がこのファイルに固定され、最初から比較が出る（デモの撮り直し用）。
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato.app import Config, serve  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site"), ap.add_argument("name")
    ap.add_argument("--response"), ap.add_argument("--after"), ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--live", action="store_true", help="入れたログごとに Claude API で下書きを作る（料金がかかる）")
    a = ap.parse_args()
    if a.live and a.response:
        ap.error("--live と --response は一緒に使えません（--live は、入れたログから Claude に下書きを作らせます）")
    if a.live and not os.environ.get("ANTHROPIC_API_KEY"):
        ap.error("--live には、環境変数 ANTHROPIC_API_KEY が必要です")
    serve(Config(a.site, a.name, a.response, (a.after, None) if a.after else None, live=a.live), a.port)
