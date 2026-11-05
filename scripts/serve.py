#!/usr/bin/env python3
"""ブラウザでログを入れて、レポートを見る（このパソコンの中だけで動く）。

使い方: python3 scripts/serve.py <サイト情報のフォルダ> <サイト名> [--response Claudeの返答のJSON]
          [--after 直したあとのログ] [--port 8765]
--response なしなら見本の下書き、ありなら Claude の返答のうち、入れたログに当てはまるものを使う。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato.app import Config, serve  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site"), ap.add_argument("name")
    ap.add_argument("--response"), ap.add_argument("--after"), ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    serve(Config(a.site, a.name, a.response, (a.after, None) if a.after else None), a.port)
