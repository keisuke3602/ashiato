#!/usr/bin/env python3
"""ログから作ったブリーフを Claude API に渡して、下書きの返答を保存する。

使い方: python3 scripts/run_advisor.py <ログ> <サイトの情報のフォルダ> <サイト名> <返答の保存先.json> [--run]
  --run なし: API を呼ばない。何を送るか（モデル、文字数）だけを表示する。
  --run あり: API を呼ぶ（料金がかかる）。キーは環境変数 ANTHROPIC_API_KEY から読む。コードにもファイルにも書かない。

Claude に渡すのは、指示文（prompts/advisor_ja.md）とブリーフだけ。生のログは渡さない。
検証（ashiato/advisor.py の accept）に落ちた下書きは、理由をつけて Claude に返し、全件を出し直させる（最大 MAX_FIXES 回）。
できあがった返答は scripts/build_report.py の --response にそのまま渡せる。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato import advisor, brief as brief_mod, logs  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402

MODEL = "claude-opus-5-5"
MAX_TOKENS = 32000
MAX_FIXES = 2


def call(client, system, messages):
    """1回呼ぶ。(返答の文章, 使用トークン)。拒否・途中切れは例外。"""
    with client.messages.stream(model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=messages,
                                thinking={"type": "adaptive"}, output_config={"effort": "high"}) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Claude が応答を断りました: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("返答が途中で切れました（max_tokens）")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return text, msg.usage


def fix_request(rejected):
    lines = [f"- {r['draft'].get('title', '?')}: {'; '.join(r['problems'])}" for r in rejected]
    return ("次の下書きは検証に通りませんでした。\n" + "\n".join(lines)
            + "\n\n直せるものは直し、直せないもの（根拠が無い、事実と合わない）は外して、"
              "下書きの全件を JSON の配列だけで返し直してください。")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"), ap.add_argument("site"), ap.add_argument("name"), ap.add_argument("out")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)

    brief = brief_mod.build_brief(aggregate(logs.parse(a.log)), brief_mod.load_site(a.site), a.name)
    req = advisor.build_request(brief)
    print(f"モデル: {MODEL} / 指示文 {len(req['system'])} 文字 / ブリーフ {len(req['user'])} 文字 / 生ログは送らない")
    if not a.run:
        print("--run が無いので、API は呼んでいません。")
        return 0

    import anthropic  # --run のときだけ必要
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": req["user"]}]
    total_in = total_out = 0
    for attempt in range(MAX_FIXES + 1):
        text, usage = call(client, req["system"], messages)
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        ok, rejected = advisor.accept(text, brief)
        print(f"{attempt + 1}回目: 有効 {len(ok)} 件 / 拒否 {len(rejected)} 件")
        if not rejected:
            break
        for r in rejected:
            print(f"  拒否: {r['draft'].get('title', '?')} — {'; '.join(r['problems'])}", file=sys.stderr)
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": fix_request(rejected)}]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        body = json.dumps(json.loads(_json_text(text)), ensure_ascii=False, indent=2) + "\n"
    except ValueError:
        body = text  # JSON として読めなくても、返答は失わずに保存する
    out.write_text(body, encoding="utf-8")
    print(f"保存: {a.out}（入力 {total_in} / 出力 {total_out} トークン、呼び出し {attempt + 1} 回）")
    return 0 if not rejected else 1


def _json_text(text):
    import re
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1) if m else text


if __name__ == "__main__":
    sys.exit(main())
