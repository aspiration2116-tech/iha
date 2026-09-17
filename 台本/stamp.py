#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章見出しの時刻とヘッダの尺・字数を、本文の実測から書き直す。

    python3 stamp.py 台本.md            # 書き換える
    python3 stamp.py 台本.md --check    # ずれを表示するだけ

手で書いた時刻は必ずずれます。行を1行足すたびに以降の全章がずれるからです。
**改稿のたびに最後に必ず実行してください。**

数え方は台本01の実測に合わせた 4.96字/秒 + 無音の実尺。
"""
import re, sys

# 台本01 v17 の実測: 発話6,137字 / 無音10.1秒 / 尺20:37(=1,237秒)
#   4.96字/秒 は「無音込みの実効値」なので、これに無音を足すと二重計上になる。
#   ここでは発話だけの速度を使い、無音は別に足す。6137/5.002 + 10.1 = 1,237秒 で一致。
RATE = 5.002  # 字/秒(発話のみ)

def measure(section):
    lines = [l for l in section.split("\n")
             if l.startswith("**") and not l.startswith("**【")]
    n = sum(len(re.sub(r'^\*\*[^*]+\*\*', '', l)) for l in lines)
    sil = sum(float(x) for x in re.findall(r'【無音([\d.]+)秒】', section))
    return n, n / RATE + sil

def mmss(x):
    x = int(round(x / 5.0) * 5)          # 5秒刻み
    return f"{x//60}:{x%60:02d}"

def main(path, check=False):
    src = open(path, encoding="utf-8").read()
    head, rest = src.split("# 台本本文", 1)
    main_, tail = rest.split("# 概要欄", 1)

    parts = re.split(r'(\n## 【[^】]+】)', main_)
    t, out, rows = 0.0, parts[0], []
    for i in range(1, len(parts), 2):
        hdr, body = parts[i], parts[i + 1]
        title = re.sub(r'\n## 【[^】]+】', '', hdr)
        old = re.search(r'【([^】]+)】', hdr).group(1)
        n, d = measure(body)
        new = f"{mmss(t)}-{mmss(t + d)}"
        rows.append((title.strip(), n, round(d), old, new))
        out += f"\n## 【{new}】{title}" + body
        t += d

    total_n = sum(r[1] for r in rows)
    print(f"{path}")
    ng = 0
    for title, n, d, old, new in rows:
        mark = "" if old == new else f"  ← {old}"
        if old != new: ng += 1
        print(f"  {n:5d}字 {d:4d}秒  【{new}】{title}{mark}")
    print(f"  合計 {total_n:,}字 / {int(t)//60}分{int(t)%60}秒"
          f"{'  (章見出しのずれ ' + str(ng) + '章)' if ng else '  ✅ 章見出しは実測と一致'}")

    # ヘッダの尺・字数
    m = re.search(r'\*\*尺\*\*\s*([^/]+)/\s*\*\*読み上げ\*\*\s*([\d,]+)字', head)
    if m:
        cur = (m.group(1).strip(), m.group(2).replace(",", ""))
        want = (f"{int(t)//60}分{int(t)%60}秒", str(total_n))
        if cur[1] != want[1] or ng:
            print(f"  ヘッダ申告 {cur[0]} / {cur[1]}字  → 実測 {want[0]} / {int(want[1]):,}字")
    if check:
        sys.exit(1 if ng else 0)

    new_head = head
    if m:
        new_head = (head[:m.start()]
                    + f"**尺** {int(t)//60}分{int(t)%60}秒(無音込み・推定。収録前にVOICEVOXで実測)"
                      f" / **読み上げ** {total_n:,}字"
                    + head[m.end():])
    open(path, "w", encoding="utf-8").write(new_head + "# 台本本文" + out + "# 概要欄" + tail)
    print("  → 書き換えました")

a = [x for x in sys.argv[1:] if not x.startswith("-")]
main(a[0], "--check" in sys.argv)
