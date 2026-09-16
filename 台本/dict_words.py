#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台本に出る固有名詞を拾い、VOICEVOXに登録すべき語を実機の読みつきで出す。

    python3 dict_words.py 02_墓_三十三回忌_原稿.md ...

話者名と、本文中で繰り返し出る漢字の連なり(人名・社名・寺社名など)を集め、
OpenJTalk(VOICEVOXと同じG2P)にかけて
  ・2つ以上のアクセント句に割れる語   → 登録しないと棒読みになる
  ・読みが複数候補ある語             → 登録しないと事故る
を表にする。**正しい読みは人が決める。**ここは現状の読みを見せるだけ。
"""
import collections, re, sys
from njd_check import njd, phrases

def body_of(path):
    s = open(path, encoding="utf-8").read()
    return s.split("# 台本本文")[1].split("# 概要欄")[0]

def main(paths):
    for path in paths:
        b = body_of(path)
        speakers = collections.Counter(
            m.group(1) for m in re.finditer(r'^\*\*([^*【]{1,8})\*\*', b, re.M))
        # 本文に3回以上出る2〜6字の漢字の連なり
        text = re.sub(r'^\*\*[^*]+\*\*', '', b, flags=re.M)
        runs = collections.Counter(re.findall(r'[一-鿿]{2,6}', text))
        cands = [w for w, c in runs.items() if c >= 3]
        words = list(speakers) + cands
        NUM = set("〇一二三四五六七八九十百千万億半")
        SUF = ("先生", "さん", "様", "ちゃん", "くん", "家", "君")
        seen, out = set(), []
        for w in words:
            if w in seen or len(w) < 2: continue
            if any(c in NUM for c in w): continue          # 数詞は割れて当然
            if w.endswith(SUF) and len(w) > 3: continue    # 「名倉先生」等は語+敬称
            seen.add(w)
            rows = njd(w)
            if not rows: continue
            ph = phrases(rows)
            pron = "".join(r["pron"] for r in rows).replace("'", "")
            if len(ph) >= 2:
                out.append((w, pron, f"{len(ph)}句に割れる"))
        print(f"\n=== {path}")
        if not out:
            print("  登録が要る語なし")
        for w, pron, why in sorted(out, key=lambda x: -len(x[0])):
            print(f"  {w:<8} 現在の読み {pron:<22} {why}")

main(sys.argv[1:])
