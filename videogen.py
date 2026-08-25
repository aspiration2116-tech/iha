#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台本から動画を作る。

  台本テキスト
    → 1行1クリップに分割
    → 字幕の改行(1〜2行・「、」で区切る・150サイズに収まる幅)
    → VOICEVOX の読み間違いを検出・修正
    → VOICEVOX ENGINE で音声合成
    → Pixabay からイラストを取得
    → ffmpeg で mp4 に書き出し(BGM のミックス込み)

外部に必要なもの:
  * VOICEVOX ENGINE   … 音声合成。http://127.0.0.1:50021 で待ち受けている必要がある
  * ffmpeg            … 動画の書き出し。brew install ffmpeg
  * Pixabay の APIキー … 画像の自動取得。無料。config.json の pixabay_key に入れる
  * pyopenjtalk(任意) … 入っていれば読み間違いを全行スキャンできる

どれが欠けていても、そこまでの工程は動く。check_env() が状態を返す。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
import wave

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(BASE, "video_work")

VOICEVOX_URL = "http://127.0.0.1:50021"
PIXABAY_URL = "https://pixabay.com/api/"

# 字幕の見た目(Vrew の globalCaptionStyle に合わせた既定値)
DEFAULTS = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "caption_font": "Hiragino Sans",     # Mac の標準日本語フォント
    "caption_size": 72,                  # 1080p で Vrew の 150 相当
    "caption_color": "000000",           # 文字色(黒)
    "caption_outline": "ffffff",         # 縁取り(白)
    "caption_outline_width": 6,
    "caption_margin_v": 90,              # 下からの余白(px)
    "voicevox_speaker": 3,
    "clip_pad_sec": 0.25,                # 各クリップの後ろに足す無音
    "image_type": "illustration",        # illustration / photo / all
    "bgm_volume": 0.06,                  # 「音量3」相当のひかえめな既定値
}

# ---------------------------------------------------------------- 幅の計算


def eff(s):
    """全角を1、半角を0.5として数えた表示幅。"""
    return sum(0.5 if unicodedata.east_asian_width(ch) in "NaH" else 1 for ch in s)


# ---------------------------------------------------------------- 読み間違い

# そのまま置き換えて安全なもの(意味が変わらず、読みだけ直る)
SAFE_FIXES = [
    ("吹き出し口", "吹き出しぐち", "フキダシクチ と読まれる"),
    ("吸い込み口", "吸い込みぐち", "スイコミコー と読まれる"),
    ("ひとっ走り", "ひとっぱしり", "ヒトッハシリ と読まれる"),
    ("白髪", "しらが", "ハクハツ と読まれる"),
    ("内気", "ないき", "ウチキ と読まれる"),
    ("一手間", "ひと手間", "イチテマ と読まれる"),
    ("手放し方", "手放しかた", "テバナシホー と読まれる"),
    ("後が楽", "あとが楽", "ゴガラク と読まれる"),
    ("中から", "なかから", "チューカラ と読まれる"),
    ("棚の上", "棚のうえ", "タナノジョー と読まれる"),
    ("空にする", "からにする", "ソラニスル と読まれる"),
    ("蒸発皿", "じょうはつざら", "ジョーハツサラ と読まれる"),
    ("照り返し", "てりかえし", "デリガエシ と読まれる"),
    ("長ズボン", "ながズボン", "チョーズボン と読まれる"),
    ("古タイヤ", "ふるタイヤ", "コタイヤ と読まれる"),
    ("ご飯粒", "ごはんつぶ", "ゴメシツブ と読まれる"),
    ("水鉢", "みずばち", "スイバチ と読まれる"),
    ("本革", "ほんがわ", "ホンカワ と読まれる"),
    ("天日", "てんぴ", "テンジツ と読まれる"),
    ("日中", "にっちゅう", "ヒチュー と読まれる"),
    ("風量", "ふうりょう", "カゼリョウ と読まれる"),
    ("食いつき", "くいつき", "グイツキ と読まれる"),
    ("房のまま", "ふさのまま", "ボーノママ と読まれる"),
    ("十分です", "じゅうぶんです", "ジュップン と読まれる"),
    ("十分に", "じゅうぶんに", "ジュップン と読まれる"),
    ("重なり", "かさなり", "オモナリ と読まれる"),
    ("放って", "ほうって", "ハナッテ と読まれる"),
    ("卵鞘", "卵が入った袋", "タマゴサヤ と読まれる"),
    ("小豆大", "小豆くらいの大きさ", "ショーズマサル と読まれる"),
    ("燻煙剤", "煙が出る殺虫剤", "イブシケムリザイ と読まれる"),
    ("消臭クリーナー", "においとりクリーナー", "ケシシュー と読まれる"),
    ("消臭スプレー", "においとりスプレー", "ケシシュー と読まれる"),
]

