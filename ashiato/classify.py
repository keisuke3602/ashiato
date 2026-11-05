"""ユーザーエージェント（UA）の自前の表で、リクエストの送り手の種類を決める。

種類:
  ai_crawler    AIの学習用クローラー
  ai_search     AI検索のクローラー
  ai_assistant  利用者の質問に応じて取りに来る取得
  search        従来の検索ボット
  scanner       脆弱性を探る・ライブラリ由来の自動アクセス
  human         ブラウザ
  unknown       上のどれでもない
VerifiedBotCategory は「検証されたか（空でないか）」の印にだけ使い、種類の判定には使わない。
"""

AI_KINDS = ("ai_crawler", "ai_search", "ai_assistant")

# (UAに含まれる文字列（小文字）, 表示名, 種類)。上から順に最初に一致したものを採る。
UA_TABLE = [
    ("claudebot", "ClaudeBot", "ai_crawler"),
    ("anthropic-ai", "anthropic-ai", "ai_crawler"),
    ("claude-searchbot", "Claude-SearchBot", "ai_search"),
    ("claude-user", "Claude-User", "ai_assistant"),
    ("gptbot", "GPTBot", "ai_crawler"),
    ("oai-searchbot", "OAI-SearchBot", "ai_search"),
    ("chatgpt-user", "ChatGPT-User", "ai_assistant"),
    ("perplexitybot", "PerplexityBot", "ai_search"),
    ("perplexity-user", "Perplexity-User", "ai_assistant"),
    ("ccbot", "CCBot", "ai_crawler"),
    ("bytespider", "Bytespider", "ai_crawler"),
    ("googlebot", "Googlebot", "search"),
    ("bingbot", "Bingbot", "search"),
    ("python-requests", "python-requests", "scanner"),
    ("zgrab", "zgrab", "scanner"),
    ("curl/", "curl", "scanner"),
    ("go-http-client", "Go-http-client", "scanner"),
    ("wget", "wget", "scanner"),
]


def classify_ua(ua):
    """(表示名, 種類) を返す。"""
    low = ua.lower()
    for needle, name, kind in UA_TABLE:
        if needle in low:
            return name, kind
    if low.startswith("mozilla/") and any(t in low for t in ("chrome/", "safari/", "firefox/", "mobile/")):
        return "browser", "human"
    return "unknown", "unknown"


def is_verified(category):
    """VerifiedBotCategory が空でなければ検証済み。取得元に項目が無い（None）ときは判定不能で None。"""
    if category is None:
        return None
    return category != ""
