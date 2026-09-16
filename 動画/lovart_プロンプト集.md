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


## 【0:00-0:10】コールドオープン

### カット01 「開宴の問い」　`0:00` 〜　12秒 / 5行

> **ト書き(台本):** 静まり返った宴会場。マイクのこすれる音。主賓席の老人。義母の顔から血の気が引く。
>
> **メモ:** **最重要カット。サムネ候補。** 老人は後ろ姿ぎみ、義母の顔に焦点。義母の血の気が引く瞬間

**ファイル名 `images/cut01.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, wide shot of a hushed 120-guest hotel banquet hall, crystal chandeliers, round tables, an elderly man in a dark navy suit standing at the head table with a microphone, an older woman in a black kurotomesode kimono frozen mid-smile, all faces turned toward her
```


## 【0:10-0:30】約束

### カット02 「義母の宣告」　`0:12` 〜　16秒 / 5行

> **ト書き(台本):** (なし)
>
> **メモ:** 義母の顔の寄り。上品さと侮蔑を同居させる

**ファイル名 `images/cut02.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, medium shot of an older Japanese woman in a pastel twin-set and pearls, chin slightly raised, faint smile that does not reach her eyes, soft-focus hotel lounge background
```


## 【0:30-2:05】状況説明

### カット03 「みやこ食堂」　`0:28` 〜　25秒 / 7行

> **ト書き(台本):** (なし)
>
> **メモ:** 店の全景。看板・のれんは文字なしで形だけ

**ファイル名 `images/cut03.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, interior of a small Showa-era shotengai diner, worn wooden counter seating eight, handwritten paper menus on the wall, an old man in a white cook coat and towel headband working behind the counter, steam rising
```

### カット04 「父の手」　`0:53` 〜　10秒 / 3行

> **ト書き(台本):** (なし)
>
> **メモ:** 手だけ。顔は入れない。この台本の中心の絵

**ファイル名 `images/cut04.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, extreme close-up of an old man's hands on a cutting board, thick knuckles, cracked skin, faded burn scars, holding a kitchen knife
```

### カット05 「五歳の回想」　`1:03` 〜　14秒 / 3行

> **ト書き(台本):** カウンターの端。日替わり定食を食べる老人。五歳の結衣が隅で泣いている(回想)。
>
> **メモ:** 回想なのでセピア寄り。老人は目を合わせていない

**ファイル名 `images/cut05.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, warm sepia-toned memory scene, a small girl about five years old crying at the end of a diner counter, an elderly man in a grey jacket holding out a wrapped candy to her without looking at her
```

### カット06 「白い手袋」　`1:17` 〜　9秒 / 2行

> **ト書き(台本):** 結衣の部屋。引き出しに、箱に入った白い手袋をしまう。
>
> **メモ:** 手元のみ。手袋は畳まれて箱の中

**ファイル名 `images/cut06.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a young woman's hands placing a boxed pair of white formal gloves into a wooden drawer, evening light from a window
```

### カット07 「とん汁」　`1:26` 〜　11秒 / 2行

> **ト書き(台本):** (なし)
>
> **メモ:** 涼介の善良だった頃。表情は本物の感動

**ファイル名 `images/cut07.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a young businessman in a navy suit at a diner counter, both hands around a bowl of pork miso soup, eyes closed, genuinely moved
```

### カット08 「病院の廊下」　`1:38` 〜　16秒 / 4行

> **ト書き(台本):** 病院の廊下。長椅子で眠る涼介。スーツのまま、三日目。
>
> **メモ:** 涼介の善良さの証拠。この絵が後半で効く

**ファイル名 `images/cut08.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a young man in a wrinkled suit asleep sitting upright on a hospital corridor bench at night, fluorescent light, an old man in pajamas standing in a doorway watching him
```

### カット09 「常務が口ぐせ」　`1:54` 〜　12秒 / 3行

> **ト書き(台本):** (なし)
>
> **メモ:** 同じ人物が変わったことを、同じ服・違う目で見せる

**ファイル名 `images/cut09.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a young businessman in a suit checking his phone on a station platform, expression gone cold, city lights bokeh
```


## 【2:05-6:35】加害①②③④

### カット10 「握られなかった手」　`2:06` 〜　44秒 / 11行

