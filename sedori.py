#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X(Twitter)からせどりネタを拾って、再販の判断材料まで出す。

APIキー・有料クレジットは一切使わない(X API も AI API も不要)。
Xの投稿は Yahoo!リアルタイム検索、落札相場は ヤフオクの落札済み検索ページから
標準ライブラリだけで取る。

使い方
  python3 sedori.py                 # 収集してレポート(せどり候補.md)を書く
  python3 sedori.py --hours 24      # 直近24時間で集計
  python3 sedori.py --no-fetch      # 収集せずDBにある投稿だけで集計
  python3 sedori.py --soba "商品名"  # 落札相場だけ調べる
"""

import concurrent.futures
import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import websearch

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 語彙

# 拾いたい合図。(表示名, 語, 重み) 重みが大きいほど「仕入れの合図」として強い。
SIGNALS = [
    ("半額・大幅値引き", ["半額", "半額以下", "70%オフ", "80%オフ", "90%オフ",
                          "7割引", "8割引", "9割引", "3割引", "4割引", "5割引"], 1.4),
    ("在庫処分", ["在庫処分", "処分価格", "処分品", "見切り", "赤札", "黄札",
                  "クリアランス", "閉店セール", "売り尽くし", "ワゴン"], 1.4),
    ("再販・再入荷", ["再販", "再入荷", "再々販", "受注再開", "販売再開", "入荷しました"], 1.2),
    ("予約・抽選開始", ["予約開始", "予約受付", "抽選販売", "抽選開始", "受注開始"], 1.1),
    ("プレ値・高騰", ["プレ値", "高騰", "転売価格", "値上がり", "定価の"], 1.1),
    ("値下げ", ["値下げ", "値下がり", "プライスダウン", "割引", "%オフ", "%OFF"], 1.0),
    ("完売・品薄", ["完売", "品薄", "売り切れ", "入手困難", "在庫なし"], 1.0),
    ("クーポン・還元", ["クーポン", "ポイント還元", "%還元", "実質", "ポイ活"], 0.9),
    ("セール・特価", ["タイムセール", "セール", "特価", "激安", "訳あり", "アウトレット"], 0.8),
    ("注意(相場割れ)", ["定価割れ", "暴落", "相場崩壊", "投げ売り"], 0.5),
]

# 情報商材・勧誘アカウントのノイズ。これが入った投稿は捨てる。
NOISE_WORDS = [
    "コンサル", "公式LINE", "LINE登録", "ライン登録", "無料プレゼント", "無料配布",
    "月収", "月商", "日給", "稼げる", "稼ぐ方法", "副業", "不労所得", "脱サラ",
    "初心者でも", "リプ&", "リプで", "フォロー&", "フォロバ", "拡散希望",
    "note販売", "有料級", "限定公開", "DMください", "DM下さい", "マネタイズ",
]

# 仕入れ先として拾う店名。別名 → 表示名
SHOPS = {
    "ヤマダ": "ヤマダ電機", "ケーズ": "ケーズデンキ", "エディオン": "エディオン",
    "ジョーシン": "ジョーシン", "ノジマ": "ノジマ", "ヨドバシ": "ヨドバシ",
    "ビックカメラ": "ビックカメラ", "ビックのカメラ": "ビックカメラ", "ソフマップ": "ソフマップ",
    "ドンキ": "ドン・キホーテ", "ドン・キホーテ": "ドン・キホーテ", "驚安": "ドン・キホーテ",
    "イオン": "イオン", "ヨーカドー": "イトーヨーカドー", "西友": "西友", "ライフ": "ライフ",
    "コストコ": "コストコ", "業務スーパー": "業務スーパー", "カルディ": "カルディ",
    "カインズ": "カインズ", "コーナン": "コーナン", "ナフコ": "ナフコ", "DCM": "DCM",
    "ビバホーム": "ビバホーム", "島忠": "島忠", "ニトリ": "ニトリ",
    "しまむら": "しまむら", "西松屋": "西松屋", "バースデイ": "バースデイ",
    "トイザらス": "トイザらス", "ベビーザらス": "ベビーザらス",
    "ハードオフ": "ハードオフ", "ブックオフ": "ブックオフ", "オフハウス": "オフハウス",
    "セカスト": "セカンドストリート", "セカンドストリート": "セカンドストリート",
    "ゲオ": "ゲオ", "TSUTAYA": "TSUTAYA", "ヴィレヴァン": "ヴィレッジヴァンガード",
    "ロフト": "ロフト", "ハンズ": "ハンズ", "プラザ": "PLAZA",
    "ダイソー": "ダイソー", "セリア": "セリア", "キャンドゥ": "キャンドゥ",
    "3COINS": "3COINS", "スリコ": "3COINS",
    "サンドラッグ": "サンドラッグ", "マツキヨ": "マツモトキヨシ", "マツモトキヨシ": "マツモトキヨシ",
    "ウエルシア": "ウエルシア", "ツルハ": "ツルハ", "スギ薬局": "スギ薬局",
    "コスモス": "コスモス", "クリエイト": "クリエイト",
    "セブン": "セブンイレブン", "ローソン": "ローソン", "ファミマ": "ファミリーマート",
    "ワークマン": "ワークマン", "ユニクロ": "ユニクロ", "無印": "無印良品",
    "Amazon": "Amazon", "アマゾン": "Amazon", "楽天": "楽天", "ヤフショ": "Yahoo!ショッピング",
    "Yahoo!ショッピング": "Yahoo!ショッピング", "au PAY": "au PAY マーケット", "Qoo10": "Qoo10",
}

# 商品として拾いやすいジャンル・ブランド語。グループ名の第一候補に使う。
PRODUCT_WORDS = [
    "ポケカ", "ポケモンカード", "ワンピカード", "ワンピースカード", "遊戯王", "デュエマ",
    "MTG", "ヴァイス", "シャドバ", "バトスピ", "カードダス",
    "ガンプラ", "プラモ", "フィギュア", "ねんどろいど", "アミーボ", "amiibo",
    "レゴ", "LEGO", "シルバニア", "トミカ", "プラレール", "リカちゃん", "ベイブレード",
    "たまごっち", "ガチャ", "一番くじ", "ぬいぐるみ", "スイッチ", "Switch", "PS5", "PS4",
    "iPhone", "iPad", "AirPods", "Apple Watch", "Kindle", "Fire TV", "Echo",
    "ダイソン", "シャーク", "ルンバ", "バルミューダ", "アイリスオーヤマ", "パナソニック",
    "サーモス", "スタンレー", "スタバ", "スターバックス", "サンリオ", "ちいかわ",
    "ハローキティ", "ディズニー", "ジブリ", "鬼滅", "呪術廻戦", "推しの子",
    "ナイキ", "アディダス", "ニューバランス", "アシックス", "コンバース", "スニーカー",
    "シュプリーム", "ノースフェイス", "スタンリー", "コールマン", "スノーピーク",
]

# 表記ゆれをまとめる(別グループに割れるのを防ぐ)
PRODUCT_ALIAS = {
    "ポケモンカード": "ポケカ", "ワンピースカード": "ワンピカード", "スターバックス": "スタバ",
    "Switch": "スイッチ", "amiibo": "アミーボ", "LEGO": "レゴ", "スタンリー": "スタンレー",
}

# 【】の中身によくある、商品名ではない煽り文句
BRACKET_STOP = [
    "速報", "拡散", "緊急", "注意", "重要", "最新", "朗報", "悲報", "必見", "急げ", "PR",
    "セール", "値下げ", "在庫", "再販", "再入荷", "入荷", "予約", "抽選", "限定", "完売",
    "お得", "情報", "終了", "開始", "クーポン", "ポイント", "還元", "特価", "激安", "半額",
    "処分", "まとめ", "神", "レビュー", "動画", "本日", "今日", "明日", "毎日",
]

# 「10000円以上で送料無料」「1000円オフ」のような、仕入れ値ではない金額
_PRICE_TAIL_STOP = ("以上", "以下", "未満", "から", "オフ", "OFF", "off", "引き", "分", "相当")

# 商品名に見えるが商品ではないカタカナ語
KATAKANA_STOP = {
    "セール", "クーポン", "ポイント", "タイムセール", "キャンペーン", "ネット", "オンライン",
    "ショップ", "ストア", "リンク", "ツイート", "リプ", "フォロー", "リツイート", "プレゼント",
    "アカウント", "チェック", "ゲット", "オススメ", "レジ", "ワゴン", "アウトレット",
    "クリアランス", "プライスダウン", "セット", "ランキング", "レビュー", "コメント",
    "ニュース", "トレンド", "フォロワー", "スクショ", "ページ", "サイト", "アプリ",
    "メルカリ", "ラクマ", "ヤフオク", "アマゾン", "ヤフー", "ツイッター", "インスタ",
    "コンビニ", "スーパー", "ドラッグ", "ホームセンター", "リサイクル", "コンサル",
}

DEFAULT_KEYWORDS = [
    "せどり 仕入れ",
    "店舗せどり 値下げ",
    "在庫処分 半額",
    "再販 入荷",
    "ポケカ 再販",
    "一番くじ 在庫",
    "家電 処分価格",
    "トイザらス クリアランス",
]

DEFAULT_FEE_RATE = 0.10   # フリマ手数料(メルカリ10%)
DEFAULT_SHIP_COST = 600   # 送料の目安(円)

_PRICE_RE = re.compile(r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{2,7})\s*円")
_YEN_RE = re.compile(r"[¥￥]\s*(\d{1,3}(?:,\d{3})+|\d{2,7})")
_ARROW_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d{2,7})\s*円?\s*(?:→|->|=>|⇒|~>)\s*(\d{1,3}(?:,\d{3})+|\d{2,7})\s*円")
_JAN_RE = re.compile(r"(?<!\d)(4[59]\d{11})(?!\d)")
_MODEL_RE = re.compile(r"\b([A-Z]{2,6}[-‐]?\d{2,6}[A-Z0-9]{0,6})\b")
_BRACKET_RE = re.compile(r"[【「『\[]([^】」』\]]{2,30})[】」』\]]")
_KATAKANA_RE = re.compile(r"[ァ-ヶ][ァ-ヶー・]{2,}")
_HASHTAG_RE = re.compile(r"[#＃]\S+")
_URL_RE = re.compile(r"https?://\S+")


# ---------------------------------------------------------------- 小道具

def _norm(s):
    return unicodedata.normalize("NFKC", s or "").strip()


def _to_int(s):
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def _parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_hours(iso, now=None):
    dt = _parse_dt(iso)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def signature(text):
    """コピペ拡散を1件に数えるための、投稿本文の指紋。"""
    t = _URL_RE.sub("", _HASHTAG_RE.sub("", _norm(text)))
    t = re.sub(r"[\s　、。!！?？…・\-─—ー]+", "", t)
    return t[:40]


# ---------------------------------------------------------------- 抽出

def is_noise(text, extra_words=()):
    t = _norm(text)
    for w in list(NOISE_WORDS) + list(extra_words or ()):
        if w and w in t:
            return True
    return len(_HASHTAG_RE.findall(t)) >= 5


def find_signals(text):
    """投稿に含まれる合図を (表示名, 重み) の一覧で返す。"""
    t = _norm(text)
    out = []
    for label, words, weight in SIGNALS:
        if any(w in t for w in words):
            out.append((label, weight))
    return out


def find_prices(text):
    """本文中の金額。'1980円→980円' があれば (元値, 現価格) も返す。"""
    t = _norm(text)
    prices = []
    for regex in (_PRICE_RE, _YEN_RE):
        for m in regex.finditer(t):
            # 「〜円以上で送料無料」「1000円オフ」などは商品の値段ではない
            if t[m.end():m.end() + 3].startswith(_PRICE_TAIL_STOP):
                continue
            n = _to_int(m.group(1))
            if n is not None:
                prices.append(n)
    prices = [p for p in prices if 30 <= p <= 2000000]
    was = now = None
    m = _ARROW_RE.search(t)
    if m:
        was, now = _to_int(m.group(1)), _to_int(m.group(2))
        if was is not None and now is not None and now >= was:
            was = now = None
    return {"prices": sorted(set(prices)), "was": was, "now": now}


def find_shops(text):
    t = _norm(text)
    out = []
    for alias, name in SHOPS.items():
        if alias in t and name not in out:
            out.append(name)
    return out[:3]


def _bracket_is_product(s):
    """【速報】【拡散希望】のような煽り文句を落とす。残りが2文字以上なら商品名候補。"""
    for w in BRACKET_STOP:
        s = s.replace(w, "")
    return len(re.sub(r"[\s!！?？・/／|｜、。\d]+", "", s)) >= 2


def product_names(text):
    """商品名の候補を、確度の高い順に返す。"""
    t = _norm(text)
    low = t.lower()
    brand = []
    for w in PRODUCT_WORDS:
        if w.lower() in low:
            name = PRODUCT_ALIAS.get(w, w)
            if name not in brand:
                brand.append(name)
    brackets = [m.group(1).strip() for m in _BRACKET_RE.finditer(t)
                if _bracket_is_product(m.group(1).strip())]
    models = [m.group(1) for m in _MODEL_RE.finditer(t)]
    kata = []
    for m in _KATAKANA_RE.finditer(t):
        s = m.group(0)
        if s in KATAKANA_STOP or len(s) > 20:
            continue
        kata.append(s)
    kata.sort(key=len, reverse=True)
    return {"brand": brand[:2], "bracket": brackets[:2], "model": models[:2], "kata": kata[:2]}


def parse_post(post):
    """1投稿を、せどり用の構造に変換する。商品名が取れなければ key は None。"""
    text = post.get("title") or post.get("text") or ""
    names = product_names(text)
    price = find_prices(text)
    sigs = find_signals(text)
    # グループ名はまとまりやすい順(ブランド → 【】 → 型番 → カタカナ)で選ぶ
    name = (names["brand"] or names["bracket"] or names["model"] or names["kata"] or [None])[0]
    jan = _JAN_RE.search(_norm(text))
    return {
        "url": post.get("url"),
        "text": text,
        "author": post.get("author", ""),
        "date": post.get("date"),
        "key": _norm(name).lower().replace(" ", "") if name else None,
        "name": name,
        "jan": jan.group(1) if jan else None,
        "model": (names["model"] or [None])[0],
        # 相場検索を絞り込むための2語目(例: 「一番くじ」に対する「ちいかわ」)
        "detail": (names["brand"][1:2] or names["bracket"] or [None])[0],
        "signals": [s for s, _ in sigs],
        "signal_weight": max([w for _, w in sigs], default=0.0) + 0.15 * max(0, len(sigs) - 1),
        "prices": price["prices"],
        "was": price["was"],
        "now": price["now"],
        "shops": find_shops(text),
        "sig": signature(text),
    }


# ---------------------------------------------------------------- 集計

def _recency(hours):
    if hours is None:
        return 0.5
    for limit, factor in ((3, 1.0), (12, 0.8), (24, 0.6), (48, 0.4)):
        if hours <= limit:
            return factor
    return 0.25


def group_posts(posts, now=None):
    """商品ごとにまとめて、熱量スコア順に返す。

    スコア = 話題の広さ(1+log2 投稿数) × 合図の強さ(0.6+重み) × 鮮度
    同じ本文のコピペ拡散は1件として数える。
    """
    now = now or datetime.now(timezone.utc)
    groups, others = {}, []
    for p in posts:
        parsed = p if "key" in p else parse_post(p)
        if not parsed["key"]:
            others.append(parsed)
            continue
        g = groups.setdefault(parsed["key"], {
            "key": parsed["key"], "name": parsed["name"], "posts": [],
            "signals": [], "shops": [], "prices": [], "sigs": set(),
            "jan": None, "model": None, "details": [],
        })
        g["posts"].append(parsed)
        g["sigs"].add(parsed["sig"])
        for s in parsed["signals"]:
            if s not in g["signals"]:
                g["signals"].append(s)
        for s in parsed["shops"]:
            if s not in g["shops"]:
                g["shops"].append(s)
        g["prices"] += parsed["prices"]
        g["jan"] = g["jan"] or parsed["jan"]
        g["model"] = g["model"] or parsed["model"]
        if parsed["detail"]:
            g["details"].append(parsed["detail"])

    out = []
    for g in groups.values():
        ages = [a for a in (_age_hours(p["date"], now) for p in g["posts"]) if a is not None]
        newest = min(ages) if ages else None
        mentions = len(g["sigs"])                       # コピペを除いた実質の投稿数
        accounts = len({p["author"] for p in g["posts"] if p["author"]})
        weight = max([p["signal_weight"] for p in g["posts"]], default=0.0)
        score = (1 + math.log2(mentions)) * (0.6 + weight) * _recency(newest)
        prices = sorted(set(g["prices"]))
        buys = [p["now"] for p in g["posts"] if p["now"]]
        g["posts"].sort(key=lambda p: p["date"] or "", reverse=True)
        # 相場を引くクエリは具体的なものから: JAN > 型番 > 商品名+よく出る絞り込み語
        detail = max(set(g["details"]), key=g["details"].count) if g["details"] else None
        soba_query = g["jan"] or g["model"] or (
            "%s %s" % (g["name"], detail) if detail and detail != g["name"] else g["name"])
        out.append({
            "key": g["key"],
            "name": g["name"],
            "score": round(score, 1),
            "mentions": mentions,
            "posts_raw": len(g["posts"]),
            "accounts": accounts,
            "newest_hours": round(newest, 1) if newest is not None else None,
            "signals": g["signals"][:4],
            "shops": g["shops"],
            "price_min": prices[0] if prices else None,
            "price_max": prices[-1] if prices else None,
            "buy_price": min(buys) if buys else (prices[0] if prices else None),
            "jan": g["jan"],
            "model": g["model"],
            "soba_query": soba_query,
            "links": resale_links(soba_query),
            "posts": [{k: p[k] for k in ("url", "text", "author", "date", "signals", "prices")}
                      for p in g["posts"][:8]],
        })
    out.sort(key=lambda r: (-r["score"], -r["mentions"]))
    others.sort(key=lambda p: p["date"] or "", reverse=True)
    return out, others


# ---------------------------------------------------------------- 相場

def resale_links(name):
    """再販するときに相場と出品状況を見るリンク一式(全部無料ページ)。"""
    q = urllib.parse.quote((name or "").strip())
    return {
        "メルカリ(売切)": "https://jp.mercari.com/search?keyword=%s&status=sold_out&order=desc&sort=created_time" % q,
        "ヤフオク(落札相場)": "https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=%s&va=%s" % (q, q),
        "ラクマ(売切)": "https://fril.jp/s?query=%s&transaction=soldout" % q,
        "Amazon": "https://www.amazon.co.jp/s?k=%s" % q,
        "楽天": "https://search.rakuten.co.jp/search/mall/%s/" % q,
        "Yahoo!ショッピング": "https://shopping.yahoo.co.jp/search?p=%s" % q,
        "価格.com": "https://kakaku.com/search_results/%s/" % q,
        "X(元投稿)": "https://search.yahoo.co.jp/realtime/search?p=%s" % q,
    }


_soba_lock = threading.Lock()
_soba_last = [0.0]

_SOBA_PATTERNS = [
    re.compile(r'Product__priceValue[^>]*>\s*([\d,]{3,})\s*円'),
    re.compile(r'class="[^"]*priceValue[^"]*"[^>]*>\s*([\d,]{3,})'),
    re.compile(r'>\s*([\d,]{3,})\s*円\s*<'),
]


def fetch_sold_stats(query, interval=1.5):
    """ヤフオクの落札済み検索から相場を出す(APIキー不要)。

    ページの作りが変わると取れなくなるので、失敗は例外ではなく count=0 で返す。
    """
    q = (query or "").strip()
    url = ("https://auctions.yahoo.co.jp/closedsearch/closedsearch?"
           + urllib.parse.urlencode({"p": q, "va": q, "n": "50"}))
    if not q:
        return {"query": q, "count": 0, "url": url, "error": "商品名がありません"}
    with _soba_lock:
        wait = interval - (time.time() - _soba_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            html = websearch._get(url)
        except Exception as e:  # noqa: BLE001
            _soba_last[0] = time.time()
            return {"query": q, "count": 0, "url": url, "error": str(e)}
        _soba_last[0] = time.time()
    prices = []
    for pat in _SOBA_PATTERNS:
        vals = [_to_int(m) for m in pat.findall(html)]
        vals = [v for v in vals if v and 100 <= v <= 3000000]
        if len(vals) >= 3:
            prices = vals
            break
    if not prices:
        return {"query": q, "count": 0, "url": url,
                "error": "落札データが見つかりませんでした"}
    prices.sort()
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) // 2
    return {"query": q, "count": len(prices), "url": url,
            "median": median, "min": prices[0], "max": prices[-1],
            "avg": round(sum(prices) / len(prices))}


def profit(sold_median, buy_price, fee_rate=DEFAULT_FEE_RATE, ship_cost=DEFAULT_SHIP_COST):
    """相場と仕入れ値から、手数料・送料を引いた粗利を出す。"""
    if not sold_median or not buy_price:
        return None
    net = sold_median * (1 - fee_rate) - ship_cost
    gain = net - buy_price
    return {"net": round(net), "gain": round(gain),
            "rate": round(gain / buy_price * 100, 1) if buy_price else None,
            "fee_rate": fee_rate, "ship_cost": ship_cost}


# ---------------------------------------------------------------- 収集

def fetch_posts(queries, per_query=30, workers=3):
    """Yahoo!リアルタイム検索経由でXの投稿を集める。"""
    out, errors = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(websearch.fetch_x, q, per_query): q for q in queries}
        for fut in concurrent.futures.as_completed(futs):
            q = futs[fut]
            try:
                for item in fut.result():
                    item["query"] = q
                    out.append(item)
            except Exception as e:  # noqa: BLE001
                errors[q] = str(e)
    return out, errors


def store_posts(con, posts):
    """新しく見た投稿だけDBに足す。戻り値は新規件数。"""
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    for p in posts:
        url = p.get("url")
        if not url:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO sedori_posts(url,text,author,posted_at,query,first_seen)"
            " VALUES(?,?,?,?,?,?)",
            (url, p.get("title") or "", p.get("author") or "", p.get("date"),
             p.get("query") or "", now))
        new += cur.rowcount
    con.commit()
    return new


def load_posts(con, hours=48):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = con.execute(
        "SELECT url,text,author,posted_at,first_seen FROM sedori_posts"
        " WHERE COALESCE(posted_at, first_seen) >= ? ORDER BY COALESCE(posted_at, first_seen) DESC",
        (since,)).fetchall()
    return [{"url": r["url"], "title": r["text"], "author": r["author"],
             "date": r["posted_at"] or r["first_seen"]} for r in rows]


def collect(con, cfg, log=print):
    """設定のキーワードでXを回して、投稿をDBに貯める。"""
    queries = cfg.get("sedori_keywords") or DEFAULT_KEYWORDS
    posts, errors = fetch_posts(queries, per_query=cfg.get("sedori_per_query", 30))
    new = store_posts(con, posts)
    for q, e in errors.items():
        log("  ! せどり検索失敗 %s (%s)" % (q, e))
    log("せどり: %d件取得 / 新規%d件 (キーワード%d本)" % (len(posts), new, len(queries)))
    return {"fetched": len(posts), "new": new, "errors": errors}


def build(con, cfg, hours=None):
    """DBに貯めた投稿から、商品ごとのランキングを作る。"""
    hours = hours or cfg.get("sedori_window_hours", 48)
    exclude = cfg.get("sedori_exclude_words", [])
    raw = load_posts(con, hours)
    kept = [parse_post(p) for p in raw if not is_noise(p.get("title", ""), exclude)]
    items, others = group_posts(kept)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "post_count": len(raw),
        "used_count": len(kept),
        "keywords": cfg.get("sedori_keywords") or DEFAULT_KEYWORDS,
        "fee_rate": cfg.get("sedori_fee_rate", DEFAULT_FEE_RATE),
        "ship_cost": cfg.get("sedori_ship_cost", DEFAULT_SHIP_COST),
        "items": items[:60],
        "others": [{k: p[k] for k in ("url", "text", "author", "date", "signals")}
                   for p in others[:30]],
    }


# ---------------------------------------------------------------- レポート

def write_report(data, base=None):
    base = base or BASE
    path = os.path.join(base, "せどり候補.md")
    t = _parse_dt(data["generated_at"])
    L = ["# せどり候補（X/Twitterから収集）", "",
         "更新: %s / 直近%d時間の投稿 %d件（ノイズ除去後 %d件）" % (
             t.astimezone().strftime("%Y-%m-%d %H:%M") if t else "-",
             data["hours"], data["post_count"], data["used_count"]), ""]
    if not data["items"]:
        L.append("まだ候補がありません。`python3 sedori.py` を実行してください。")
    for i, it in enumerate(data["items"][:30], 1):
        head = "## %d. %s （熱量 %s / %d投稿" % (i, it["name"], it["score"], it["mentions"])
        if it["newest_hours"] is not None:
            head += " / 最新 %.1f時間前" % it["newest_hours"]
        L.append(head + "）")
        if it["signals"]:
            L.append("- 合図: %s" % " / ".join(it["signals"]))
        if it["shops"]:
            L.append("- 店舗: %s" % " / ".join(it["shops"]))
        if it["buy_price"]:
            L.append("- 価格: %s円%s" % (
                "{:,}".format(it["buy_price"]),
                "（本文の金額 %s〜%s円）" % ("{:,}".format(it["price_min"]),
                                             "{:,}".format(it["price_max"]))
                if it["price_min"] != it["price_max"] else ""))
        if it["jan"]:
            L.append("- JAN: %s" % it["jan"])
        L.append("- 相場: %s" % it["links"]["ヤフオク(落札相場)"])
        L.append("- メルカリ売切: %s" % it["links"]["メルカリ(売切)"])
        for p in it["posts"][:3]:
            L.append("  - %s %s" % (p["text"][:80].replace("\n", " "), p["url"]))
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def main():
    import research  # 循環importを避けるため、CLIのときだけ読む

    args = sys.argv[1:]
    if "--soba" in args:
        i = args.index("--soba")
        q = " ".join(a for a in args[i + 1:] if not a.startswith("--"))
        print(json.dumps(fetch_sold_stats(q), ensure_ascii=False, indent=2))
        return
    hours = None
    if "--hours" in args:
        hours = int(args[args.index("--hours") + 1])
    cfg = research.load_config()
    con = research.connect()
    try:
        if "--no-fetch" not in args:
            collect(con, cfg, log=research.log)
        data = build(con, cfg, hours)
        path = write_report(data)
    finally:
        con.close()
    print("候補 %d件 / レポート: %s" % (len(data["items"]), path))
    for it in data["items"][:10]:
        print("  %5s  %-24s %s" % (
            it["score"], (it["name"] or "")[:24], " / ".join(it["signals"][:2])))


if __name__ == "__main__":
    main()
