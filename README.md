# 足跡 (ashiato)

AIに見つけてもらうための道しるべ。

サイトのアクセスログには、AIが訪ねて来た足跡が残っています。
足跡は、AIが読みに来たページ、探したのに無かったページ、
AIの回答から来たお客さんを教えてくれます。
ところが、ログを読めるのはエンジニアだけです。
足跡は、その足跡を読み取り、何を作り、何を直せばAIに見つけてもらえるかを、
日本語で、下書きつきで示します。

Built with Claude: Japan 2026 への参加作品です。開発は 2026-11-02 に始めました。

## 誰のためのものか

エンジニアもコンサルタントもいない、小さな事業者(宿、商店、自治体のサイト)。
ログを開いたことがない人でも、AIに見つけてもらえているかが分かるようにします。

## できること

AIがそのサイトをどう見ているかを、3つの目で確かめます。どれも、事実を集めるのはコード、判断と下書きはClaude、承認は人です。

1. **アクセスログ**: AIが実際に何を読みに来て、読めたか(主な機能。下の「使ってみる」)
2. **サイトの公開ページ**: AIが読める状態か。`robots.txt` で断っていないか、案内図(サイトマップ)にあるか、本文が短くないか。
   アクセスログが無くても使えます(`ashiato/sitecheck.py`)。
3. **AIの答え**: お客様が聞きそうな質問に、AIがどう答えるか。Claudeにウェブ検索をさせた結果で、他のAIの答えとは限りません
   (`ashiato/ask_ai.py`)。

機能の一覧:

- Cloudflare Logpush や nginx/Apache のアクセスログを読み込む(行頭にドメイン名が付く形式も読めます)
- AIクローラー、AI回答エンジン、人の訪問を見分ける
- AIが探したのにページが無かった箇所を見つける
- Claudeが原因を判断し、直すための下書きを根拠の行つきで作る
- 人が承認して使う(自動では何も公開しない)
- 承認した下書きを、まとめてコピーできる(「反映のしかた」付き)
- 修正の前後で結果を比べる(直したあとのログを、あとから入れたときに出ます)

## 方針

- 実際のログはこのリポジトリに入れません。デモは合成データだけを使います。
- 下書きは提案です。公開するのは人です。

## 使ってみる

標準ライブラリだけで動きます(Python 3)。

```
python3 scripts/gen_synthetic.py            # 合成データA(旅館)を data/synthetic/ryokan/ に作る
python3 scripts/gen_synthetic_b.py          # 合成データB(読書ノートのサービス)を data/synthetic/readnote/ に作る
python3 scripts/serve.py data/synthetic/ryokan/site/before 雪待荘 \
  --response examples/ryokan/claude_response.json
pip install anthropic                       # API で下書きを取るときだけ必要（API キーは環境変数 ANTHROPIC_API_KEY）
python3 scripts/run_advisor.py data/synthetic/ryokan/before.ndjson data/synthetic/ryokan/site/before 雪待荘 out/ryokan_response.json --run
```

入れたログから、その場で Claude に下書きを作らせるには、`serve.py` に `--response` の代わりに `--live` を付けます
（環境変数 ANTHROPIC_API_KEY が要ります。ログを入れるたびに API を呼ぶので、料金がかかります）。

上の run_advisor.py は、`--run` を付けると API を呼びます（料金がかかります）。付けなければ呼びません。
`serve.py` には、`examples/` の保存済みの返答を `--response` に渡しても動かせます（API キーは要りません）。

ブラウザで `http://127.0.0.1:8765/` を開き、`data/synthetic/ryokan/before.ndjson` を落とします。
レポートの下に「直したあとのアクセス記録」の欄が出るので、`data/synthetic/ryokan/after.ndjson` を落とすと、前後の比較が出ます。
入れたログはこのパソコンの中で解析するだけで、ディスクにも外にも書き出しません。
テストは `python3 -m unittest discover -s tests` です。

## しくみ

1. コードがログを読み、AIの種類を分け(UAの表)、ページごとに数えます(`ashiato/`)。
2. 数えた結果と、サイトの情報から「ブリーフ」を作ります。Claudeに渡すのはこれだけで、生のログは渡しません。
3. Claudeが原因を判断し、下書きを書きます(指示は `prompts/advisor_ja.md`)。
4. 下書きはコードが検証します。根拠の行が無い、ブリーフに無い行を指す、事実と合わない種類(転送先が無いのに「転送」など)の下書きは、保存を拒否します。
5. 人が、承認・修正・却下します。サイトには何も書き込みません。

## 今の状況

- 目2(サイトの公開ページ)と目3(AIの答え)は、実装し、偽のクライアントを使ったテストで確認しています。
  実際の API での動作確認は、README の更新時点では、まだ行っていません。起動時に `--live` を付けると、画面に診断の欄が出ます
  (環境変数 ANTHROPIC_API_KEY が要ります。料金がかかります)。
- Managed Agents の設定ファイル(`agents/`、`environments/`)と、実行スクリプト(`scripts/run_advisor_managed.py`)は、
  合成データ(旅館)のブリーフで1回、実際に実行しました(Agent・Environment・Session を使用。生ログは送っていません)。
  下書きは13件が、検証に1回で通りました。実サイトでは実行していません。

- 動くもの: ログの読み込み(Cloudflare Logpush、nginx/Apache)、AIの種類の判別、ページ別の集計、ブリーフの作成、
  下書きの検証、日本語の画面(全体、ページごとの様子、調べた順番、次にやること、手を付けなくてよいこと、前後比較)。
- Claude API(`claude-opus-5-5`)を呼び出して下書きを取る部分があります(`scripts/run_advisor.py`)。
  ブリーフと指示文だけを渡し、検証に落ちた下書きは理由を付けて出し直させます。API キーは環境変数から読み、
  `--run` を付けないと API を呼びません。同じ下書きを Managed Agents 経由でも取れます
  (`scripts/run_advisor_managed.py`。上限額つきの Session で、ツールは全部オフ)。Agent SDK は使っていません。
- `examples/` の下書きは、Claude Code の中の別のClaudeに、ブリーフと指示文だけを渡して書かせた実際の出力です。
- 画面の「見本」の下書きは、Claudeではなく決まった規則で作ったものです(Claudeの返答を渡さないと出ます)。
- 実サイトでの確認は、集計の傾向を見たのみです。このリポジトリには、実際のログも、実際の集計値も入っていません。
- 設計とデモの台本は `docs/` にあります。

## 来歴について

作者は以前、同じ分野の手法をニュースレターに書いたことがあります。
このリポジトリのコード、画面、データ、プロンプトは、すべてイベント期間中に新しく作ったものです。