> **ト書き(台本):** 高級料亭。父は17年前のスーツ。差し出された手が宙に浮く。
>
> **メモ:** **構図を必ず覚えておく。転落パートで同じ構図・同じ角度を使う。** 手が宙に浮いた瞬間

**ファイル名 `images/cut10.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a formal tatami room in an expensive ryotei, an old man in an ill-fitting charcoal suit bowing slightly with his weathered hand extended forward, an older woman in a pale kimono seated upright, hands folded in her lap, not taking his hand, the extended hand hanging in empty air
```

**追加 `images/cut10a.png`**(この場面は44秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, the same ryotei room from the old man's side, his own weathered hand in the foreground still extended, the seated woman small and distant
```

### カット11 「帰りの電車」　`2:50` 〜　53秒 / 17行

> **ト書き(台本):** 帰りの電車。窓に映る父。自分の手をこすっている。
>
> **メモ:** 父の背中と窓の反射。会話は見せない

**ファイル名 `images/cut11.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, night train interior, an old man in a suit seated by the window, his own reflection in the dark glass, rubbing the back of one hand with the other thumb, a young woman seated beside him looking at his hands
```

**追加 `images/cut11a.png`**(この場面は53秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an old man's hand rubbing his own knuckles on his lap, train window light moving across it
```

### カット12 「母の指輪」　`3:43` 〜　24秒 / 8行

> **ト書き(台本):** みやこ食堂。閉店後のカウンター。父と結衣。
>
> **メモ:** 指輪は質素に。三十五年前のもの

**ファイル名 `images/cut12.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a thin worn gold ring with one small stone, held between an old man's fingers and a young woman's fingers, over a diner counter after closing
```

### カット13 「廊下のささやき」　`4:07` 〜　57秒 / 16行

> **ト書き(台本):** 式場の廊下。義母が涼介に、結衣に聞こえる声で。
>
> **メモ:** 聞こえる距離。結衣は背中

**ファイル名 `images/cut13.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, hotel corridor, an older woman in a kimono speaking quietly to a young man in a suit, a young woman standing further down the corridor within earshot, back turned
```

**追加 `images/cut13a.png`**(この場面は57秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an older woman's face in profile, speaking, faint satisfied smile
```

### カット14 「振込明細」　`5:04` 〜　23秒 / 7行

> **ト書き(台本):** みやこ食堂のカウンター。父が銀行で受け取った振込明細を、黙って置く。
>
> **メモ:** 紙の文字は書かない。形と余白だけ

**ファイル名 `images/cut14.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a bank transfer receipt slip placed face-up on a diner counter, an old man's weathered hand withdrawing from it, a young woman's hand reaching toward it
```

### カット15 「招待状の束」　`5:27` 〜　66秒 / 19行

> **ト書き(台本):** 式場の打ち合わせ室。印刷済みの招待状の束。
>
> **メモ:** 三人の視線が全部バラバラなのが要点

**ファイル名 `images/cut15.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a bridal planning room, a stack of printed wedding invitations on a table, an older woman in a twin-set pushing them forward with two fingers, a young woman looking down at them, a young man beside her looking at his phone
```

**追加 `images/cut15a.png`**(この場面は66秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a young man's face lit from below by a phone screen, not looking up
```


## 【6:35-7:15】越えてはいけない一線

### カット16 「手術のあと」　`6:33` 〜　21秒 / 5行

> **ト書き(台本):** (なし)
>
> **メモ:** 八時間の心臓手術の三週間前

**ファイル名 `images/cut16.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a hospital room, an old man just waking from anesthesia, oxygen tube, a young woman at the bedside holding the rail, morning light
```

### カット17 「鼻で笑う」　`6:54` 〜　18秒 / 7行

> **ト書き(台本):** (なし)
>
> **メモ:** 涼介の転落点。小さく、鼻で

**ファイル名 `images/cut17.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a young man's face, a small dismissive laugh through the nose, eyes not smiling, blurred older woman behind him
```


## 【7:15-8:05】受諾 + 伏線

### カット18 「受諾」　`7:13` 〜　51秒 / 17行

> **ト書き(台本):** 結衣の表情。悲しんでいない。うっすら笑っている。
>
> **メモ:** **泣かせない。** ここから披露宴まで、この顔を崩さない

**ファイル名 `images/cut18.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, medium close-up of a young woman, expression calm, the faintest smile, not sad, not angry, hotel meeting room background out of focus
```

**追加 `images/cut18a.png`**(この場面は51秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a young woman's eyes, calm, a single unshed brightness, no tears
```


## 【8:05-10:35】準備

### カット19 「プランナー」　`8:03` 〜　24秒 / 6行

> **ト書き(台本):** (なし)
>
> **メモ:** プランナーはためらっている

**ファイル名 `images/cut19.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a wedding planner in a navy uniform suit at a counter, holding a clipboard, hesitating, a young woman facing her
```

### カット20 「駅までの道」　`8:27` 〜　19秒 / 4行

> **ト書き(台本):** (なし)
>
> **メモ:** 二人の距離が主題

**ファイル名 `images/cut20.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, evening street, a young couple walking apart from each other, the man half-turned back speaking, the woman looking ahead
```

### カット21 「パンフレットの父」　`8:47` 〜　50秒 / 15行

> **ト書き(台本):** 実家のリビング。父が式場のパンフレットを眺めている。
>
> **メモ:** **母の写真をここで置く。顔は映さない**(写真立ての背または逆光)

**ファイル名 `images/cut21.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a living room in an old house, an old man in a cardigan seated at a low table looking at a glossy wedding-venue brochure, a framed photograph of a woman beside him, a young woman standing in the doorway
```

**追加 `images/cut21a.png`**(この場面は50秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an old man's hands quietly closing a glossy brochure
```

### カット22 「鷹野の家の門」　`9:37` 〜　6秒 / 1行

> **ト書き(台本):** 夜道。木造の古い家。門の前。招待状を一枚握った手。
>
> **メモ:** 門の前。人物は手だけ

**ファイル名 `images/cut22.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, night, the gate of an old wooden Japanese house, a young woman's hand gripping a single envelope, warm light from inside
```

### カット23 「鷹野との約束」　`9:42` 〜　29秒 / 11行

> **ト書き(台本):** (なし)
>
> **メモ:** 老人が長いこと見ている

**ファイル名 `images/cut23.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, interior of an old Japanese house, an elderly man with swept-back white hair seated formally, looking steadily at a young woman seated across from him, a single envelope on the tatami between them
```

### カット24 「会長だと明かす」　`10:11` 〜　22秒 / 5行

> **ト書き(台本):** (なし)
>
> **メモ:** 正体を見せるカット。威厳を出す

**ファイル名 `images/cut24.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a magazine-cover style portrait of an elderly Japanese man in a dark navy suit, white hair, sharp deep-set eyes, arms folded, corporate office background
```


## 【10:35-17:05】反転

### カット25 「空席の親族席」　`10:34` 〜　12秒 / 4行

> **ト書き(台本):** 都心のホテル、大宴会場。新婦側の親族席だけが空席。
>
> **メモ:** 空席だけが浮いて見える構図

**ファイル名 `images/cut25.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a grand hotel banquet hall filled with 120 guests, one table of empty chairs conspicuously untouched at the front left, chandeliers
```

### カット26 「お守り」　`10:46` 〜　14秒 / 4行

> **ト書き(台本):** (なし)
>
> **メモ:** 介添えに預けたバッグ。開けていない

**ファイル名 `images/cut26.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a small clutch bag on a bridal seat, two folded documents just visible inside
```

### カット27 「マウント」　`11:00` 〜　16秒 / 4行

> **ト書き(台本):** (なし)
>
> **メモ:** 義母の得意の絶頂

**ファイル名 `images/cut27.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, an older woman in a black kurotomesode kimono speaking to seated guests, one hand raised elegantly, guests smiling politely
```

### カット28 「常務に」　`11:16` 〜　15秒 / 4行

> **ト書き(台本):** (なし)
>
> **メモ:** 黒田は困っている

**ファイル名 `images/cut28.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, the same older woman leaning toward a middle-aged man in a grey suit at the head table, confiding, the man looking uncomfortable
```

### カット29 「ロビーの一時間」　`11:30` 〜　43秒 / 10行

> **ト書き(台本):** (なし)
>
> **メモ:** 動かない八十二歳。ここが反転のエンジン

**ファイル名 `images/cut29.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a hotel lobby, an elderly man in a dark navy suit sitting alone upright on a chair, a single envelope resting on his knees, doors to the banquet hall closed behind him
```

**追加 `images/cut29a.png`**(この場面は43秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an elderly man's hands resting on a single envelope on his knees, a hotel clock on the wall behind
```

### カット30 「扉が開く」　`12:13` 〜　45秒 / 13行

> **ト書き(台本):** (なし)
>
> **メモ:** 黒田がグラスを落とす瞬間

**ファイル名 `images/cut30.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** the banquet hall doors opening, a hotel manager in black tailcoat and white gloves escorting an elderly man in a dark navy suit inside, guests turning, a man in a grey suit dropping a glass
```

**追加 `images/cut30a.png`**(この場面は45秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an older woman's face as recognition hits, all color gone
```

### カット31 「席を譲る」　`12:58` 〜　18秒 / 5行

> **ト書き(台本):** (なし)
>
> **メモ:** 格の逆転を絵にする

**ファイル名 `images/cut31.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a middle-aged man in a grey suit standing up and gesturing to his own seat at the head table, an elderly man in a navy suit standing beside him, the hall watching
```

### カット32 「祝辞」　`13:16` 〜　65秒 / 19行

> **ト書き(台本):** (なし)
>
> **メモ:** **末広は開かせない。** 帯に挿したまま握る

**ファイル名 `images/cut32.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** an elderly man in a dark navy suit standing with a microphone at the head table, speaking quietly, 120 guests listening, an older woman in black kimono clutching a folded fan tucked in her obi
```

**追加 `images/cut32a.png`**(この場面は65秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of an elderly man's face speaking, eyes down, remembering
```

### カット33 「マイクを取る」　`14:21` 〜　51秒 / 14行

> **ト書き(台本):** (なし)
>
> **メモ:** 結衣は怒っていない。冷えている

**ファイル名 `images/cut33.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a bride in a colored formal gown standing and taking the microphone, face completely calm, the hall silent, an older woman in black kimono half-risen in panic
```

**追加 `images/cut33a.png`**(この場面は51秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, reverse shot from behind the bride toward 120 guests, all faces turned to her
```

### カット34 「窓口係」　`15:12` 〜　29秒 / 7行

> **ト書き(台本):** (なし)
>
> **メモ:** 義母が初めて本音を出す直前

**ファイル名 `images/cut34.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, an older woman in black kimono, mouth slightly open, all composure gone, another woman in a formal kimono beside her having just spoken, guests staring
```

### カット35 「指輪をはめる」　`15:42` 〜　25秒 / 8行

> **ト書き(台本):** (なし)
>
> **メモ:** 右手。婚約指輪ではないという宣言

**ファイル名 `images/cut35.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a bride's right hand sliding a thin old gold ring onto her own finger, the hall blurred behind
```

### カット36 「扇子が落ちる」　`16:07` 〜　36秒 / 9行

> **ト書き(台本):** (なし)
>
> **メモ:** 拾う人がいないことが要点。上から見た構図

**ファイル名 `images/cut36.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a folded Japanese fan slipping from an obi and lying on a banquet hall carpet, a black kimono hem beside it, nobody reaching for it
```

### カット37 「退場」　`16:43` 〜　20秒 / 7行

> **ト書き(台本):** (なし)
>
> **メモ:** 振り返らない

**ファイル名 `images/cut37.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a bride walking alone toward the banquet hall doors, back to camera, chin level, a young man in formal wear half-reaching after her
```


## 【17:05-18:15】転落

### カット38 「宙に浮いた手」　`17:03` 〜　22秒 / 4行

> **ト書き(台本):** 宴会場。主賓席の前。政子の差し出した手が宙に浮く。料亭(加害①)と同じ構図・同じ角度で、手の主だけを入れ替える。
>
> **メモ:** **カット10と同じ構図・同じ角度・手の主だけ入れ替える。** これが台本の円を閉じる絵

**ファイル名 `images/cut38.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY — 加害①の鏡** a banquet hall, an older woman in black kimono having rushed forward with her hand extended, an elderly man in a navy suit looking at the offered hand without taking it, bowing once, the hand hanging in empty air, guests watching
```

### カット39 「転落」　`17:25` 〜　46秒 / 11行

> **ト書き(台本):** (なし)
>
> **メモ:** 契約打ち切りと九州行き。2枚に割ってもよい

**ファイル名 `images/cut39.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a corporate meeting room, three executives bowing deeply to an empty chair-side, grey atmosphere / a young man packing a desk box
```

**追加 `images/cut39a.png`**(この場面は46秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a small regional train platform, a young man alone with a suitcase, four relatives seeing him off
```

### カット40 「鳴り続ける電話」　`18:11` 〜　6秒 / 2行

> **ト書き(台本):** 神崎の家。玄関の磨りガラス越しに、衣紋掛けの黒留袖。鳴り続ける電話。
>
> **メモ:** **義母の顔は出さない。** 磨りガラス越しのシルエットだけ

**ファイル名 `images/cut40.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** the entrance of a house seen through frosted glass, the silhouette of a black formal kimono hanging on a garment rack, a telephone on a stand, nobody coming
```


## 【18:15-20:40】締め

### カット41 「水曜の昼」　`18:16` 〜　33秒 / 10行

> **ト書き(台本):** みやこ食堂。のれん。カウンター。父の荒れた手のアップ。
>
> **メモ:** 二人の四十年が見える距離感

**ファイル名 `images/cut41.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, the diner, an elderly man in a grey jacket ducking under the noren curtain, the old cook behind the counter looking up, warm daylight
```

### カット42 「臨時休業」　`18:49` 〜　21秒 / 7行

> **ト書き(台本):** みやこ食堂の厨房の壁。古い予定表。披露宴の日付に「臨時休業」の文字。
>
> **メモ:** 文字は書かない。書くなら墨で二文字のみ、崩して読めなくてよい

**ファイル名 `images/cut42.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** close-up of an old paper schedule sheet pinned to a kitchen wall, one square marked with two handwritten characters, kitchen out of focus behind
```

### カット43 「玄関の袋」　`19:10` 〜　15秒 / 4行

> **ト書き(台本):** 実家の玄関。たたんだままのモーニングの袋。その横に写真立て。母の顔は映さない。写真立ての背と、父の手だけ。
>
> **メモ:** **母の顔は絶対に映さない。** 写真立ての背だけ

**ファイル名 `images/cut43.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY** a house entryway, a folded morning-coat rental bag left on the floor, a photo frame standing beside it turned away from the viewer, only its back and stand visible
```

### カット44 「厨房に立つ」　`19:25` 〜　44秒 / 12行

> **ト書き(台本):** みやこ食堂の厨房。結衣が白衣で立っている。父がカウンター側から見ている。
>
> **メモ:** 立ち位置が入れ替わっている

**ファイル名 `images/cut44.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, a young woman in a white chef coat standing behind the diner counter, an old man watching from the customer side, steam, warm light
```

**追加 `images/cut44a.png`**(この場面は44秒あるので2枚目を推奨)

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, close-up of a bowl of pork miso soup set down on a counter, a man's hands receiving it
```

### カット45 「白い手袋をはめる」　`20:09` 〜　16秒 / 6行

> **ト書き(台本):** 閉店後の店の前。のれんの下。結衣が父の手に白い手袋をはめる。
>
> **メモ:** **エンドカード候補。** 手だけ。顔は入れない

**ファイル名 `images/cut45.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, **KEY — ラスト** close-up under a noren curtain at night, a young woman sliding a white formal glove onto an old man's weathered hand
```

### カット46 「エンド」　`20:25` 〜　12秒 / 2行

> **ト書き(台本):** (なし)
>
> **メモ:** CTAとチャンネル名を乗せる下地。中央を空ける

**ファイル名 `images/cut46.png`**

```
Japanese manga illustration for a narrated story video, cel shading, clean bold ink outlines, muted desaturated palette, soft cinematic key light, 16:9 widescreen, no text, no speech bubbles, the diner noren curtain at night from outside, warm light inside, empty street
```


---

**必須 46枚 / 推奨を含めて 58枚。総尺 20:37。**

## 共通ネガティブプロンプト

```
text, letters, kanji, hiragana, captions, speech bubbles, watermark, signature, logo, extra fingers, malformed hands, blurry, lowres, 3d render, photo, western cartoon, chibi, oversaturated
```
