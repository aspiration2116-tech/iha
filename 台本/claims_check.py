#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ヘッダの自己申告と本文を突き合わせる。

    python3 claims_check.py 台本.md

先生が3本の再採点で同じ減点をしました。**変更表・伏線表に書いた引用が本文に無い。**
「入れた」と書いた台詞が無い、「削った」と書いた語がまだある、
伏線表の設置側が本文に存在しない —— どれも読めば分かるのに、毎回見落とされます。

やること:
  ① ヘッダ(`# 台本本文` より前)の「…」で囲まれた引用を全部抜く
  ② その引用が本文にあるか grep する
  ③ 無ければ「申告のみ(本文に無い)」として出す
  ④ 章の配分をマニュアルの設計値と比べる

**引用は本文の表記どおりに書くこと。**要約して書くと、この検査は通りません。
それでいいのです。要約した申告は、先生に「嘘」と判定されます。
"""
import re, sys

# マニュアル1章の設計値(秒)
DESIGN = {
    "コールドオープン": 10, "約束": 20, "状況説明": 95, "加害": 270,
    "越えてはいけない一線": 40, "受諾": 50, "準備": 145,
    "反転": 390, "転落": 70, "締め": 150,
}
# 台本01 v17 の実測: 発話6,137字 / 無音10.1秒 / 尺20:37(=1,237秒)。
# 4.96字/秒 は無音込みの実効値なので、無音を別に足すなら発話だけの速度を使う。
RATE = 5.002  # 字/秒(発話のみ)
DESIGN_TOTAL = sum(DESIGN.values())  # 1,240秒 = 20:40

def main(path):
    src = open(path, encoding="utf-8").read()
    head, rest = src.split("# 台本本文", 1)
    body = rest.split("# 概要欄")[0]
    # 本文の発話テキストだけ(話者名・ト書きを除く)
    spoken = "\n".join(re.sub(r'^\*\*[^*]+\*\*', '', l)
                       for l in body.split("\n") if l.startswith("**"))
    plain = spoken.replace("、", "").replace("。", "").replace(" ", "")

    # タイトル・サムネの引用は本文に無くて当然なので除く
    scan = head
    for sec in ("## タイトル", "## サムネ"):
        if sec in scan:
            i = scan.index(sec)
            j = scan.find("\n## ", i + 1)
            scan = scan[:i] + (scan[j:] if j > 0 else "")
    # 「旧 → 新」「旧|新」の行は、右側(=本文に入れたはずのもの)だけを検査する
    picked = []
    for line in scan.split("\n"):
        seg = line
        if "→" in line:
            seg = line.rsplit("→", 1)[1]
        elif line.count("|") >= 3:
            cells = [c for c in line.split("|") if c.strip()]
            seg = cells[-1] if cells else line
        picked += re.findall(r'「([^「」\n]{4,60})」', seg)
    quotes = [re.sub(r'\*+', '', q).strip() for q in picked]
    LABEL = re.compile(r'^(伏線\d+組|[0-9０-９]+[点件本組行秒字]|[ぁ-んァ-ヴー一-鿿]{2,6}の(末路|型|話))$')
    quotes = [q for q in quotes if q and not LABEL.match(q)]
    seen, missing = set(), []
    for q in quotes:
        if q in seen: continue
        seen.add(q)
        key = q.replace("、", "").replace("。", "").replace(" ", "")
        if key not in plain:
            missing.append(q)

    print(f"検査: {path}")
    print(f"\n=== ① ヘッダの引用 {len(seen)}件 / 本文に無いもの {len(missing)}件")
    for q in missing:
        print(f"  ✗ 「{q[:48]}」")
    if not missing:
        print("  ✅ ヘッダの引用はすべて本文にある")

    parts = re.split(r'\n## 【[^】]+】', body)
    titles = re.findall(r'\n## 【[^】]+】(.*)', body)
    secs = []
    for title, sec in zip(titles, parts[1:]):
        lines = [l for l in sec.split("\n") if l.startswith("**") and not l.startswith("**【")]
        n = sum(len(re.sub(r'^\*\*[^*]+\*\*', '', l)) for l in lines)
        sil = sum(float(x) for x in re.findall(r'【無音([\d.]+)秒】', sec))
        secs.append((title, n / RATE + sil))

    # 設計値は総尺20:40のときの秒数。台本ごとに尺は違うので、
    # 設計値をその台本の尺に比例させてから比べる(見るのは配分であって絶対秒ではない)。
    total = sum(d for _, d in secs)
    scale = total / DESIGN_TOTAL
    print(f"\n=== ② 章の配分(設計値を総尺{int(total)//60}:{int(total)%60:02d}に按分して比較)")
    over = 0
    for title, d in secs:
        key = next((k for k in DESIGN if k in title), None)
        if not key: continue
        tgt = DESIGN[key] * scale
        diff = d - tgt
        mark = ""
        if abs(diff) >= 45:
            mark = f"  ← 設計{int(tgt)//60}:{int(tgt)%60:02d}から{diff:+.0f}秒"
            over += 1
        print(f"  {int(d)//60}:{int(d)%60:02d}  {title.strip()[:20]}{mark}")
    # ③ 数の申告(「ト書き29本」「無音13箇所」「話者11人」)を機械で数え直す。
    #   ①は「」の引用しか見ないので、数の食い違いは素通りしていた。
    #   台本08の採点で「機械が見ていない列に食い違いが6件移っただけ」と指摘された。
    body_lines = body.split("\n")
    actual = {
        # 「> ト書き:」で始まる行だけを数える(作画への注意書きの「>」は含めない)
        "ト書き": sum(1 for l in body_lines if l.lstrip().startswith("> ト書き")),
        "無音":   len(re.findall(r'【無音[\d.]+秒】', body)),
        "話者":   len({m.group(1) for m in
                      (re.match(r'^\*\*([^*【]+)\*\*', l) for l in body_lines) if m}),
        "発話":   sum(1 for l in body_lines
                      if l.startswith("**") and not l.startswith("**【")),
    }
    UNIT = {"ト書き": "本|枚", "無音": "箇所|か所|カ所", "話者": "人", "発話": "行"}
    # 章ごとの部分的な申告や、変更前後を並べた行は全体の数ではないので見ない
    CHAP = ("コールドオープン", "約束", "状況説明", "加害", "一線", "受諾",
            "準備", "反転", "転落", "締め")
    num = []
    for line in head.split("\n"):
        # 表の行は「指摘の中身」を書く場所で、台本全体の数ではない
        if line.lstrip().startswith("|"):
            continue
        if "→" in line or any(c in line for c in CHAP):
            continue
        for key, units in UNIT.items():
            for m in re.finditer(key + r'[^。|\n]{0,10}?([0-9,]+) *(?:' + units + r')(.?)',
                                 line):
                if m.group(2) in ("も", "と"):   # 「1人も増えていない」は数の申告ではない
                    continue
                claimed = int(m.group(1).replace(",", ""))
                if claimed != actual[key]:
                    num.append((key, claimed, actual[key], m.group(0)[:30]))

    print("\n=== ③ 数の申告(機械で数え直す)")
    print(f"  ト書き {actual['ト書き']}本 / 無音 {actual['無音']}箇所 / "
          f"話者 {actual['話者']}人 / 発話 {actual['発話']}行")
    for key, c, a, txt in num:
        print(f"  ✗ 申告「{txt}」→ 実際は {a}")
    if not num:
        print("  ✅ 数の申告はすべて本文と合う")

    print(f"\n{'─'*56}")
    print(f"申告の食い違い {len(missing)}件 / 配分の逸脱 {over}章 / "
          f"数の食い違い {len(num)}件。**すべて0を目指す。**")
    sys.exit(1 if (missing or over or num) else 0)

main(sys.argv[1])
