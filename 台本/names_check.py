#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台本をまたいだ人物名の衝突を出す。

    python3 names_check.py

1本ずつ見ている限り誰も気づきません。連投すると視聴者が混ざります。
実例:妊娠回のラストで生まれる娘が「佳奈」、次回予告で出る浮気回の主人公も「佳奈」。
"""
import collections, glob, os, re

def speakers(path):
    body = open(path, encoding="utf-8").read().split("# 台本本文")[1].split("# 概要欄")[0]
    return {m.group(1) for m in re.finditer(r'^\*\*([^*【]{1,8})\*\*', body, re.M)}

def names_in_text(path):
    """本文に出る人名らしい語(姓+名、カタカナ名、〜さん)"""
    body = open(path, encoding="utf-8").read().split("# 台本本文")[1].split("# 概要欄")[0]
    t = re.sub(r'^\*\*[^*]+\*\*', '', body, flags=re.M)
    out = set()
    out |= set(re.findall(r'([一-鿿]{2,4})さん', t))
    out |= set(re.findall(r'([一-鿿]{2,4})ちゃん', t))
    out |= set(re.findall(r'名前は、([ぁ-んァ-ヴー一-鿿]{2,4})', t))
    return out

GENERIC = {"お母","お父","おじい","おばあ","お義母","お義父","支配人","常務","課長",
           "先生","会長","部長","社長","おばちゃん","おじちゃん","看護","担当"}

owner, where = {}, collections.defaultdict(set)
for path in sorted(glob.glob("*_原稿.md")):
    no = os.path.basename(path).split("_")[0]
    for n in speakers(path) | names_in_text(path):
        if len(n) < 2 or n in GENERIC: continue
        where[n].add(no)

dup = {n: sorted(v) for n, v in where.items() if len(v) > 1}
print("台本をまたいで同じ名前が出る語\n" + "─" * 46)
if not dup:
    print("  なし ✅")
for n, v in sorted(dup.items(), key=lambda x: -len(x[1])):
    print(f"  {n:<8} {' / '.join(v)}")
print(f"\n{len(dup)}件。**登場人物の名前は台本ごとに全部変えること。**")
print("同じ役(ナレ・親族A など)の重複は問題ありません。")
