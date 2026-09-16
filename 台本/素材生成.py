#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「沖縄旅行の注意点」の画素材を書き出す。

  python3 台本/素材生成.py

出力先: 台本/素材/
  サムネ/     … サムネイル3案(完成見本 + 文字だけの透過PNG)
  図解/       … 編集で作るのが面倒な図6点(1920x1080 透過)
  テロップ/   … 章ごとのテロップ(1920x1080 透過)

文字を直したいときは、このファイルの下の方のデータを書き換えて実行し直す。
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "素材")
FONT_PATH = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"

W, H = 1920, 1080          # テロップ・図解
TW, TH = 1280, 720         # サムネイル

# 色
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
YELLOW = (255, 221, 51, 255)
RED = (232, 62, 60, 255)
BLUE = (28, 104, 176, 255)
TEAL = (0, 150, 150, 255)
NAVY = (12, 34, 62, 255)
GRAY = (140, 148, 158, 255)
GREEN = (44, 160, 90, 255)


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def tsize(draw, text, f):
    b = draw.textbbox((0, 0), text, font=f)
    return b[2] - b[0], b[3] - b[1]


def fit(draw, text, max_w, start=200, min_size=20):
    """max_w に収まる最大のフォントサイズを返す。"""
    s = start
    while s > min_size:
        f = font(s)
        if tsize(draw, text, f)[0] <= max_w:
            return f
        s -= 2
    return font(min_size)


def bold(draw, xy, text, f, fill=WHITE, outline=BLACK, ow=8, bw=3, anchor="la"):
    """太らせた文字 + フチ。IPAゴシックは細いので、重ね描きで太くする。"""
    x, y = xy
    if outline and ow:
        for dx in range(-ow, ow + 1, 2):
            for dy in range(-ow, ow + 1, 2):
                if dx * dx + dy * dy <= ow * ow:
                    draw.text((x + dx, y + dy), text, font=f, fill=outline, anchor=anchor)
    for dx in range(-bw, bw + 1):
        for dy in range(-bw, bw + 1):
            draw.text((x + dx, y + dy), text, font=f, fill=fill, anchor=anchor)


def plain(draw, xy, text, f, fill=WHITE, anchor="la"):
    draw.text(xy, text, font=f, fill=fill, anchor=anchor)


def gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.point((0, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img.resize((w, h)).convert("RGBA")


def save(img, folder, name):
    p = os.path.join(OUT, folder)
    os.makedirs(p, exist_ok=True)
    fp = os.path.join(p, name)
    img.save(fp)
    return fp


def new_t():
    """テロップ用。透過。映像の上に乗せる。"""
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def new_fig():
    """図解用。全画面グラフィックなので背景を持たせる。
    どんな映像の上に置いても読めるようにするため。"""
    return gradient((W, H), (10, 26, 50), (18, 52, 86))


def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


# ══════════════════════════════════════════════ サムネイル

THUMBS = [
    ("A", "沖縄県民が本音", "観光客がやりがちな失敗", (8, 60, 110), (0, 120, 130)),
    ("B", "知らずに来ると損", "沖縄の落とし穴", (60, 20, 30), (150, 60, 30)),
    ("C", "県民はヒヤヒヤしてます", "沖縄旅行の注意点", (14, 30, 66), (20, 90, 140)),
]


def thumb_text_layer(main, sub, num="15"):
    """文字だけの透過レイヤー。お二人の写真に重ねて使う。"""
    img = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    f = fit(d, main, TW - 90, start=150)
    bold(d, (TW // 2, 96), main, f, fill=YELLOW, ow=11, bw=4, anchor="ma")

    # 下の帯
    bh = 132
    band = Image.new("RGBA", (TW, bh), (0, 0, 0, 195))
    img.alpha_composite(band, (0, TH - bh))
    d = ImageDraw.Draw(img)

    f2 = fit(d, sub, TW - 330, start=92)
    bold(d, (46, TH - bh // 2), sub, f2, fill=WHITE, ow=6, bw=3, anchor="lm")

    # 数字を特大で右下に
    fn = font(190)
    bold(d, (TW - 40, TH - bh // 2 - 8), num, fn, fill=RED, ow=12, bw=5, anchor="rm")
    return img


def build_thumbs():
    for key, main, sub, c1, c2 in THUMBS:
        bg = gradient((TW, TH), c1, c2)
        d = ImageDraw.Draw(bg)
        # 写真を入れる場所のガイド
        d.rectangle([0, 150, TW, TH - 150], outline=(255, 255, 255, 60), width=3)
        f = font(30)
        plain(d, (TW // 2, TH // 2 - 20), "ここに沖縄の写真を入れてください", f,
              fill=(255, 255, 255, 120), anchor="mm")
        plain(d, (TW // 2, TH // 2 + 26), "(海・国際通り・夕方の渋滞など)", font(24),
              fill=(255, 255, 255, 90), anchor="mm")
        # お二人の位置
        d.ellipse([TW - 300, TH - 330, TW - 130, TH - 160], outline=(255, 255, 255, 90), width=3)
        plain(d, (TW - 215, TH - 245), "お二人", font(24), fill=(255, 255, 255, 110), anchor="mm")

        layer = thumb_text_layer(main, sub)
        bg.alpha_composite(layer)
        save(bg.convert("RGB"), "サムネ", "サムネ%s_完成見本.png" % key)
        save(layer, "サムネ", "サムネ%s_文字だけ.png" % key)
    print("サムネ  3案 × 2種類")


# ══════════════════════════════════════════════ 図解

def fig_hotel():
    """03 ホテル: 観光地は北と中部にある"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 58), "観光地は、北と中部にあります", font(78), fill=WHITE, ow=8, anchor="ma")

    zones = [("北 部", 200, GREEN, ["美ら海水族館", "古宇利島", "やんばる"]),
             ("中 部", 430, TEAL, ["アメリカンビレッジ", "残波岬"]),
             ("南部・那覇", 660, BLUE, ["国際通り", "首里城", "空港"])]
    for name, y, col, spots in zones:
        rounded(d, [180, y, 1740, y + 190], 22, col[:3] + (60,))
        d.rectangle([180, y, 196, y + 190], fill=col)
        bold(d, (230, y + 44), name, font(62), fill=WHITE, ow=6)
        for i, s in enumerate(spots):
            x = 560 + (i % 3) * 400
            rounded(d, [x, y + 52, x + 360, y + 134], 16, (255, 255, 255, 230))
            plain(d, (x + 180, y + 93), s, fit(d, s, 320, start=44), fill=NAVY, anchor="mm")

    rounded(d, [180, 890, 1740, 1010], 20, (232, 62, 60, 230))
    bold(d, (W // 2, 950), "那覇に泊まると、毎日ここを往復することになります",
         font(60), fill=WHITE, ow=5, anchor="mm")
    save(img, "図解", "01_ホテルは北と中部に.png")


def fig_distance():
    """09 距離感: 那覇→美ら海"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 60), "那覇 → 美ら海水族館", font(84), fill=WHITE, ow=8, anchor="ma")

    y = 330
    d.line([260, y, 1660, y], fill=(255, 255, 255, 90), width=10)
    for x, label in [(260, "那覇"), (1660, "美ら海")]:
        d.ellipse([x - 26, y - 26, x + 26, y + 26], fill=YELLOW)
        bold(d, (x, y + 52), label, font(52), fill=WHITE, ow=5, anchor="ma")

    rounded(d, [640, y - 108, 1280, y - 24], 18, (232, 62, 60, 235))
    bold(d, (960, y - 66), "片道 約2時間", font(62), fill=WHITE, ow=4, anchor="mm")

    bars = [("往復すると", "4時間", RED), ("東京→那覇のフライト", "約2時間30分", GRAY)]
    for i, (t, v, col) in enumerate(bars):
        by = 560 + i * 150
        plain(d, (260, by), t, font(50), fill=(255, 255, 255, 220))
        rounded(d, [880, by - 14, 880 + (700 if i == 0 else 440), by + 76], 16, col)
        bold(d, (900, by + 30), v, font(58), fill=WHITE, ow=4, anchor="lm")

    rounded(d, [260, 880, 1660, 1000], 20, (44, 160, 90, 235))
    bold(d, (W // 2, 940), "だから、その日は「北部の日」にしてください",
         font(62), fill=WHITE, ow=5, anchor="mm")
    save(img, "図解", "02_那覇から美ら海の距離感.png")


def fig_traffic():
    """07 渋滞の時間割"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 56), "沖縄の渋滞には、時間割があります", font(80), fill=WHITE, ow=8, anchor="ma")

    x0, x1, y = 200, 1760, 430
    span = x1 - x0
    def px(hour):
        return x0 + span * (hour - 5) / 17.0     # 5時〜22時

    # 一日の帯(空いている時間)
    rounded(d, [x0, y, x1, y + 110], 14, (78, 120, 160, 255))
    # 渋滞の時間。ラベルは帯の上に出す(帯の中に入れると幅が足りない)
    for a, b, label in [(7.5, 9, "朝の渋滞"), (17, 20, "夕方の渋滞")]:
        d.rectangle([px(a), y, px(b), y + 110], fill=RED)
        cx = (px(a) + px(b)) / 2
        bold(d, (cx, y - 82), label, font(54), fill=RED, ow=6, anchor="ma")
        d.line([cx, y - 16, cx, y], fill=RED, width=5)

    for hour in range(5, 23, 2):
        d.line([px(hour), y + 110, px(hour), y + 134], fill=(255, 255, 255, 150), width=3)
        plain(d, (px(hour), y + 146), "%d時" % hour, font(36), fill=(255, 255, 255, 210), anchor="ma")

    rows = [("朝", " 7:30 〜  9:00", "那覇へ向かう方向"),
            ("夕", "17:00 〜 20:00", "那覇から北へ向かう方向")]
    for i, (head, t, dest) in enumerate(rows):
        ry = 650 + i * 104
        bold(d, (240, ry), head, font(58), fill=WHITE, ow=5)
        bold(d, (330, ry), t, font(58), fill=YELLOW, ow=5)
        plain(d, (800, ry + 8), dest, font(48), fill=(255, 255, 255, 235))

    rounded(d, [200, 860, 1760, 1000], 20, (44, 160, 90, 235))
    bold(d, (W // 2, 930), "対策は「ずらす」だけ。朝は9時過ぎ、夕方は20時ごろ動く",
         font(58), fill=WHITE, ow=5, anchor="mm")
    save(img, "図解", "03_渋滞の時間割.png")


def fig_rentacar():
    """05 営業所は場所で選ぶ"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 56), "レンタカーの営業所は「場所」で選ぶ", font(76), fill=WHITE, ow=8, anchor="ma")

    cx, cy = W // 2, 470
    d.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=YELLOW)
    bold(d, (cx, cy), "空港", font(56), fill=NAVY, ow=0, bw=2, anchor="mm")
    bold(d, (cx, 250), "▲ 北", font(52), fill=(255, 255, 255, 200), ow=4, anchor="ma")
    bold(d, (cx, 660), "▼ 南", font(52), fill=(255, 255, 255, 200), ow=4, anchor="ma")

    cards = [
        (150, "泊まるのが 空港より北", "那覇市内・おもろまち・北部", "→ 北側の営業所", TEAL),
        (1030, "泊まるのが 空港より南", "豊見城・糸満", "→ 空港の近くの営業所", BLUE),
    ]
    for x, t1, t2, t3, col in cards:
        rounded(d, [x, 760, x + 740, 1010], 22, col[:3] + (70,))
        d.rectangle([x, 760, x + 14, 1010], fill=col)
        bold(d, (x + 44, 790), t1, font(50), fill=WHITE, ow=5)
        plain(d, (x + 44, 858), t2, font(40), fill=(255, 255, 255, 200))
        bold(d, (x + 44, 930), t3, font(52), fill=YELLOW, ow=5)

    plain(d, (W // 2, 700), "借りてすぐ、逆方向に走らないために", font(44),
          fill=(255, 255, 255, 210), anchor="ma")
    save(img, "図解", "04_レンタカー営業所の選び方.png")


def fig_ynumber():
    """08 Yナンバー事故の流れ"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 56), "Yナンバーの車と事故になったら", font(78), fill=WHITE, ow=8, anchor="ma")

    steps = [("1", "日本の警察を呼ぶ", "ここは普通と同じ", BLUE),
             ("2", "米軍の憲兵と通訳が来る", "着くまで時間がかかる", RED),
             ("3", "同じことを2回聞かれる", "日本側と、米軍側と", RED)]
    for i, (n, t1, t2, col) in enumerate(steps):
        x = 130 + i * 570
        rounded(d, [x, 260, x + 520, 620], 24, col[:3] + (70,))
        d.ellipse([x + 40, 300, x + 132, 392], fill=col)
        bold(d, (x + 86, 346), n, font(62), fill=WHITE, ow=0, bw=2, anchor="mm")
        f = fit(d, t1, 440, start=50)
        bold(d, (x + 40, 430), t1, f, fill=WHITE, ow=5)
        plain(d, (x + 40, 512), t2, font(36), fill=(255, 255, 255, 200))
        if i < 2:
            bold(d, (x + 540, 440), "▶", font(56), fill=(255, 255, 255, 170), ow=3)

    rounded(d, [130, 690, 1790, 800], 20, (232, 62, 60, 235))
    bold(d, (W // 2, 745), "その日の予定は、まず飛びます", font(64), fill=WHITE, ow=5, anchor="mm")

    rounded(d, [130, 850, 1790, 1010], 22, (44, 160, 90, 235))
    bold(d, (W // 2, 900), "当てられたら", font(46), fill=(255, 255, 255, 230), ow=4, anchor="ma")
    bold(d, (W // 2, 960), "警察を呼ぶ ／ ナンバーを控える ／ 写真を撮る ／ レンタカー会社へ",
         font(48), fill=WHITE, ow=5, anchor="ma")
    save(img, "図解", "05_Yナンバー事故の流れ.png")


def fig_rip():
    """10 離岸流。上が沖、下が岸。"""
    img = new_fig()
    d = ImageDraw.Draw(img)
    bold(d, (W // 2, 24), "白波が立っていない場所が、危ない", font(72), fill=WHITE, ow=8, anchor="ma")

    SEA_T, SEA_B, SAND_B = 250, 830, 910
    CH_L, CH_R = 770, 1150                      # 離岸流の通り道

    # 見出し3つ(海の上に置く。波と重ねない)
    for x0, x1, t1, t2, col in [
        (130, 740, "白波が立っている", "比較的、安全", (44, 160, 90, 235)),
        (CH_L, CH_R, "波が立っていない", "離岸流", (232, 62, 60, 240)),
        (1180, 1790, "白波が立っている", "比較的、安全", (44, 160, 90, 235))]:
        rounded(d, [x0, 126, x1, 250], 16, col)
        cx = (x0 + x1) / 2
        plain(d, (cx, 134), t1, fit(d, t1, x1 - x0 - 40, start=38), fill=(255, 255, 255, 240), anchor="ma")
        bold(d, (cx, 182), t2, fit(d, t2, x1 - x0 - 44, start=54), fill=WHITE, ow=4, anchor="ma")

    # 海 → 砂浜
    d.rectangle([130, SEA_T, 1790, SEA_B], fill=(28, 96, 150, 205))
    rounded(d, [130, SEA_B - 20, 1790, SAND_B], 18, (226, 210, 168, 245))
    d.rectangle([130, SEA_B - 20, 1790, SEA_B + 10], fill=(226, 210, 168, 245))
    plain(d, (168, SEA_B + 22), "岸(砂浜)", font(42), fill=(96, 74, 42, 255))
    plain(d, (1756, SEA_T + 16), "沖", font(42), fill=(255, 255, 255, 190), anchor="ra")

    # 白波(安全な側)。離岸流の通り道には描かない
    for row in range(5):
        yy = SEA_T + 62 + row * 108
        for x in list(range(150, CH_L - 60, 64)) + list(range(CH_R + 20, 1772, 64)):
            d.arc([x, yy, x + 64, yy + 48], 200, 340, fill=(255, 255, 255, 230), width=9)

    # 離岸流の通り道(波が消える)
    d.rectangle([CH_L, SEA_T, CH_R, SEA_B - 20], fill=(16, 62, 104, 235))
    # 沖へ向かう矢印(海の中だけに収める)
    mid = (CH_L + CH_R) // 2
    d.line([mid, SEA_B - 120, mid, SEA_T + 96], fill=(232, 62, 60, 255), width=16)
    d.polygon([(mid, SEA_T + 46), (mid - 38, SEA_T + 112), (mid + 38, SEA_T + 112)],
              fill=(232, 62, 60, 255))
    bold(d, (mid, SEA_B - 104), "沖へ流される", font(40), fill=(255, 220, 220, 255), ow=4, anchor="ma")

    # 横に泳いで抜ける
    ay = SEA_T + 400
    d.line([mid + 30, ay, 1430, ay], fill=YELLOW, width=16)
    d.polygon([(1480, ay), (1424, ay - 32), (1424, ay + 32)], fill=YELLOW)
    rounded(d, [1180, ay - 118, 1700, ay - 44], 14, (0, 0, 0, 170))
    bold(d, (1440, ay - 106), "流されたら、横に泳ぐ", font(50), fill=YELLOW, ow=5, anchor="ma")

    rounded(d, [130, 950, 1790, 1058], 20, (232, 62, 60, 240))
    bold(d, (W // 2, 1004), "岸に向かって真っすぐ泳がないでください。流れに勝てません",
         font(54), fill=WHITE, ow=5, anchor="mm")
    save(img, "図解", "06_離岸流の見分け方.png")


# ══════════════════════════════════════════════ テロップ

# (章番号, ファイル名, 種類, 文字)  種類: big=全画面 / band=上帯 / sub=下部
TELOPS = [
    ("01", "沖縄県民の夫婦が、本音で", "band"),
    ("03", "観光客の動き = 県民の通勤の動き", "band"),
    ("03", "初日 那覇 ／ 中日 北部・中部 ／ 最終日 空港の近く", "big"),
    ("03", "高速をケチると、1時間損します", "sub"),
    ("04", "那覇の中は、ゆいレールとバスで足ります", "band"),
    ("04", "バスは、遅れます(10〜20分は普通)", "sub"),
    ("05", "こすっただけで、数万円", "big"),
    ("05", "免責補償 ＋ NOC ＋ レッカー", "big"),
    ("05", "名前で選ばない。場所で選ぶ", "big"),
    ("05", "返却は満タン。北へ行くなら名護で給油", "sub"),
    ("06", "沖縄自動車道 = 80km/h", "big"),
    ("06", "左ミラー。発進前と、左折前", "big"),
    ("06", "脇道に車が見えたら、ゆるめる", "sub"),
    ("06", "雨 ＋ 朝夕 = 線が消える", "sub"),
    ("06", "バスレーン。迷ったら、右の車線", "big"),
    ("06", "時間で、車線の向きが変わる", "sub"),
    ("07", "ずらす。それだけ", "big"),
    ("07", "最終日 = 空港の近く", "big"),
    ("08", "Y / A / E = 米軍関係者の車", "band"),
    ("08", "ぶつからないこと。それが一番の対策", "sub"),
    ("09", "那覇 → 美ら海水族館　片道 約2時間", "big"),
    ("09", "その日を「北部の日」にする", "big"),
    ("10", "白波が立っていない場所が、危ない", "big"),
    ("10", "流されたら、岸じゃなく、横", "big"),
    ("10", "ネットの中で泳いでください", "sub"),
    ("10", "素足で岩場を歩かない", "sub"),
    ("10", "旧盆は、海に入らない", "sub"),
    ("11", "砂・サンゴ・星の砂", "big"),
    ("11", "星の砂は、お店で買えます", "sub"),
    ("12", "草むらに入らない。それだけ", "sub"),
    ("12", "御嶽(うたき)", "big"),
    ("12", "香炉・並んだ石・しめ縄 → 引き返す", "big"),
    ("13", "紫外線は、本土の2〜3倍", "band"),
    ("13", "①塗り直す ②曇りこそ注意 ③長袖を1枚", "big"),
    ("14", "カタブイ = 片方だけ降る雨", "band"),
    ("14", "カタブイの後は、虹", "big"),
    ("14", "台風は「来る前」に決める", "big"),
    ("14", "欠航後の振替は、数百人〜数千人待ち", "sub"),
    ("15", "同じものが、スーパーだと安い", "big"),
    ("15", "安さ→スーパー ／ 種類→空港 ／ 食べる→国際通り", "sub"),
    ("15", "17時以降、チャージ料のお店あり", "sub"),
    ("15", "コーレーグースは、数滴", "big"),
    ("16", "旧盆 = 旧暦。毎年、日付が変わる", "band"),
    ("17", "ハブには、まず会いません", "sub"),
    ("17", "治安は、いいです", "sub"),
    ("17", "困ったら、聞いてください", "sub"),
    ("17", "15個、全部 — 知っていれば防げること", "big"),
]


def telop(text, kind):
    img = new_t()
    d = ImageDraw.Draw(img)
    if kind == "big":
        f = fit(d, text, W - 200, start=130)
        bold(d, (W // 2, H // 2), text, f, fill=WHITE, ow=10, bw=4, anchor="mm")
    elif kind == "band":
        bh = 190
        band = Image.new("RGBA", (W, bh), (12, 34, 62, 225))
        img.alpha_composite(band, (0, 70))
        d = ImageDraw.Draw(img)
        f = fit(d, text, W - 180, start=110)
        bold(d, (W // 2, 70 + bh // 2), text, f, fill=YELLOW, ow=7, bw=3, anchor="mm")
    else:  # sub
        f = fit(d, text, W - 260, start=74)
        bold(d, (W // 2, H - 150), text, f, fill=WHITE, ow=8, bw=3, anchor="ma")
    return img


def build_telops():
    seen = {}
    for ch, text, kind in TELOPS:
        seen[ch] = seen.get(ch, 0) + 1
        name = "%s-%02d_%s.png" % (ch, seen[ch], text[:16].replace("/", "／").replace(" ", ""))
        save(telop(text, kind), "テロップ", name)
    print("テロップ %d枚" % len(TELOPS))


def build_figs():
    fig_hotel(); fig_distance(); fig_traffic()
    fig_rentacar(); fig_ynumber(); fig_rip()
    print("図解  6枚")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    build_thumbs()
    build_figs()
    build_telops()
    print("→ %s" % OUT)
