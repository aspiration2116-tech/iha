# メルカリShops 自動出品アプリ

メルカリShops **公式API** を使って商品を自動出品するローカルアプリです。
商品を「出品キュー」に登録しておくと、ワンクリックの一括出品、または
毎日決まった時刻の自動出品ができます。追加ライブラリ不要(Python3標準のみ)。

> **重要**: これは事業者向けの「メルカリShops」用です。個人向けメルカリ(フリマ)には
> 公開APIがなく、外部ツールでの自動出品は利用規約で禁止されています(アカウント停止の
> リスクがあるため本アプリでは対応しません)。

## 利用条件(先に済ませておくこと)

1. **メルカリShopsに出店する**(スマホのメルカリアプリまたはWebから開設)
2. **API連携の利用申請をする** — API連携は事前申請制です。
   [メルカリShopsガイド「API連携について」](https://support.mercari-shops.com/hc/ja/categories/15261095776281-API%E9%80%A3%E6%90%BA%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6) を参照
3. **アクセストークンを発行する** — ショップ管理画面 → [設定] →
   [APIアクセストークンを発行] → トークン名を入れて発行(発行直後しかコピーできません)。
   [発行手順の公式ヘルプ](https://support.mercari-shops.com/hc/ja/articles/12290169038617)

## 起動方法

```bash
python3 mercari_server.py
# → ブラウザで http://localhost:8771 を開く
```

Macなら `メルカリ出品を開く.command` をダブルクリックでも起動できます。

## 使い方

1. **設定・ログ** タブでアクセストークンを貼り付けて保存
   (トークンは `mercari_token.txt` に保存され、gitには含まれません。
   環境変数 `MERCARI_SHOPS_TOKEN` でも指定可能)
2. **接続テスト** を押して「接続成功」になることを確認
3. **商品を追加** タブ、または **CSV一括登録** タブで商品をキューに登録
   - CSVの列: `name, description, price, stock, category_id, condition, image_urls`
     (画像URLが複数あるときは `|` 区切り。ひな形は `mercari_products_sample.csv`)
   - **画像は `https://` の公開URLのみ指定可能**です(メルカリ側がURLから取得します)。
     ローカル画像は使えないので、先にどこかへホストしてください。
     [公式ヘルプ: 画像URLの指定](https://support.mercari-shops.com/hc/ja/articles/15366688241305)
4. **出品キュー** タブで「今すぐ出品する」を押すと一括出品されます
5. 毎日自動で出品したい場合は **設定・ログ** タブで「毎日自動で出品する」を有効化
   (アプリを起動している間だけ動きます。1回の件数や間隔は `mercari_config.json` の
   `schedule` で調整)

初めて本番出品する前に、**サンドボックス環境**(設定タブのチェックボックス)で
動作確認することをおすすめします。

## コマンドラインでも使えます

```bash
python3 mercari_api.py test                        # 接続テスト
python3 mercari_api.py ops                         # 使えるquery/mutation一覧
python3 mercari_api.py schema CreateProductInput   # 出品入力のフィールド確認
python3 mercari_api.py enum ProductCondition       # 商品状態のenum値確認
python3 mercari_autolist.py import mercari_products_sample.csv
python3 mercari_autolist.py run 5                  # 5件出品
```

## 出品時の既定値について

`mercari_config.json` の `product_defaults` が、フォームで指定しなかった
フィールドの既定値として `createProduct` の入力にそのまま使われます
(配送方法・発送日数・商品の状態など)。

**注意**: ここに入れてある値(`condition: "NEW"` など)は一般的な想定値です。
APIのスキーマは更新されることがあるため、出品前に必ず

```bash
python3 mercari_api.py schema CreateProductInput
python3 mercari_api.py enum ProductCondition
```

で実際のフィールド名・enum値を確認し、`product_defaults` を合わせてください
(UIの「スキーマ確認」ボタンでも見られます)。正式なリファレンスは
[APIドキュメント](https://api.mercari-shops.com/docs/index.html) を参照。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `mercari_server.py` | ローカルダッシュボード(ポート8771)+自動出品スケジューラ |
| `mercari_index.html` | ダッシュボード画面 |
| `mercari_api.py` | メルカリShops GraphQL APIクライアント(CLIとしても使用可) |
| `mercari_autolist.py` | 出品キュー(SQLite)とCSV取込・一括出品エンジン |
| `mercari_config.json` | エンドポイント・出品既定値・スケジュール設定 |
| `mercari_products_sample.csv` | CSV取込のひな形 |
| `mercari_token.txt` | アクセストークン(自動生成・git管理外) |
| `mercari.db` | 出品キューとログ(自動生成・git管理外) |

## 参考リンク

- [メルカリShops APIの紹介(公式エンジニアリングブログ)](https://engineering.mercari.com/blog/entry/20221121-mercari-shops-api/)
- [APIリファレンス](https://api.mercari-shops.com/docs/index.html)
- [API連携時によくある技術的な質問](https://support.mercari-shops.com/hc/ja/articles/15366795504665)