# 人が判断したほうがよいもの(自動では直さず、警告だけ出す)
WARN_PATTERNS = [
    # 「〜の方が」は比較で、ホーガ が正しい読み。人を指す「方は/方へ/方も」だけ知らせる
    (re.compile(r"(?:いる|ている|くる|する|な|の)方(?=[はへもにとほ、。]|$)"),
     "「方」が ホー と読まれます。人・みなさん・さん に置き換えてください"),
    (re.compile(r"[たっし]分(?=[はがをのにで、。]|$)"),
     "「分」が ワケ と読まれることがあります。ぶん と書いてください"),
    (re.compile(r"加齢"), "「加齢」が カレー と読まれます。年齢とともに 等に"),
    (re.compile(r"分別"), "「分別」が フンベツ と読まれます。仕分け・分け方 に"),
    (re.compile(r"糞"), "「糞」が クソ と読まれます。ふん に"),
    (re.compile(r"配線が通"), "「通って」が カヨッテ と読まれます。走って に"),
    (re.compile(r"冷ます"), "「冷ます」が ヒエマス と読まれます。さます に"),
    (re.compile(r"焦る"), "「焦る」が コゲル と読まれます。あせる に"),
    (re.compile(r"実に"), "「実に」が ミニ と読まれることがあります"),
    # 踊り字。よくある語は正しく読まれるので、それ以外だけ知らせる
    (re.compile(r"(?<!時)(?<!人)(?<!別)(?<!家)(?<!次)(?<!度)(?<!様)(?<!色)"
                r"(?<!日)(?<!我)(?<!所)(?<!方)(?<!数)(?<!各)々"),
     "踊り字「々」が読み飛ばされることがあります。文字を書き下してください"),
]

# pyopenjtalk で全行スキャンするときの「誤読カナ」。値は誤読が出ても無視する文脈
BAD_KANA = {
    "ホー": ("ホーホー", "ホーガ", "ホース", "ジョーホー", "ホーコーザイ",
            "ホームセンター", "カタホー", "ホーソー", "ホーメン", "ホーコー"),
    "ワケ": ("キリワケ", "シワケ", "ウチワケ"),
    "ウチキ": (),
    "ケシシュー": (),
    "カヨッテ": (),
    "ハクハツ": (),
    "カレー": (),
    "フンベツ": (),
    "スイコミコー": (),
    "ヒトッハシリ": (),
    "チューカラ": (),
    "ゴガラク": (),
    "ヤスミジョー": (),
    "タナノジョー": (),
    "ソラニスル": (),
    "イチテマ": (),
    "オモナリ": (),
    "ハナッテ": (),
    "モツヲ": (),
    "コゲル": (),
    "カゼリョウ": (),
    "テンジツ": (),
    "ヒチュー": (),
    "ホンカワ": (),
    "ショーズ": (),
    "タマゴサヤ": (),
    "デリガエシ": (),
    "ボーノママ": (),
    "グイツキ": (),
    "ゴメシツブ": (),
    "スイバチ": (),
    "コタイヤ": (),
    "チョーズボン": (),
    "ジョーハツサラ": (),
}


def fix_readings(text):
    """安全な置き換えを適用し、(直した文, 適用一覧, 要確認の警告) を返す。"""
    applied, warns = [], []
    out = text
    for before, after, note in SAFE_FIXES:
        if before in out:
            applied.append({"before": before, "after": after, "note": note})
            out = out.replace(before, after)
    for pat, msg in WARN_PATTERNS:
        m = pat.search(out)
        if m:
            warns.append({"hit": m.group(0), "note": msg})
    return out, applied, warns


