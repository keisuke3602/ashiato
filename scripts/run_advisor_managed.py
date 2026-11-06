#!/usr/bin/env python3
"""Managed Agents で下書きを取る（Agent と Environment は、先に `ant apply` で作っておく）。

使い方: python3 scripts/run_advisor_managed.py <ログ> <サイトの情報のフォルダ> <サイト名> <返答の保存先.json> [--run]
  --run なし: 何も呼ばない。使う Agent / Environment の ID と、上限金額だけを表示する。
  --run あり: Session を1つ作り、ブリーフを送る（料金がかかる。上限は BUDGET_CENTS）。キーは環境変数 ANTHROPIC_API_KEY。

Session に入れるのは、ブリーフだけ。生のログは入れない（Session の記録は、消すまで残るため）。
Agent は、ツールを使わない設定（agents/ashiato-advisor.md）。ツールの許可を求められたら、すべて断る。
返答は scripts/run_advisor.py と同じ検証（ashiato/advisor.py の accept）に通し、落ちた下書きは同じ Session の中で出し直させる。
IDs は claude-lock.json（`ant apply` が書く）から読む。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ashiato import advisor, brief as brief_mod, logs  # noqa: E402
from ashiato.aggregate import aggregate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AGENT_KEY, ENV_KEY = "./agents/ashiato-advisor.md", "./environments/ashiato-env.yaml"
BUDGET_CENTS = "300"  # 1 Session の上限: $3.00
MAX_FIXES = 2


def load_ids(lock_path=ROOT / "claude-lock.json"):
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))["resources"]
    return lock[AGENT_KEY]["id"], lock[ENV_KEY]["id"]


def fix_request(rejected):
    lines = [f"- {r['draft'].get('title', '?')}: {'; '.join(r['problems'])}" for r in rejected]
    return ("次の下書きは検証に通りませんでした。\n" + "\n".join(lines)
            + "\n\n直せるものは直し、直せないもの（根拠が無い、事実と合わない）は外して、"
              "下書きの全件を JSON の配列だけで返し直してください。")


def ask(client, session_id, text):
    """メッセージを1つ送り、Claude が止まるまでの返答の文章を返す。ストリームを先に開く。"""
    out = []
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id, events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}])
        for event in stream:
            if event.type == "agent.message":
                out += [b.text for b in event.content if b.type == "text"]
            elif event.type in ("agent.tool_use", "agent.mcp_tool_use") and getattr(event, "evaluated_permission", "") == "ask":
                client.beta.sessions.events.send(session_id=session_id, events=[{
                    "type": "user.tool_confirmation", "tool_use_id": event.id, "result": "deny"}])  # ツールは使わせない
            elif event.type == "session.status_idle":
                reason = event.stop_reason.type
                if reason == "requires_action":
                    continue
                if reason == "budget_reached":
                    raise RuntimeError("上限金額に達しました")
                break
            elif event.type == "session.status_terminated":
                raise RuntimeError("Session が終了しました")
    return "".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"), ap.add_argument("site"), ap.add_argument("name"), ap.add_argument("out")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)

    brief = brief_mod.build_brief(aggregate(logs.parse(a.log)), brief_mod.load_site(a.site), a.name)
    user = advisor.build_request(brief)["user"]
    agent_id, env_id = load_ids()
    print(f"Agent {agent_id} / Environment {env_id} / 上限 ${int(BUDGET_CENTS) / 100:.2f} / ブリーフ {len(user)} 文字 / 生ログは送らない")
    if not a.run:
        print("--run が無いので、Session は作っていません。")
        return 0

    import anthropic
    client = anthropic.Anthropic()
    session = client.beta.sessions.create(
        agent=agent_id, environment_id=env_id, title="ashiato advisor",
        budget={"type": "limit", "max_list_cost": {"amount": BUDGET_CENTS, "currency": "USD"}})
    print(f"Session: {session.id}")
    text = ask(client, session.id, user)
    for attempt in range(MAX_FIXES + 1):
        ok, rejected = advisor.accept(text, brief)
        print(f"{attempt + 1}回目: 有効 {len(ok)} 件 / 拒否 {len(rejected)} 件")
        if not rejected or attempt == MAX_FIXES:
            break
        for r in rejected:
            print(f"  拒否: {r['draft'].get('title', '?')} — {'; '.join(r['problems'])}", file=sys.stderr)
        text = ask(client, session.id, fix_request(rejected))
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        body = json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n"
    except ValueError:
        body = text
    out.write_text(body, encoding="utf-8")
    print(f"保存: {a.out}")
    return 0 if not rejected else 1


if __name__ == "__main__":
    sys.exit(main())
