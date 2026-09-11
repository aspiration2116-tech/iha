# youtube-research

ライフハック雑学チャンネル(@tomorrow_life_hack)のネタ探し・競合分析を自動化するツール。APIキー不要(RSS + ページ解析)。

## 領域

- データ収集: YouTube/Web上のネタ・競合動画情報を集める
- 分析: 集めたデータから「今作るべきネタ」を計算する
- 配信: ローカルサーバーで結果をブラウザ表示する
- 設定・運用: チャンネル/キーワード設定、Mac移行・自動起動

## ルーティング表

| やりたいこと | ファイル |
| --- | --- |
| 収集ロジック全体の流れ | `research.py` |
| YouTube取得(RSS/videosページ/検索ページ) | `ytfetch.py` |
| Web横断検索(X/ニュース/はてな/ブログ等) | `websearch.py` |
| 「伸びてるネタ」の判定ロジック(VPH・倍率・タイトル型) | `analysis.py` |
| ダッシュボードAPI/配信ロジック | `server.py` |
| ダッシュボードUI | `index.html` |
| 対象チャンネル・キーワード・除外語・ポート設定 | `config.json` |
| 別Macへの移行手順 | `README.md` |
| 最新の分析結果(人間向け、毎回上書き) | `ネタ候補.md` |
| 生データ・実行履歴(gitでは追跡しない) | `research.db` / `latest.json` / `*.log` |

`research.db`・`latest.json`・`*.log`・`ネタ候補.md` は実行のたびに変わる生成物のため `.gitignore` で除外している。ソースはPythonファイルのみ。
