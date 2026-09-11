# Lovart / nanobanana 用｜サムネイル背景プロンプト

- **サムネのレイアウト（文字入り）**: https://claude.ai/code/artifact/395cd670-3681-4d11-acf0-72dc67af8368
- Lovartのプロジェクト: `https://www.lovart.ai/canvas?projectId=2norm5rehi4glovart`

> ## 大前提：AI画像に日本語を描かせない
> nanobanana を含め、画像生成モデルは**日本語の文字を正しく描けません**（崩れた偽物の漢字になる）。
> だから全プロンプトに `no text, no letters` を入れてあります。
> **文字は上のリンクのレイヤーを使ってください。** 分担はこうです。
>
> | | 担当 |
> |---|---|
> | 背景写真 | **Lovart / nanobanana**（このファイルのプロンプト） |
> | 文字・赤バツ・レイアウト | **上のリンクのアートボード**（位置・サイズ・色は確定済み） |

## 共通設定（最初に一度だけ）

Lovartのスタイル指定に入れておくと、4案の絵が揃います。

```
STYLE: Warm, clean Japanese home lifestyle photography. Soft natural window light.
Muted natural palette — warm beige, off-white, pale wood, with one warm amber accent.
Shallow depth of field, 50mm lens look. Calm, reassuring, slightly nostalgic.
Photorealistic but soft — not harsh, not clinical, not stock-photo glossy.
No text, no letters, no watermarks, no logos. 16:9 aspect ratio, 1280x720.
```

**必ず守ること**

1. **`no text, no letters` を消さない。**
2. **ダニそのものを描かせない。** 不快で離脱を招きます。「光の中に舞うホコリ」「繊維のマクロ」で間接的に見せる方針です。全プロンプトに `no insects` が入っています。
3. **文字を置く側を空ける。** 各プロンプトの最後に、どちら側を空けるか書いてあります。

---

## 案A｜順番が、逆です（本命）

文字は**右3分の1**に縦組みで入るので、そこを空けます。

```
A Japanese woman in her late 50s sitting on the edge of a bed in the morning,
covering her nose with a tissue, mid-sneeze, eyes slightly closed. Behind her a
white futon and duvet on a low bed. Bright morning light from a window, countless
fine dust particles floating and glittering in the light beam. Her expression is
troubled but not dramatic. She is positioned in the LEFT HALF of the frame.
The RIGHT ONE-THIRD of the frame is empty, darker background — leave it clear.
No insects. No text, no letters, no watermarks, no logos. 16:9.
STYLE: [共通設定を貼る]
```

## 案B｜夏より汚い（季節フック）

左右で夏と秋を対比させます。**中央**に文字が入るので空けます。

```
Split composition, two halves of one image. LEFT HALF: a white futon airing on a
balcony railing in strong summer sunlight, clear blue sky, clean and bright.
RIGHT HALF: the same white futon indoors in soft low autumn light, with fine dust
particles floating thickly and visibly in a slanted light beam, the air noticeably
hazier. Same futon, two seasons, the autumn side visibly dustier. The CENTRE of the
frame is simple and uncluttered — leave it clear.
No insects. No text, no letters, no watermarks, no logos. 16:9.
STYLE: [共通設定を貼る]
```

## 案C｜4分（数値型・自チャンネル実測1.76倍）

文字は**左半分**に入るので、そこを空けます。

```
Close-up of a vacuum cleaner head moving slowly across a white futon laid on a bed.
Only a hand and forearm visible — no face. Bright afternoon light from a window,
warm and soft. The futon fills the RIGHT HALF of the frame at a slight angle.
The LEFT HALF is simple, darker, uncluttered — leave it clear.
No insects. No text, no letters, no watermarks, no logos. 16:9.
STYLE: [共通設定を貼る]
```

## 案D｜旧台本（7選版）用

文字は**右3分の1**、赤い年齢バッジが左下に入ります。

```
A Japanese woman in her early 60s sitting on the edge of a bed in the morning,
holding back a sneeze with a tissue, eyes slightly closed. Behind her a white futon
on a low bed. Bright morning light from a window, fine dust particles floating and
glittering in the light beam. Gentle, everyday, not dramatic. She is positioned in
the LEFT HALF. The RIGHT ONE-THIRD of the frame is empty, darker — leave it clear.
No insects. No text, no letters, no watermarks, no logos. 16:9.
STYLE: [共通設定を貼る]
```

---

## どれを使うか

| 案 | 根拠 | 判断 |
|---|---|---|
| **A 順番が、逆です** | 競合508本に無い角度（敵は生きたダニではない）。台本の中心と一致 | **本命** |
| **B 夏より汚い** | 季節の意外性は強いが、他チャンネルにもある角度 | 対抗 |
| **C 4分** | 自チャンネルの実測で**数値型は1.76倍**。4分は台本どおりの正直な数字 | **Aと比較する価値あり** |
| D 旧台本用 | 公開するのは準拠版なので、出番は無い見込み | 予備 |

> **AとCを実際に回して比べてください。**
> 直近25本が600〜4,000回という状態は、視聴維持ではなく**インプレッションの問題**です。
> 台本をこれ以上磨くより、サムネのA/Bを回すほうが効きます（2人の採点者が独立して同じ判定）。

## 文字のスペック（自分で組む場合）

| 項目 | 値 |
|---|---|
| サイズ | 1280 × 720 |
| 書体 | Noto Sans JP **900**（太いゴシックなら何でも可） |
| 主コピー | 86〜96px／縦組み／白 `#ffffff`、強調語だけ黄 `#ffd400` |
| 副コピー | 50〜58px／同上 |
| 縁取り | 黒 `#0d0d0d` を 14px（副コピーは9px）。`paint-order: stroke fill` |
| 赤バツ・バッジ | `#e8342a` |
| 空けておく場所 | 右下 210×54px（YouTubeの再生時間バッジが乗る） |
