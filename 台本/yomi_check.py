#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本のVOICEVOX読み事故チェッカー

  pip install janome
  python3 yomi_check.py 01_披露宴_定食屋の親.md

janome(IPAdic)はVOICEVOXのG2P(OpenJTalk + NAIST-jdic)と同系統の辞書なので、
ここで誤読が出る語はVOICEVOXでもほぼ確実に誤読する。

出力:
  ① 未知語        … 読みが生成できない語。確実に事故る
  ② 危険読み      … 実際の出力が既知の誤読パターンに一致した箇所
  ③ 固有名詞の分割 … 複数トークンに割れている固有名詞。読みは合っても
                     アクセント句が分かれて棒読みになる。辞書登録で直す
"""
import re, sys, collections
from janome.tokenizer import Tokenizer

# (表層の先頭, 出てはいけない読みの先頭, 正しい読み)
BAD = [
    ("行っ","オコナッ","イッ"), ("通っ","トオッ","カヨッ"), ("通う","トオウ","カヨウ"),
    ("今日","コンニチ","キョウ"), ("十分","ジュウブン","ジュップン"), ("白髪","ハクハツ","シラガ"),
    ("通帳","カヨイチョウ","ツウチョウ"), ("入り口","イリクチ","イリグチ"), ("入口","イリクチ","イリグチ"),
    ("義実","ヨシザネ","ギジッ"), ("吾","ワレ","(人名は辞書登録)"), ("刀","カタナ","(入刀は辞書登録)"),
    ("日本","ニッポン","ニホン"), ("来ら","キタラ","コラ"), ("方","ホウ","カタ"),
    ("一日","ツイタチ","イチニチ"), ("辛","ツラ","カラ"), ("上手","カミテ","ジョウズ"),
    ("市場","イチバ","シジョウ"), ("最中","モナカ","サイチュウ"), ("人気","ヒトケ","ニンキ"),
    ("生物","ナマモノ","セイブツ"), ("一時","ヒトトキ","イチジ"), ("六か月","ロクカゲツ","ロッカゲツ"),
    ("八日","ハチニチ","ヨウカ"), ("開い","アイ","ヒライ"), ("止む","トム","ヤム"),
    ("盛","サカ","モ"), ("吐","ツ","ハ"), ("器","キ","ウツワ"), ("背筋","ハイキン","セスジ"),
    ("豚汁","ブタジル","トンジル"), ("暖簾","ダンレン","ノレン"), ("紋付","モンヅケ","モンツキ"),
    ("女房","ジョボウ","ニョウボウ"), ("一言","イチゲン","ヒトコト"), ("代物","ダイブツ","シロモノ"),
    ("出向い","シュッコウイ","デムイ"), ("一張羅","イチハリ","イッチョウラ"), ("宛名","エンメイ","アテナ"),
]
# ここに台本の固有名詞を並べる(分割チェック用)
NAMES = ["中村結衣","中村健一","神崎涼介","神崎政子","鷹野誠一","鷹野物産","東洋通商","みやこ食堂"]
# 誤検知を抑える除外(表層,読み)
IGNORE = {("分","ブン")}

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

def main(path):
    t = Tokenizer()
    lines = load(path)
    unknown, hits = [], []
    splits = collections.Counter()
    for ln, s in lines:
        toks = list(t.tokenize(s))
        surfaces = [tk.surface for tk in toks]
        for tk in toks:
            sf, rd = tk.surface, tk.reading
            if rd in (None, '*'):
                if KANJI.search(sf): unknown.append((ln, sf, s[:46]))
                continue
            if (sf, rd) in IGNORE: continue
            for surf, bad, good in BAD:
                if sf.startswith(surf) and rd.startswith(bad):
                    hits.append((ln, sf, rd, good, s[:50]))
        for nm in NAMES:
            if nm in s and nm not in surfaces:
                splits[nm] += 1

    print(f"検査: {path}  ({len(lines)}行)\n")
    print("=== ① 未知語(確実に事故る) ===")
    print("  なし" if not unknown else "")
    for ln, sf, s in unknown: print(f"  L{ln}  {sf}\n        {s}")
    print("\n=== ② 危険読み ===")
    print("  なし" if not hits else "")
    for ln, sf, rd, good, s in hits: print(f"  L{ln}  「{sf}」→ {rd}   正:{good}\n        {s}")
    print("\n=== ③ 固有名詞がアクセント句に分割(辞書登録で直す) ===")
    print("  なし" if not splits else "")
    for nm, c in splits.most_common(): print(f"  {nm}  ({c}箇所)")
    ng = len(unknown) + len(hits)
    print(f"\n{'❌ 要修正 ' + str(ng) + '件' if ng else '✅ 読み事故なし'}")
    return 1 if ng else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親.md"))
