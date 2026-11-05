#!/usr/bin/env python3
"""ログ1ファイルとサイト情報から、ブリーフ・見本の下書き・レポートを作る（Claude も API も使わない）。

使い方: python3 scripts/build_report.py <ログ> <サイトの情報のフォルダ> <サイト名> <出力フォルダ>
出力: brief.json, drafts.json（見本）, report.html
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato import brief as brief_mod, drafts as drafts_mod, logs, report, sample  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402


def build(log_path, site_dir, site_name, out_dir):
    b = brief_mod.build_brief(aggregate(logs.parse(log_path)), brief_mod.load_site(site_dir), site_name)
    d = sample.sample_drafts(b)
    out = Path(out_dir)
    drafts_mod.save(d, brief_mod.known_ids(b), out)
    (out / "brief.json").write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "report.html").write_text(report.render_report(b, d), encoding="utf-8")
    return b, d


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    build(*sys.argv[1:])
