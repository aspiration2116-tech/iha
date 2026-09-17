#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""区切り線ごとに、地の文の語尾を縦に並べる。

    python3 endings.py 台本.md

先生が三度言った規則「区切り線から区切り線までは時制をひとつに固定する」を
**目で確かめるための表**です。機械は時制を判定できないので、人が縦読みします。
混在している区切りには ← 混在 が付きます。
"""
import re, sys
from style_check import load, narrators

PAST    = ("ました","ませんでした","でした","だった","ました。","た")
PRESENT = ("ます","ません","です","である","いる")

def tense(s):
    s = s.rstrip("。」』)】!?…・")
    if s.endswith(("ませんでした","でした","ました")): return "過去"
    if s.endswith(("ません","ます","です")): return "現在"
    if re.search(r'[たった]$', s): return "過去"
    if re.search(r'[るいうくすつぬふむゆ]$', s): return "現在"
    return "—"

def main(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0]
    rows = load(path); NARR = narrators(rows)
    blocks, cur, sec = [], [], ""
    for raw in body.split("\n"):
        t = raw.strip()
        if t.startswith("## "): sec = re.sub(r'^##\s*', '', t)
        if t == "---" or t.startswith("> ト書き") or t.startswith("## "):
            if cur: blocks.append((sec, cur)); cur = []
            continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*(.+)$', t)
        if m and m.group(1) in NARR and not m.group(2).lstrip().startswith("「"):
            cur.append(m.group(2).strip())
    if cur: blocks.append((sec, cur))

    bad = 0
    for i, (sec, lines) in enumerate(blocks, 1):
        ts = [tense(l) for l in lines]
        kinds = {x for x in ts if x != "—"}
        mix = len(kinds) > 1
        if mix: bad += 1
        print(f"\n── 区切り{i:2d}  {sec[:22]}{'   ← 混在' if mix else ''}")
        for l, k in zip(lines, ts):
            print(f"   {k}  {l[:44]}")
    print(f"\n{'─'*56}\n区切り {len(blocks)} / 時制が混在 {bad}。**0を目指す。**")

main(sys.argv[1])
