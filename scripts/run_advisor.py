#!/usr/bin/env python3
"""ログから作ったブリーフを Claude API に渡して、下書きの返答を保存する。

使い方: python3 scripts/run_advisor.py <ログ> <サイトの情報のフォルダ> <サイト名> <返答の保存先.json> [--run]
  --run なし: API を呼ばない。何を送るか（モデル、文字数）だけを表示する。
  --run あり: API を呼ぶ（料金がかかる）。キーは環境変数 ANTHROPIC_API_KEY から読む。コードにもファイルにも書かない。

Claude に渡すのは、指示文（prompts/advisor_ja.md）とブリーフだけ。生のログは渡さない。
検証に落ちた下書きは、理由をつけて Claude に返し、全件を出し直させる（最大 MAX_FIXES 回）。
できあがった返答は scripts/build_report.py の --response にそのまま渡せる。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato import advisor, brief as brief_mod, llm, logs  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"), ap.add_argument("site"), ap.add_argument("name"), ap.add_argument("out")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)

    brief = brief_mod.build_brief(aggregate(logs.parse(a.log)), brief_mod.load_site(a.site), a.name)
    req = advisor.build_request(brief)
    print(f"モデル: {llm.MODEL} / 指示文 {len(req['system'])} 文字 / ブリーフ {len(req['user'])} 文字 / 生ログは送らない")
    if not a.run:
        print("--run が無いので、API は呼んでいません。")
        return 0

    text, _ok, rejected, total_in, total_out = llm.advise(brief)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        body = json.dumps(json.loads(m.group(1) if m else text), ensure_ascii=False, indent=2) + "\n"
    except ValueError:
        body = text  # JSON として読めなくても、返答は失わずに保存する
    out.write_text(body, encoding="utf-8")
    print(f"保存: {a.out}（入力 {total_in} / 出力 {total_out} トークン）")
    return 0 if not rejected else 1


if __name__ == "__main__":
    sys.exit(main())
