#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本の文体を定量解析する

  python3 style_check.py 台本.md

朗読台本の素人くささは、語彙ではなく**分布**に出る。
  ① 文末表現の連続 … 「〜ました。」が3回以上続くと、耳が単調さを検知する
  ② セリフ比率     … 地の文が多いほど「説明されている」感じになる
  ③ 話者の連続     … 同じ声が長く続くとラジオになる
  ④ 一文の長さ分布 … 長短のリズムがないと眠くなる
"""
import re, sys, collections

SPEAKER = re.compile(r'^\*\*([^*]{1,8})\*\*$')

def load(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0]
    items, sp = [], None
    for raw in body.split("\n"):
        t = raw.strip()
        if not t or t == "---" or t.startswith((">", "#", "|", "`")): continue
        if t.startswith("**【無音"): continue
        m = SPEAKER.match(t)
        if m: sp = m.group(1); continue
        if raw.startswith("　"):
            if items and items[-1][0] == sp and items[-1][2]:
                items[-1] = (sp, items[-1][1] + raw[1:].strip(), True)
            else:
                items.append((sp, raw[1:].strip(), True))
            continue
        m2 = re.match(r'^\*\*([^*]{1,8})\*\*(.+)$', t)
        if m2: items.append((m2.group(1), m2.group(2).strip(), False))
    return items

def ending(s):
    s = s.rstrip("。」』)】!?…")
    for pat in ("ませんでした","ませんでしたか","ました","ません","ています","ていました",
                "でした","です","ます","だった","のです","からです","ください","ですか"):
        if s.endswith(pat): return pat
    return s[-3:] if len(s) >= 3 else s

def main(path):
    items = load(path)
    narr = [t for sp, t, _ in items if sp in ("結衣", "ナレ")]
    line = [t for sp, t, _ in items if sp not in ("結衣", "ナレ")]
    quoted = [t for sp, t, _ in items if t.lstrip().startswith("「")]
    total = len(items)
    print(f"検査: {path}\n発話 {total} / 地の文+ナレ {len(narr)} / 他話者 {len(line)}\n")

    # ① 文末の連続
    print("=== ① 文末表現の連続(3回以上は要修正) ===")
    seq, runs, cur = [ending(t) for sp, t, _ in items if sp in ("結衣","ナレ") and not t.lstrip().startswith("「")], [], []
    for e in seq:
        if cur and cur[-1] == e: cur.append(e)
        else:
            if len(cur) >= 3: runs.append((cur[0], len(cur)))
            cur = [e]
    if len(cur) >= 3: runs.append((cur[0], len(cur)))
    if runs:
        for e, n in sorted(runs, key=lambda x: -x[1]): print(f"  「…{e}」が {n}回連続")
    else: print("  なし")
    c = collections.Counter(seq)
    print(f"  地の文 {len(seq)}文 / 文末の種類 {len(c)}種")
    for e, n in c.most_common(6):
        print(f"    …{e:<10} {n:3d}回 ({n/len(seq)*100:4.1f}%)" + ("  ← 偏りすぎ" if n/len(seq) > .30 else ""))

    # ② セリフ比率
    q = len(quoted); print(f"\n=== ② セリフ比率 ===\n  セリフ {q}/{total} = {q/total*100:.0f}%" +
                          ("  ← 60%を下回ると説明的" if q/total < .6 else "  ✅"))

    # ③ 話者の連続
    print("\n=== ③ 同じ話者が続く最長区間 ===")
    runs, cur, sp0 = [], 0, None
    for sp, t, _ in items:
        if sp == sp0: cur += 1
        else:
            if cur >= 8: runs.append((sp0, cur))
            sp0, cur = sp, 1
    if cur >= 8: runs.append((sp0, cur))
    if runs:
        for s, n in sorted(runs, key=lambda x: -x[1])[:8]:
            print(f"  {s} が {n}発話 連続" + ("  ← 長い" if n >= 14 else ""))
    else: print("  なし")
    cc = collections.Counter(sp for sp, _, _ in items)
    print("  話者比率: " + " / ".join(f"{k} {v}({v/total*100:.0f}%)" for k, v in cc.most_common()))

    # ④ 一文の長さ
    lens = [len(t) for _, t, _ in items]
    import statistics
    print(f"\n=== ④ 一文の長さ ===\n  中央値 {statistics.median(lens):.0f}字 / 平均 {statistics.mean(lens):.1f}字 / 最長 {max(lens)}字")
    short = sum(1 for l in lens if l <= 12); long_ = sum(1 for l in lens if l >= 30)
    print(f"  12字以下 {short}({short/total*100:.0f}%) / 30字以上 {long_}({long_/total*100:.0f}%)")
    print("  " + ("✅ 長短のリズムあり" if short/total > .2 and long_/total > .12
                  else "← 長短の差が小さい。短い一撃と長い説明を交互に置く"))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親_原稿.md")
