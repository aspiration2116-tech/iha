# LP（プロフィールリンク先）

Instagramのプロフィールに置く**唯一のリンク**の遷移先。年齢確認 → 作品一覧 → FANZA、を1ページで担う。

## ファイル

| ファイル | 役割 |
|---|---|
| `index.html` | 本体。触らなくていい |
| `works.json` | 作品データ。**運用中に編集するのはここだけ** |

## works.json の書き方

```json
{
  "id": "w004",
  "title": "作品タイトル",
  "circle": "サークル名",
  "category": "jireta",        // categories の id と合わせる
  "comment": "1〜2文の紹介。ネタバレなし",
  "postedAt": "2026-08-19",     // この降順で並ぶ
  "reel": "https://www.instagram.com/reel/XXXX/",  // 空文字なら非表示
  "url": "https://al.dmm.co.jp/?lurl=...&af_id=YOURID-001&ch=link_tool&ch_id=text",
  "adult": true                 // true = 年齢確認を通った人だけに表示
}
```

カテゴリを増やすときは `categories` にも `{ "id": "...", "label": "..." }` を足す。

## 動作確認

```bash
python3 -m http.server 8899
# → http://localhost:8899/
```

`file://` で直接開くと `works.json` の読み込みがブラウザにブロックされて真っ白になる。必ずサーバー経由で確認する。

年齢確認をやり直したいときは、開発者ツールのコンソールで:

```js
localStorage.removeItem('age_ok_v1'); location.reload();
```

## 実装されていること

- 年齢確認モーダル（`localStorage` に記憶。「いいえ」で外部へ離脱）
- `adult: true` の作品は確認前に**DOMごと出さない**
- カテゴリタブでの絞り込み
- `?from=reel012` を `af_id` の枝番に差し込む流入元計測
- アフィリエイトリンクに `rel="nofollow sponsored noopener"`
- 広告表記をページ上部と下部に表示（`works.json` の `site.note`）
- 検索エンジンからの流入を切る `noindex`（消したければ `<meta name="robots">` を削除）

## 公開先

`05_リンク導線とアフィリエイト設定.md` の「ホスティング先の選び方」を参照。
成人向けリンクを許容するホスティング＋独自ドメインが前提。
