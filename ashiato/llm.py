"""Claude API を呼んで、ブリーフから下書きを作る。画面（app.py）と scripts/run_advisor.py の両方が使う。

渡すのは、指示文とブリーフだけ（advisor.build_request）。生ログは渡さない。
検証（advisor.accept）に落ちた下書きは、理由を付けて同じ会話の中で出し直させる。
anthropic は、呼ぶときだけ読み込む（このモジュールを読むだけなら、API も通信も使わない）。
"""
from . import advisor

MODEL = "claude-opus-5-5"
MAX_TOKENS = 32000
MAX_FIXES = 2


def fix_request(rejected):
    lines = [f"- {r['draft'].get('title', '?')}: {'; '.join(r['problems'])}" for r in rejected]
    return ("次の下書きは検証に通りませんでした。\n" + "\n".join(lines)
            + "\n\n直せるものは直し、直せないもの（根拠が無い、事実と合わない）は外して、"
              "下書きの全件を JSON の配列だけで返し直してください。")


def call(client, system, messages):
    """1回呼ぶ。(返答の文章, 使用トークン)。拒否・途中切れは RuntimeError。"""
    with client.messages.stream(model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=messages,
                                thinking={"type": "adaptive"}, output_config={"effort": "high"}) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude が応答を断りました")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("返答が途中で切れました")
    return "".join(b.text for b in msg.content if b.type == "text"), msg.usage


def advise(brief, client=None, log=print):
    """ブリーフから、検証に通った下書きを作る。(返答の文章, 有効な下書き, 拒否された下書き, 入力トークン, 出力トークン)。"""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    req = advisor.build_request(brief)
    messages = [{"role": "user", "content": req["user"]}]
    total_in = total_out = 0
    for attempt in range(MAX_FIXES + 1):
        text, usage = call(client, req["system"], messages)
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        ok, rejected = advisor.accept(text, brief)
        log(f"{attempt + 1}回目: 有効 {len(ok)} 件 / 拒否 {len(rejected)} 件")
        if not rejected:
            break
        for r in rejected:
            log(f"  拒否: {r['draft'].get('title', '?')} — {'; '.join(r['problems'])}")
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": fix_request(rejected)}]
    return text, ok, rejected, total_in, total_out
