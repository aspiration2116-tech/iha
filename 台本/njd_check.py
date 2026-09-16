#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本のVOICEVOX読み・アクセント検査(OpenJTalk実機版)

  apt-get install -y open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
  python3 njd_check.py 台本.md

VOICEVOXのG2Pは OpenJTalk + naist-jdic。本ツールはその実機を直接叩くので、
読み・アクセント型・アクセント句境界が「推測ではなく実測」で得られる。

NJD出力の各フィールド:
  表層, 品詞, 品詞細分類1..3, 活用型, 活用形, 原形, 読み, 発音, アクセント型/モーラ数, 連結規則, 連結フラグ
  ・発音       … 実際に喋られるカナ(連濁・促音・長音の適用後)
  ・アクセント型 … 核の位置。0=平板
  ・連結フラグ  … 0ならここから新しいアクセント句が始まる
"""
import re, subprocess, sys, tempfile, os, collections

DIC   = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"

def njd(text):
    """テキストを OpenJTalk に通し、NJD解析結果を返す"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text + "\n"); src = f.name
    tr = src + ".trace"
    subprocess.run(["open_jtalk", "-x", DIC, "-m", VOICE, "-ot", tr, "-ow", "/dev/null", src],
                   capture_output=True)
    out = open(tr, encoding="utf-8").read()
    os.unlink(src); os.unlink(tr)
    if "[Text analysis result]" not in out: return []
    body = out.split("[Text analysis result]")[1].split("[Output label]")[0]
    rows = []
    for line in body.strip().split("\n"):
        c = line.split(",")
        if len(c) < 13: continue
        rows.append({
            "surface": c[0], "pos": c[1], "pos1": c[2], "pos2": c[3],
            "read": c[8], "pron": c[9], "acc": c[10], "chain": c[12],
        })
    return rows

def norm(p):
    """アクセント核マーカーを除き、長音表記を統一して比較用に正規化"""
    p = p.replace("'", "").replace("\u2019", "")
    p = re.sub(r'([ウオコソトノホモヨロゴゾドボポョ])ウ', lambda m: m.group(1) + "ー", p)
    p = re.sub(r'([ケセテネヘメレゲゼデベペェ])イ', lambda m: m.group(1) + "ー", p)
    return p

def phrases(rows):
    """連結フラグからアクセント句に区切る"""
    out, cur = [], []
    for r in rows:
        if r["pos"] == "記号":
            if cur: out.append(cur); cur = []
            continue
        if r["chain"] == "0" and cur:
            out.append(cur); cur = []
        cur.append(r)
    if cur: out.append(cur)
    return out

SPEAKER = re.compile(r'\*\*[^*]{1,8}\*\*')
KANJI   = re.compile(r'[一-鿿]')

def load(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0] if "# 台本本文" in src else src
    out = []
    for i, l in enumerate(body.split("\n")):
        s = l.strip()
        if not s or s == "---" or s.startswith((">", "#", "|", "-", "`")): continue
        if s.startswith("**【無音"): continue
        s = SPEAKER.sub("", s).replace("**", "")
        s = re.sub(r'\((小声で|心の声)\)', '', s)
        if s: out.append((i + 1, s))
    return out

# 正しい発音が確定している語(ここに足していく)
EXPECT = {
    "中村":"ナカムラ","結衣":"ユイ","健一":"ケンイチ","神崎":"カンザキ","政子":"マサコ",
    "涼介":"リョウスケ","鷹野":"タカノ","誠一":"セイイチ","黒田":"クロダ",
    "通帳":"ツウチョウ","入口":"イリグチ","司会者":"シカイシャ","女房":"ニョウボウ",
    "主賓":"シュヒン","一言":"ヒトコト","半年":"ハントシ","実家":"ジッカ","義母":"ギボ",
    "背筋":"セスジ","宛名":"アテナ","飴":"アメ","箸":"ハシ","髪":"カミ",
    "金":"カネ","司会":"シカイ","白髪":"シラガ","日本":"ニホン",
}
# 固有名詞(1アクセント句にまとまっているべきもの)
NAMES = ["中村結衣","中村健一","神崎涼介","神崎政子","鷹野誠一","鷹野物産","東洋通商","みやこ食堂"]

def main(path):
    lines = load(path)
    unknown, mism, splits = [], [], collections.Counter()
    longph = []
    for ln, s in lines:
        rows = njd(s)
        for r in rows:
            sf, pr = r["surface"], r["pron"]
            if KANJI.search(sf) and (pr in ("*", "") or r["pos1"] == "サ変接続" and pr == "*"):
                unknown.append((ln, sf, s[:46]))
            if sf in EXPECT and norm(pr) != norm(EXPECT[sf]):
                mism.append((ln, sf, pr, EXPECT[sf], s[:46]))
        # 固有名詞のアクセント句分割
        for ph in phrases(rows):
            txt = "".join(x["surface"] for x in ph)
            if len(ph) >= 1:
                mora = sum(int(x["acc"].split("/")[1]) for x in ph if "/" in x["acc"])
                if mora >= 13:
                    longph.append((ln, txt, mora))
        joined = [x["surface"] for x in rows]
        for nm in NAMES:
            if nm in s and nm not in joined:
                # nm が複数アクセント句にまたがるか
                ph_txts = ["".join(x["surface"] for x in p) for p in phrases(rows)]
                if not any(nm in p for p in ph_txts):
                    splits[nm] += 1

    print(f"検査: {path}  ({len(lines)}行)  engine=open_jtalk/naist-jdic\n")
    print("=== ① 発音が生成できない語 ===");  print("  なし" if not unknown else "")
    for ln, sf, s in unknown: print(f"  L{ln}  {sf}\n        {s}")
    print("\n=== ② 期待発音と不一致 ===");  print("  なし" if not mism else "")
    for ln, sf, pr, want, s in mism: print(f"  L{ln}  「{sf}」→ {pr}  期待:{want}\n        {s}")
    print("\n=== ③ 固有名詞が複数アクセント句に分割 ===");  print("  なし" if not splits else "")
    for nm, c in splits.most_common(): print(f"  {nm}  ({c}箇所)  → 辞書登録で1句にまとめる")
    print("\n=== ④ 長すぎるアクセント句(13モーラ超・不自然になりやすい) ===")
    print("  なし" if not longph else "")
    for ln, txt, m in longph[:20]: print(f"  L{ln}  {txt} ({m}モーラ)  → 読点で割る")
    ng = len(unknown) + len(mism)
    print(f"\n{'❌ 要修正 ' + str(ng) + '件' if ng else '✅ 読み事故なし'}")
    return 1 if ng else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親.md"))