def scan_readings(lines):
    """pyopenjtalk があれば全行の読みを実際に確かめる。無ければ空を返す。"""
    try:
        import pyopenjtalk  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    hits = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        kana = pyopenjtalk.g2p(line, kana=True)
        for bad, allow in BAD_KANA.items():
            if bad not in kana:
                continue
            masked = kana
            for a in allow:
                masked = masked.replace(a, "")
            if bad in masked:
                hits.append({"index": i, "text": line, "kana": kana, "bad": bad})
    return hits


# ---------------------------------------------------------------- 字幕の改行

_DIGIT_COMMA = re.compile(r"(?<=[0-9０-９])、(?=[0-9０-９])")


# 読点の直前がこれらなら、読点を落としても文の切れ目が分かる
_PARTICLE = set("はがをにでともへやのばらずてただ")
# 文節の切れ目になりやすい語。この直後で行を割る
_BREAK_AFTER = ("を", "に", "は", "が", "で", "と", "も", "へ", "や", "の",
                "から", "まで", "より", "ば", "て", "た", "だ", "ら", "ても",
                "ので", "のに", "けど", "たら", "なら", "ます", "です", "ない")


def _commas(s):
    """落としてよい読点の位置。数字にはさまれたものは対象外。"""
    return [m.start() for m in re.finditer("、", s)
            if not _DIGIT_COMMA.match(s, m.start())]


def _drop_commas(s):
    """落としてよい読点だけを取り除く。"""
    drop = set(_commas(s))
    return "".join(ch for i, ch in enumerate(s) if not (ch == "、" and i in drop))


def _droppable(s):
    """読点を落としても読み違えないか。直前が助詞・活用語尾なら落としてよい。"""
    pos = _commas(s)
    return bool(pos) and all(i > 0 and s[i - 1] in _PARTICLE for i in pos)


def _clean(s, keep_comma_eff, keep_comma=False):
    """1行ぶんの仕上げ。短い行と、落とすと読みにくい読点は残す。"""
    s = s.strip("、 ")
    if not _commas(s):
        return s
    if keep_comma or eff(s) <= keep_comma_eff:
        return s
    return _drop_commas(s) if _droppable(s) else s


# 「第5位」「失敗の1つ」などの直後の行は順位の見出し。読点を間として残す
HEADLINE_BEFORE = re.compile(r"^(第\s*\d+\s*位|失敗の\s*\d+\s*つ|\d+つ目)[。．]?$")


def wrap_caption(text, max_eff=23.5, max_chars=44, one_line_eff=20.0,
                 keep_comma_eff=12.0, headline=False):
    """字幕を1行または2行に割る。

    * 1行に収まるなら1行。読点は落とす(短い行・数字の読点・落とすと読みにくいものは残す)
    * 収まらないなら「、」の位置で2行に割る
    * 「、」で割ると1行目が極端に短くなる場合だけ、文節の切れ目で割る
    """
    t = text.strip().rstrip("。").rstrip("．")
    if not t:
        return [""]

    one = _clean(t, keep_comma_eff, headline)
    if eff(one) <= one_line_eff:
        return [one]

    cands = []
    for i in _commas(t):
        a = _clean(t[:i], keep_comma_eff)
        b = _clean(t[i + 1:], keep_comma_eff)
        if a and b:
            cands.append((a, b))
    best = _best_split(cands, max_eff, max_chars)
    if best:
        return list(best)

    return list(_split_by_phrase(_drop_commas(t), max_eff, max_chars))


def _score(a, b, max_eff):
    """左右の均等さを見る。短すぎる行と幅超えを強く嫌う。"""
    ea, eb = eff(a), eff(b)
    if ea > max_eff or eb > max_eff:
        return -1e9
    if ea < 5 or eb < 5:
        return -1e6 + min(ea, eb)
    pen = 3 if a[-1] in "のなという" else 0   # 名詞句を割ってしまう切れ目は避ける
    return -abs(ea - eb) - pen


def _best_split(cands, max_eff, max_chars):
    best, score = None, -1e8
    for a, b in cands:
        if len(a) + len(b) > max_chars:
            continue
        s = _score(a, b, max_eff)
        if s > score:
            best, score = (a, b), s
    return best if score > -1e5 else None


# この語で始まる側に割らない(複合助詞・補助動詞)
_NO_BREAK_BEFORE = ("とって", "ついて", "よって", "対して", "つれて", "かけて",
                    "しても", "ながら", "ください", "いる", "ある", "おく", "みる",
                    "しまう", "くる", "いく", "です", "ます")


