# Lovart用 プロンプト集 —— 台本01 v17

**このファイルは `gen_prompts.py` が台本から自動生成します。台本を直したら再実行してください。**

```bash
python3 gen_prompts.py ../台本/01_披露宴_定食屋の親_原稿.md > lovart_プロンプト集.md
```

---

## 作業の順番(この順でないと絵が揃いません)

1. **キャラクター設定シートを先に5枚作る**(下記)。Lovartのキャンバスに置いて、以降のカットで**参照画像として毎回添える**。これをやらないと、同じ人物が毎カット別人になります。
2. **場所シートを3枚作る**(みやこ食堂・料亭・大宴会場)。同じ店が毎回違う店に見えるのを防ぎます。
3. カットを**上から順に**生成する。1カット1枚。長い場面には2枚目を足す。
4. `動画/images/` に `cut01.png` … の名前で保存する。
5. `python3 compose_final.py` で動画が組み上がります。

> **無料枠を節約するコツ**
> ① キャラシートと場所シートで枠を使い切らないよう、**1回で複数ポーズを1枚に**出す(下のシートのプロンプトはそう書いてあります)。
> ② 顔が出ないカット(手・小物・引きの絵)は品質が安定するので**先に**まとめて出す。
> ③ うまくいかないカットは、文章を足すより**削って**やり直す。長いプロンプトほど崩れます。
> ④ 画面比は必ず **16:9 / 1920×1080**。縦横が違うと組むときに切れます。

---

## キャラクター設定シート(最初に作る5枚)

各プロンプトの末尾に共通スタイルを付けてください。

**共通スタイル(全カットに付ける)**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles
```

### シートA 中村結衣(主人公・29歳)

```
character reference sheet, four views of the same Japanese woman age 29 on one canvas: front, three-quarter, profile, and from behind. shoulder-length black hair tied low, narrow calm eyes, no strong makeup, slim, 158cm. outfit variations shown side by side: simple beige knit with dark skirt / white chef coat with navy apron / white A-line wedding dress with hair up / deep green colored formal gown. neutral expression in every view
```

> **作画ルール:** この人物は**ラスト(カット43)まで一度も泣きません**。困り顔・涙目も禁止。怒りも出さない。ずっと静かな顔。

### シートB 中村健一(父・70歳前後)

```
character reference sheet, three views of the same Japanese man around 70 on one canvas: front, three-quarter, and hands close-up. close-cropped grey hair, deep face lines, slight stoop, thick weathered hands with cracked knuckles and faded burn scars. outfit variations side by side: white cook coat with towel headband and navy apron / an ill-fitting old charcoal suit / a rented morning coat. quiet expression
```

> **作画ルール:** 手は**この台本の主役**です。カット04・45で寄ります。設定シートの段階で手を作り込んでください。

### シートC 神崎政子(義母・60代前半)

```
character reference sheet, three views of the same Japanese woman in her early sixties on one canvas: front, three-quarter, profile. stiffly set bouffant hair, thin drawn eyebrows, pearl earrings, a faint smile that never reaches the eyes. outfit variations side by side: pastel twin-set with pearls / black kurotomesode kimono with five family crests and gold obi, a folded fan tucked into the obi. elegant upright posture
```

> **作画ルール:** 黒留袖の**末広(扇子)は絶対に開かせない**。帯に挿したまま、握るだけ。開いて扇いだり口元を隠したりすると、この層の視聴者が必ずコメントで指摘します。口元を隠すときは**袂(たもと)**です。

### シートD 神崎涼介(婚約者・33歳)

```
character reference sheet, three views of the same Japanese man age 33 on one canvas: front, three-quarter, profile. neat side-parted black hair, handsome but soft-jawed, easy to read as weak. outfit variations side by side: navy business suit / black formal morning coat with silver tie. two expressions: warm and sincere / cold and evasive
```

> **作画ルール:** 前半(カット07・08)は**本当にいい人の顔**で描いてください。そこが本物でないと、後半の裏切りが効きません。

### シートE 鷹野誠一(会長・82歳)

```
character reference sheet, three views of the same Japanese man age 82 on one canvas: front, three-quarter, seated. full head of white hair combed back, deep-set sharp eyes, straight back, large weathered hands. outfit variations side by side: plain grey jacket over a shirt / dark navy suit with a silver tie. calm authoritative expression
```

> **作画ルール:** 披露宴では**濃紺のスーツに銀のネクタイ**です。**黒紋付羽織袴は着せないでください**(親族ではない招待客の紋付は格が高すぎて非常識に見えます)。

### 脇役(シートは不要。カットごとに指定)

| 役 | 指定 |
|---|---|
| 黒田常務(55) | grey suit, silver tie, glasses, middle-aged Japanese man |
| プランナー(30・女) | navy uniform suit, clipboard, polite |
| 支配人(50・男) | black tailcoat, white gloves, formal hotel manager |
| 親族A・B(50〜60代・女) | formal iro-tomesode kimono, seated guests |
| 受付(30・男) | dark suit, reception desk |

---

## 場所シート(3枚)

### みやこ食堂

```
establishing shot of a small Showa-era Japanese diner in a shopping street, worn wooden counter seating eight, handwritten paper menu strips on the wall, a noren curtain at the entrance, an old paper schedule sheet pinned near the kitchen, warm tungsten light
```

### 料亭(顔合わせ)

```
a formal tatami room in an expensive traditional Japanese restaurant, tokonoma alcove, low lacquer table, shoji screens, cool restrained daylight
```

### 都心のホテル大宴会場

```
a grand hotel banquet hall for 120 guests, crystal chandeliers, round tables with white cloth, a raised head table, tall curtained windows
```

---

## カット表

各カットの `ト書き` は台本そのままです。`メモ` は作画上の判断が要る点だけ書いています。
