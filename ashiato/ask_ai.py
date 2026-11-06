"""目3: お客様が聞きそうな質問に、AIがどう答えるかを確かめる（アクセスログが無くても使える）。

Claude にウェブ検索をさせて答えを取る。他のAI（ChatGPT など）の答えそのものではない。画面にも、そう書く。
事実（質問、答え、出典のドメイン、自社が出典に入っているか・名前が出るか）だけを記録し、判断は Claude がする。
根拠の目印は "ai:Q1" の形。結果は参考情報で、ログの根拠とは別に扱う。
"""
import json
import re
from urllib.parse import urlsplit

from .llm import MODEL

QUESTIONS_PROMPT = ("次の事業者のお客様が、AIに聞きそうな質問を、日本語で3つ考えてください。"
                    "事業者名は含めず、探している人が実際に聞く言い方にします。JSON の配列（文字列3つ）だけを返してください。\n事業者: ")
ANSWER_SYSTEM = "あなたは、一般のお客様の質問に、ウェブ検索を使って日本語で簡潔に答えるアシスタントです。"
MAX_SEARCHES = 3
MAX_TURNS = 3


def _text(msg):
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _urls(msg):
    """答えに使われた出典のURL（検索結果と、本文の引用）。"""
    urls = []
    for b in msg.content:
        t = getattr(b, "type", "")
        if t == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            urls += [getattr(r, "url", "") for r in b.content]
        for c in (getattr(b, "citations", None) or []):
            urls.append(getattr(c, "url", ""))
    return [u for u in dict.fromkeys(urls) if u]


def make_questions(client, business):
    msg = client.messages.create(model=MODEL, max_tokens=1000, messages=[{"role": "user", "content": QUESTIONS_PROMPT + business}])
    text = _text(msg)
    m = re.search(r"\[.*\]", text, re.S)
    qs = [q for q in json.loads(m.group(0) if m else text) if isinstance(q, str) and q.strip()]
    if not qs:
        raise ValueError("質問を作れませんでした")
    return qs[:3]


def ask(client, question):
    """1つの質問にウェブ検索つきで答えさせる。pause_turn（検索が長いとき）は、続きを頼む。"""
    messages = [{"role": "user", "content": question}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES}]
    answer, urls = "", []
    for _ in range(MAX_TURNS):
        msg = client.messages.create(model=MODEL, max_tokens=4000, system=ANSWER_SYSTEM, tools=tools, messages=messages)
        answer += _text(msg)
        urls += _urls(msg)
        if msg.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": msg.content})
    return answer.strip(), [u for u in dict.fromkeys(urls)]


def check_ai_answers(client, site_name, domain="", business=""):
    """質問を作り、答えを取り、事実の一覧にする。domain は自社サイトのドメイン（例: example.com）。"""
    questions = make_questions(client, business or site_name)
    items = []
    for i, q in enumerate(questions, 1):
        answer, urls = ask(client, q)
        hosts = list(dict.fromkeys(urlsplit(u).netloc.lower() for u in urls))
        site_cited = bool(domain) and any(h == domain.lower() or h.endswith("." + domain.lower()) for h in hosts)
        items.append({"question": q, "answer": answer[:1200], "cited_domains": hosts[:8],
                      "site_cited": site_cited, "site_named": site_name in answer, "evidence": [f"ai:Q{i}"]})
    return {"note": "Claudeにウェブ検索をさせた結果です。他のAIの答えとは限りません。", "items": items}
