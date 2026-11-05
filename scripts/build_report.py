#!/usr/bin/env python3
"""ログ1ファイルとサイト情報から、ブリーフ・下書き・レポートを作る（このスクリプトは Claude も API も呼ばない）。

使い方: python3 scripts/build_report.py <ログ> <サイトの情報のフォルダ> <サイト名> <出力フォルダ>
          [--response Claudeの返答のJSON] [--after 直したあとのログ <サイトの情報のフォルダ>]
  --response なし: 見本の下書き（決まった規則で作る。画面に「見本」と出る）
  --response あり: Claude の返答を検証して使う。検証に通らない下書きは使わない
  --after あり: 直したあとのログと並べて「直したあとの変化」を出す
出力: brief.json, drafts.json, report.html
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato import advisor, brief as brief_mod, drafts as drafts_mod, logs, report, sample  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402
from ashiato.compare import compare  # noqa: E402
from ashiato.trace import build_trace  # noqa: E402


def build(log_path, site_dir, site_name, out_dir, response=None, after=None):
    agg = aggregate(logs.parse(log_path))
    b = brief_mod.build_brief(agg, brief_mod.load_site(site_dir), site_name)
    if response:
        d, rejected = advisor.accept(Path(response).read_text(encoding="utf-8"), b)
        for r in rejected:
            print(f"使わない下書き: {r['draft'].get('title', '?')} — {'; '.join(r['problems'])}", file=sys.stderr)
    else:
        d = sample.sample_drafts(b)
    cmp = compare(agg, aggregate(logs.parse(after[0]))) if after else None
    out = Path(out_dir)
    drafts_mod.save(d, brief_mod.known_ids(b), out)
    (out / "brief.json").write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "report.html").write_text(report.render_report(b, d, cmp, build_trace(b, d)), encoding="utf-8")
    return b, d


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"), ap.add_argument("site"), ap.add_argument("name"), ap.add_argument("out")
    ap.add_argument("--response")
    ap.add_argument("--after", nargs=2, metavar=("LOG", "SITE"))
    a = ap.parse_args()
    build(a.log, a.site, a.name, a.out, a.response, a.after)
