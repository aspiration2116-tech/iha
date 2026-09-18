#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本の文体を定量解析する

  python3 style_check.py 台本.md

朗読台本の素人くささは、語彙ではなく**分布**に出る。
  ① 文末表現の連続 … 「〜ました。」が3回以上続くと、耳が単調さを検知する
  ② セリフ比率     … 地の文が多いほど「説明されている」感じになる
                    ※60%という基準は当方の設定値で、競合台本の実測ではない。
                      状況説明と後日談は本質的に地の文なので、50%台なら許容。
  ③ 話者の連続     … 同じ声が長く続くとラジオになる
  ④ 一文の長さ分布 … 長短のリズムがないと眠くなる
                    ※テロップ2行=36字が上限なので、30字以上は構造的に増やしにくい。
                      12字以下が25%以上あればリズムは成立する。
"""
import re, sys, collections

SPEAKER = re.compile(r'^\*\*([^*]{1,10})\*\*$')

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

def narrators(items):
    """地の文の話者(主人公とナレ)を自動判定する。台本ごとに主人公名が変わるため"""
    c = collections.Counter(sp for sp, t, _ in items if not t.lstrip().startswith("「"))
    main_sp = c.most_common(1)[0][0] if c else None
    return {main_sp, "ナレ"}

def main(path):
    items = load(path)
    NARR = narrators(items)
    narr = [t for sp, t, _ in items if sp in NARR]
    line = [t for sp, t, _ in items if sp not in NARR]
    quoted = [t for sp, t, _ in items if t.lstrip().startswith("「")]
    total = len(items)
    print(f"検査: {path}\n発話 {total} / 地の文+ナレ {len(narr)} / 他話者 {len(line)}\n")

    # ① 文末の連続
    #   マニュアル6章の合格条件は「文末表現の3連続以上 0」で、"地の文の" とは書いていない。
    #   地の文しか見ていなかったため、台詞に化けたモノローグの3連続(台本10 v3 で3か所)が
    #   素通りしていた。地の文と台詞を別々に数えて、どちらも要修正にする。
    print("=== ① 文末表現の連続(3回以上は要修正) ===")
    def runs_of(pairs):
        """(識別子, 文末) の並びから3連続以上を拾う"""
        out, cur = [], []
        for key, e in pairs:
            if cur and cur[-1][1] == e: cur.append((key, e))
            else:
                if len(cur) >= 3: out.append(cur)
                cur = [(key, e)]
        if len(cur) >= 3: out.append(cur)
        return out

    seq = [ending(t) for sp, t, _ in items if sp in NARR and not t.lstrip().startswith("「")]
    runs = runs_of([(t, ending(t)) for sp, t, _ in items
                    if sp in NARR and not t.lstrip().startswith("「")])
    print("  [地の文]")
    if runs:
        for g in sorted(runs, key=lambda x: -len(x)):
            print(f"    「…{g[0][1]}」が {len(g)}回連続")
            for t, _ in g: print(f"       {t[:34]}")
    else: print("    なし")
    # 台詞は「」で始まる行だけを、話者に関係なく並び順で見る。
    # 地の文が1行でも挟まればそこで切れる(耳に届くのは並び順だから)。
    dlg, cur_d = [], []
    for sp, t, _ in items:
        if t.lstrip().startswith("「"): cur_d.append((f"{sp}{t}", ending(t)))
        else:
            dlg += runs_of(cur_d); cur_d = []
    dlg += runs_of(cur_d)
    print("  [台詞]")
    if dlg:
        for g in sorted(dlg, key=lambda x: -len(x)):
            print(f"    「…{g[0][1]}」が {len(g)}回連続")
            for t, _ in g: print(f"       {t[:34]}")
    else: print("    なし")
    c = collections.Counter(seq)
    print(f"  地の文 {len(seq)}文 / 文末の種類 {len(c)}種")
    for e, n in c.most_common(6):
        print(f"    …{e:<10} {n:3d}回 ({n/len(seq)*100:4.1f}%)" + ("  ← 偏りすぎ" if n/len(seq) > .30 else ""))

    # ② セリフ比率
    q = len(quoted); r = q/total
    print(f"\n=== ② セリフ比率 ===\n  セリフ {q}/{total} = {r*100:.0f}%" +
          ("  ← 50%未満は説明的すぎる" if r < .5 else "  ✅ (60%は当方の設定値。50%台は許容)"))

    # ③ 地の文の連続(セリフは声の芝居なので連続しても問題にしない)
    print("\n=== ③ 地の文が続く最長区間(8以上は要修正) ===")
    runs, cur = [], 0
    for sp, t, _ in items:
        if sp in NARR and not t.lstrip().startswith("「"): cur += 1
        else:
            if cur >= 8: runs.append(cur)
            cur = 0
    if cur >= 8: runs.append(cur)
    if runs:
        for n in sorted(runs, reverse=True)[:8]:
            print(f"  地の文が {n}連続" + ("  ← 長い" if n >= 12 else ""))
    else: print("  なし")
    # 台詞に化けたモノローグ(同じ話者が何行続けて喋るか)。
    # ③が地の文しか見ていなかったため、台本10 v3 の23発話連続が素通りした。
    best, cur_sp, cur_n, cur_at = (0, None, 0), None, 0, 0
    for i, (sp, t, _) in enumerate(items):
        if sp == cur_sp: cur_n += 1
        else: cur_sp, cur_n, cur_at = sp, 1, i
        if cur_n > best[0]: best = (cur_n, sp, items[cur_at][1])
    print(f"  同じ話者の最長連続: {best[0]}行  {best[1]} 「{best[2][:24]}」から"
          + ("  ← 15以上はモノローグ。別の声を一つ入れる" if best[0] >= 15 else ""))
    cc = collections.Counter(sp for sp, _, _ in items)
    print("  話者比率: " + " / ".join(f"{k} {v}({v/total*100:.0f}%)" for k, v in cc.most_common()))

    # ④ 一文の長さ
    lens = [len(t) for _, t, _ in items]
    import statistics
    print(f"\n=== ④ 一文の長さ ===\n  中央値 {statistics.median(lens):.0f}字 / 平均 {statistics.mean(lens):.1f}字 / 最長 {max(lens)}字")
    short = sum(1 for l in lens if l <= 12); long_ = sum(1 for l in lens if l >= 30)
    print(f"  12字以下 {short}({short/total*100:.0f}%) / 30字以上 {long_}({long_/total*100:.0f}%)")
    print("  " + ("✅ 長短のリズムあり" if short/total > .25
                  else "← 短い一撃が足りない。体言止めを増やす"))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親_原稿.md")