def _split_by_phrase(s, max_eff, max_chars):
    """助詞や活用語尾の直後で割る。語の途中では割らない。"""
    n = len(s)
    best, score = (s[: n // 2], s[n // 2:]), -1e9
    for i in range(3, n - 2):
        w = next((w for w in _BREAK_AFTER if s[:i].endswith(w)), None)
        if not w:
            continue
        if s[i] in "んっーゃゅょ":
            continue
        # 「〜に|とって」のように複合助詞を割らない
        if any(s[i:].startswith(x) for x in _NO_BREAK_BEFORE):
            continue
        # 1文字の助詞で切るときは、その前が名詞(漢字・カタカナ)のときだけ。
        # 「ているも|のも」「つけただ|けで」のような語の途中で切らないため。
        if len(w) == 1 and i >= 2 and "ぁ" <= s[i - 2] <= "ん":
            continue
        a, b = s[:i], s[i:]
        if len(a) + len(b) > max_chars:
            continue
        sc = _score(a, b, max_eff)
        if sc > score:
            best, score = (a, b), sc
    return best


# ---------------------------------------------------------------- 台本の分割

def split_script(text):
    """台本を1行1クリップに分ける。空行は捨てる。"""
    return [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


_STOP = set("""
これ それ あれ ここ そこ どこ こと もの ため とき ところ よう ほう ひと みなさん
今日 本当 一番 場合 自分 今回
""".split())
_KANJI = re.compile(r"[一-龥]{2,}")
_KATA = re.compile(r"[ァ-ヶー]{3,}")


def image_keyword(caption, fallback=""):
    """字幕から画像検索のことばを1つ選ぶ。見つからなければ fallback。"""
    cands = [w for w in _KATA.findall(caption) if w not in _STOP]
    cands += [w for w in _KANJI.findall(caption) if w not in _STOP]
    cands = [w for w in cands if len(w) >= 2]
    if not cands:
        return fallback
    return max(cands, key=len)


def build_plan(script_text, topic="", cfg=None):
    """台本 → クリップの一覧。音声も画像もまだ作らない。"""
    cfg = dict(DEFAULTS, **(cfg or {}))
    lines = split_script(script_text)
    clips = []
    for i, raw in enumerate(lines):
        speech, applied, warns = fix_readings(raw)
        head = bool(i and HEADLINE_BEFORE.match(lines[i - 1]))
        caption_lines = wrap_caption(raw, headline=head)
        clips.append({
            "index": i,
            "source": raw,
            "speech": speech,                       # 読み上げ用(読みを直したもの)
            "caption": "\n".join(caption_lines),    # 字幕(見た目は元のまま)
            "caption_lines": caption_lines,
            "fixes": applied,
            "warns": warns,
            "keyword": image_keyword(raw, topic),
            "image": None,
            "audio": None,
            "duration": None,
        })
    scan = scan_readings([c["speech"] for c in clips])
    if scan:
        by_i = {}
        for h in scan:
            by_i.setdefault(h["index"], []).append(h)
        for i, hits in by_i.items():
            clips[i]["warns"] = clips[i]["warns"] + [
                {"hit": h["bad"], "note": "読み上げると %s になります" % h["kana"]}
                for h in hits]
    return {
        "topic": topic,
        "clips": clips,
        "scanned": scan is not None,
        "stats": _plan_stats(clips),
    }


def _plan_stats(clips):
    n1 = sum(1 for c in clips if len(c["caption_lines"]) == 1)
    n2 = sum(1 for c in clips if len(c["caption_lines"]) == 2)
    over = [c["index"] for c in clips if len(c["caption_lines"]) > 2]
    wide = [c["index"] for c in clips
            for L in c["caption_lines"] if eff(L) > 23.5]
    body = sum(len(c["source"]) for c in clips)
    return {
        "clips": len(clips),
        "one_line": n1, "two_line": n2, "over_line": over, "too_wide": sorted(set(wide)),
        "chars": body, "chars_with_newline": body + len(clips),
        "fixes": sum(len(c["fixes"]) for c in clips),
        "warns": sum(len(c["warns"]) for c in clips),
    }


# ---------------------------------------------------------------- VOICEVOX

def _post_json(url, payload=None, timeout=120):
    data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def voicevox_speakers():
    """使えるナレーターの一覧。ENGINE が動いていなければ例外。"""
    with urllib.request.urlopen(VOICEVOX_URL + "/speakers", timeout=10) as res:
        raw = json.loads(res.read().decode("utf-8"))
    out = []
    for sp in raw:
        for st in sp.get("styles", []):
            out.append({"id": st["id"], "name": "%s（%s）" % (sp["name"], st["name"])})
    return out


VOICEVOX_HELP = ("VOICEVOX ENGINE につながりません。VOICEVOX を起動してから"
                 "もう一度お試しください（%s で待ち受けます）" % VOICEVOX_URL)


def synthesize(text, speaker, out_path, speed=1.0):
    """1行ぶんの音声を作って wav で保存し、秒数を返す。"""
    q = VOICEVOX_URL + "/audio_query?" + urllib.parse.urlencode(
        {"text": text, "speaker": speaker})
    try:
        raw = _post_json(q)
    except OSError as e:
        raise RuntimeError(VOICEVOX_HELP) from e
    query = json.loads(raw.decode("utf-8"))
    query["speedScale"] = speed
    try:
        wav = _post_json(VOICEVOX_URL + "/synthesis?" + urllib.parse.urlencode(
            {"speaker": speaker}), query)
    except OSError as e:
        raise RuntimeError(VOICEVOX_HELP) from e
    with open(out_path, "wb") as f:
        f.write(wav)
    return wav_duration(out_path)


def wav_duration(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def concat_wavs(paths, out_path, pad_sec=0.0):
    """同じ形式の wav をつないで1本にする(ffmpeg 不要)。"""
    with wave.open(paths[0], "rb") as w0:
        params = w0.getparams()
    silence = b"\x00" * int(params.framerate * pad_sec) * params.sampwidth * params.nchannels
    with wave.open(out_path, "wb") as out:
        out.setparams(params)
        for p in paths:
            with wave.open(p, "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if silence:
                out.writeframes(silence)
    return wav_duration(out_path)


# ---------------------------------------------------------------- 画像

def pixabay_search(keyword, api_key, image_type="illustration", per_page=12):
    params = {
        "key": api_key, "q": keyword, "lang": "ja", "image_type": image_type,
        "orientation": "horizontal", "safesearch": "true", "per_page": per_page,
    }
    url = PIXABAY_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as res:
        data = json.loads(res.read().decode("utf-8"))
    return [{"id": h["id"], "preview": h["previewURL"], "large": h.get("largeImageURL")
             or h["webformatURL"]} for h in data.get("hits", [])]


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as res, open(path, "wb") as f:
        shutil.copyfileobj(res, f)
    return path


# ---------------------------------------------------------------- 手持ちの画像

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
_NUM = re.compile(r"(\d+)")


def _natural_key(name):
    """「2」が「10」より前に来るように並べる。"""
    return [int(t) if t.isdigit() else t.lower() for t in _NUM.split(name)]


def list_folder_images(folder):
    """フォルダの中の画像を、名前の順に並べて返す。"""
    folder = os.path.expanduser(folder or "")
    if not os.path.isdir(folder):
        raise RuntimeError("フォルダが見つかりません: %s" % folder)
    names = [n for n in os.listdir(folder)
             if n.lower().endswith(IMAGE_EXT) and not n.startswith(".")]
    names.sort(key=_natural_key)
    return [os.path.join(folder, n) for n in names]


HOME = os.path.expanduser("~")


def browse(path=""):
    """フォルダの中を見る。ホームフォルダの外へは出ない。"""
    path = os.path.realpath(os.path.expanduser(path or HOME))
    if not (path == HOME or path.startswith(HOME + os.sep)) or not os.path.isdir(path):
        path = HOME
    folders = []
    for n in sorted(os.listdir(path), key=lambda x: x.lower()):
        if n.startswith("."):
            continue
        full = os.path.join(path, n)
        if not os.path.isdir(full):
            continue
        try:
            cnt = sum(1 for f in os.listdir(full)
                      if f.lower().endswith(IMAGE_EXT) and not f.startswith("."))
        except OSError:
            cnt = 0
        folders.append({"name": n, "path": full, "images": cnt})
    here = sum(1 for f in os.listdir(path)
               if f.lower().endswith(IMAGE_EXT) and not f.startswith("."))
    parent = os.path.dirname(path)
    return {
        "path": path,
        "label": path.replace(HOME, "ホーム", 1),
        "parent": parent if path != HOME and parent.startswith(HOME) else "",
        "folders": folders,
        "images": here,
    }


def assign_folder_images(pdir, plan, folder, mode="order", progress=None,
                         overwrite=False):
    """Canva などで書き出した画像を各クリップに割り当てる。

    mode="order"   … 並び順のとおり、上から順に配る(足りなければ繰り返す)
    mode="keyword" … ファイル名にクリップの検索語が入っていればそれを優先し、
                     見つからないクリップには順番に配る
    """
    files = list_folder_images(folder)
    if not files:
        raise RuntimeError("そのフォルダに画像がありません: %s" % folder)
    n = len(plan["clips"])
    used = 0
    for c in plan["clips"]:
        if c.get("image") and not overwrite:
            continue
        pick = None
        if mode == "keyword":
            kw = (c.get("keyword") or "").strip()
            if kw:
                pick = next((f for f in files
                             if kw in os.path.basename(f)), None)
        if pick is None:
            pick = files[used % len(files)]
            used += 1
        dst = os.path.join(pdir, "images", "%05d%s"
                           % (c["index"], os.path.splitext(pick)[1].lower()))
        shutil.copyfile(pick, dst)
        c["image"] = dst
        c["image_name"] = os.path.basename(pick)
        if progress:
            progress("画像を割り当てています %d/%d" % (c["index"] + 1, n))
    return save_plan(pdir, plan)


# ---------------------------------------------------------------- ASS 字幕

def _ass_color(hexstr, alpha="00"):
    """#RRGGBB → ASS の &HAABBGGRR。"""
    h = hexstr.lstrip("#")
    return "&H%s%s%s%s" % (alpha, h[4:6], h[2:4], h[0:2])


def _ass_time(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def build_ass(clips, cfg, path):
    """クリップの秒数から、焼き込む字幕ファイルを作る。"""
    cfg = dict(DEFAULTS, **(cfg or {}))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg['width']}
PlayResY: {cfg['height']}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{cfg['caption_font']},{cfg['caption_size']},{_ass_color(cfg['caption_color'])},{_ass_color(cfg['caption_color'])},{_ass_color(cfg['caption_outline'])},&H80000000,-1,0,0,0,100,100,0,0,1,{cfg['caption_outline_width']},0,2,60,60,{cfg['caption_margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows, t = [], 0.0
    for c in clips:
        dur = float(c.get("duration") or 0) + float(cfg["clip_pad_sec"])
        text = (c.get("caption") or "").replace("\n", "\\N")
        if text:
            rows.append("Dialogue: 0,%s,%s,Main,,0,0,0,,%s"
                        % (_ass_time(t), _ass_time(t + dur), text))
        t += dur
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(rows) + "\n")
    return path, t


# ---------------------------------------------------------------- ffmpeg

def ffmpeg_path(cfg=None):
    """ffmpeg を探す。PATH に無くても、よくある場所とこのフォルダの中を見る。"""
    cfg = cfg or {}
    for c in (cfg.get("ffmpeg_path"), shutil.which("ffmpeg"),
              "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
              os.path.join(BASE, "ffmpeg")):
        if not c:
            continue
        c = os.path.expanduser(c)
        if not os.path.isfile(c):
            continue
        if not os.access(c, os.X_OK):
            try:                       # ダウンロードした実行ファイルは権限が落ちている
                os.chmod(c, 0o755)
            except OSError:
                continue
        return c
    return None


FFMPEG_HELP = (
    "ffmpeg が見つかりません。次のどちらかで用意してください。\n"
    "(1) ターミナルで brew install ffmpeg\n"
    "(2) ffmpeg の実行ファイルをこのツールのフォルダに置く"
    "（置いたあと、ターミナルで xattr -d com.apple.quarantine ffmpeg が必要な場合があります）")


def _concat_file(clips, cfg, path, fallback_image):
    """静止画を並べる concat デマルチプレクサ用のファイル。"""
    lines = []
    for c in clips:
        img = c.get("image") or fallback_image
        dur = float(c.get("duration") or 0) + float(cfg["clip_pad_sec"])
        lines.append("file '%s'" % img.replace("'", r"'\''"))
        lines.append("duration %.3f" % dur)
    if lines:
        lines.append("file '%s'" % (clips[-1].get("image") or fallback_image))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def solid_image(path, cfg, color="#f2ede4"):
    """画像が無いクリップ用の下地。ffmpeg で1枚作る。"""
    subprocess.run(
        [ffmpeg_path(cfg) or "ffmpeg", "-y", "-f", "lavfi", "-i",
         "color=c=%s:s=%dx%d" % (color.lstrip("#"), cfg["width"], cfg["height"]),
         "-frames:v", "1", path],
        check=True, capture_output=True)
    return path


def _bgm_filters(bgm_rules, clips, cfg, inputs):
    """BGM の入力と filter_complex の断片を組み立てる。

    bgm_rules: [{"file":..., "from":1, "to":182, "volume":0.06}, ...]
               from/to は1始まりのクリップ番号(両端を含む)
    """
    ends, t = [], 0.0
    for c in clips:
        t += float(c.get("duration") or 0) + float(cfg["clip_pad_sec"])
        ends.append(t)
    parts, labels = [], []
    for n, rule in enumerate(bgm_rules):
        i0 = max(1, int(rule.get("from", 1))) - 1
        i1 = min(len(clips), int(rule.get("to", len(clips)))) - 1
        if i0 > i1:
            continue
        start = ends[i0 - 1] if i0 > 0 else 0.0
        dur = ends[i1] - start
        vol = float(rule.get("volume", cfg["bgm_volume"]))
        idx = len(inputs)
        inputs.extend(["-stream_loop", "-1", "-i", rule["file"]])
        lbl = "bgm%d" % n
        parts.append(
            "[%d:a]atrim=0:%.3f,asetpts=PTS-STARTPTS,volume=%.4f,"
            "afade=t=in:st=0:d=1,afade=t=out:st=%.3f:d=1,adelay=%d|%d[%s]"
            % (idx, dur, vol, max(0.0, dur - 1.5), int(start * 1000), int(start * 1000), lbl))
        labels.append(lbl)
    return parts, labels


def render(project_dir, clips, cfg=None, bgm_rules=None, out_name="out.mp4",
           progress=None):
    """画像 + 音声 + 字幕 (+ BGM) を mp4 にする。"""
    cfg = dict(DEFAULTS, **(cfg or {}))
    bgm_rules = [r for r in (bgm_rules or []) if r.get("file")]
    ff = ffmpeg_path(cfg)
    if not ff:
        raise RuntimeError(FFMPEG_HELP)

    def say(m):
        if progress:
            progress(m)

    say("音声をつないでいます")
    voice = os.path.join(project_dir, "voice.wav")
    concat_wavs([c["audio"] for c in clips], voice, cfg["clip_pad_sec"])

    say("字幕を作っています")
    ass_path = os.path.join(project_dir, "sub.ass")
    _, total = build_ass(clips, cfg, ass_path)

    fallback = os.path.join(project_dir, "_blank.png")
    if not os.path.exists(fallback):
        solid_image(fallback, cfg)
    concat_txt = _concat_file(clips, cfg, os.path.join(project_dir, "images.txt"), fallback)

    out_path = os.path.join(project_dir, out_name)
    inputs = ["-f", "concat", "-safe", "0", "-i", concat_txt, "-i", voice]
    vf = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
          "crop=%d:%d,setsar=1,fps=%d,ass='%s'[v]"
          % (cfg["width"], cfg["height"], cfg["width"], cfg["height"], cfg["fps"],
             ass_path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")))
    parts = [vf]
    bgm_parts, bgm_labels = _bgm_filters(bgm_rules, clips, cfg, inputs)
    parts.extend(bgm_parts)
    if bgm_labels:
        mix = "".join("[%s]" % l for l in bgm_labels)
        parts.append("[1:a]%s amix=inputs=%d:duration=first:dropout_transition=0,"
                     "alimiter=limit=0.95[a]" % (mix, len(bgm_labels) + 1))
        amap = "[a]"
    else:
        amap = "1:a"

    cmd = ([ff, "-y"] + inputs
           + ["-filter_complex", ";".join(parts),
              "-map", "[v]", "-map", amap,
              "-c:v", "libx264", "-preset", "medium", "-crf", "20",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
              "-shortest", out_path])
    say("動画を書き出しています（%d分%02d秒ぶん）" % (int(total // 60), int(total % 60)))
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().split("\n")[-12:]
        raise RuntimeError("ffmpeg が失敗しました:\n" + "\n".join(tail))
    say("できました")
    return out_path, total


# ---------------------------------------------------------------- 環境チェック

def check_env(cfg=None):
    cfg = dict(DEFAULTS, **(cfg or {}))
    ff = ffmpeg_path(cfg)
    out = {"ffmpeg": bool(ff), "ffmpeg_path": ff or "", "voicevox": False,
           "speakers": [], "pixabay": bool(cfg.get("pixabay_key")),
           "pyopenjtalk": False}
    try:
        out["speakers"] = voicevox_speakers()
        out["voicevox"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        import pyopenjtalk  # noqa: F401,PLC0415
        out["pyopenjtalk"] = True
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------- 一連の流れ


def save_plan(pdir, plan):
    with open(os.path.join(pdir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    return plan


def load_plan(pdir):
    path = os.path.join(pdir, "plan.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_images(pdir, plan, api_key, image_type="illustration", progress=None,
                 overwrite=False):
    """各クリップに画像を1枚ずつ割り当てる。同じことばの画像は使い回す。"""
    if not api_key:
        raise RuntimeError("config.json に pixabay_key がありません。"
                           "pixabay.com で無料登録してキーを入れてください")
    cache = {}
    n = len(plan["clips"])
    for c in plan["clips"]:
        if c.get("image") and not overwrite:
            continue
        kw = (c.get("keyword") or plan.get("topic") or "").strip()
        if not kw:
            continue
        if progress:
            progress("画像を探しています %d/%d（%s）" % (c["index"] + 1, n, kw))
        try:
            hits = cache.get(kw)
            if hits is None:
                hits = pixabay_search(kw, api_key, image_type)
                if not hits and plan.get("topic"):
                    hits = pixabay_search(plan["topic"], api_key, image_type)
                cache[kw] = hits
            if not hits:
                continue
            hit = hits[c["index"] % len(hits)]
            path = os.path.join(pdir, "images", "%05d.jpg" % c["index"])
            download(hit["large"], path)
            c["image"] = path
            c["image_id"] = hit["id"]
        except Exception as e:  # noqa: BLE001
            c["image_error"] = str(e)
    return save_plan(pdir, plan)


def make_audio(pdir, plan, speaker, speed=1.0, progress=None, overwrite=False):
    """全クリップの音声を作り、それぞれの秒数を記録する。"""
    n = len(plan["clips"])
    for c in plan["clips"]:
        path = os.path.join(pdir, "audio", "%05d.wav" % c["index"])
        if c.get("audio") and c.get("duration") and os.path.exists(path) and not overwrite:
            continue
        if progress:
            progress("音声を作っています %d/%d" % (c["index"] + 1, n))
        c["duration"] = synthesize(c["speech"], speaker, path, speed)
        c["audio"] = path
    return save_plan(pdir, plan)


def run_all(pdir, plan, cfg, bgm_rules=None, progress=None):
    """音声 → 画像 → 書き出し まで通す。"""
    cfg = dict(DEFAULTS, **(cfg or {}))
    make_audio(pdir, plan, cfg["voicevox_speaker"], cfg.get("voice_speed", 1.0), progress)
    if cfg.get("image_folder"):
        assign_folder_images(pdir, plan, cfg["image_folder"],
                             cfg.get("assign_mode", "order"), progress)
    elif cfg.get("pixabay_key"):
        fetch_images(pdir, plan, cfg["pixabay_key"], cfg["image_type"], progress)
    elif progress:
        progress("画像の取り込み先が未設定なので、画像は入れずに書き出します")
    out, total = render(pdir, plan["clips"], cfg, bgm_rules, progress=progress)
    plan["output"] = out
    plan["total_sec"] = total
    save_plan(pdir, plan)
    return out, total


plan_stats = _plan_stats


def project_dir(name):
    d = os.path.join(WORK, re.sub(r"[^\w\-]", "_", name or "project"))
    os.makedirs(os.path.join(d, "audio"), exist_ok=True)
    os.makedirs(os.path.join(d, "images"), exist_ok=True)
    return d


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            plan = build_plan(f.read())
        print(json.dumps(plan["stats"], ensure_ascii=False, indent=2))
        for c in plan["clips"][:20]:
            print(c["index"], " / ".join(c["caption_lines"]))
    else:
        print(json.dumps(check_env(), ensure_ascii=False, indent=2))
