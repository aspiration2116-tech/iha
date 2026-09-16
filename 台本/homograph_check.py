#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同表記異読語(ホモグラフ)の全数検出

  python3 homograph_check.py 台本.md

方法:
  ① 台本を OpenJTalk に通し、実際に選ばれた発音を得る
  ② 各表層形を naist-jdic に単独で引き、登録されている読みを全部取る
  ③ 読みが2通り以上ある語を「要目視」として、選ばれた読みと候補を並べて出す

語のリストを人間が思いつく方式では必ず漏れる。辞書側から引けば漏れない。
"""
import re, subprocess, sys, tempfile, os, collections

DIC   = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"

def njd(text):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text + "\n"); src = f.name
    tr = src + ".trace"
    subprocess.run(["open_jtalk","-x",DIC,"-m",VOICE,"-ot",tr,"-ow","/dev/null",src],
                   capture_output=True)
    out = open(tr, encoding="utf-8").read(); os.unlink(src); os.unlink(tr)
    if "[Text analysis result]" not in out: return []
    body = out.split("[Text analysis result]")[1].split("[Output label]")[0]
    return [{"s":c[0],"pos":c[1],"pron":c[9],"acc":c[10]}
            for c in (l.split(",") for l in body.strip().split("\n")) if len(c) >= 13]

_cache = {}
def candidates(surface):
    """naist-jdic に登録された surface の全エントリ -> {(発音, アクセント型, 品詞)}"""
    if surface in _cache: return _cache[surface]
    p = subprocess.run(["mecab","-d",DIC,"-a"], input=surface+"\n",
                       capture_output=True, text=True)
    out = set()
    for line in p.stdout.split("\n"):
        if "\t" not in line: continue
        m, feat = line.split("\t", 1)
        if m != surface: continue
        f = feat.split(",")
        if len(f) < 11: continue
        out.add((f[8], f[9], f[0] + "/" + f[1]))
    _cache[surface] = out
    return out

SPEAKER = re.compile(r'\*\*[^*]{1,10}\*\*')

def load(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0] if "# 台本本文" in src else src
    out = []
    for i, l in enumerate(body.split("\n")):
        s = l.strip()
        if not s or s == "---" or s.startswith((">", "#", "|", "`")): continue
        if s.startswith("**【無音"): continue
        s = SPEAKER.sub("", s).replace("**", "")
        s = re.sub(r'\((小声で|心の声)\)', '', s)
        if s: out.append((i + 1, s))
    return out

def norm(p): return p.replace("'", "").replace("’", "")

def main(path):
    lines = load(path)
    amb_read  = collections.defaultdict(list)   # 読みが割れる語
    amb_acc   = collections.defaultdict(list)   # 読みは同じでアクセントが割れる語
    for ln, s in lines:
        for r in njd(s):
            if r["pos"] == "記号": continue
            sf, pron, acc = r["s"], norm(r["pron"]), r["acc"]
            cs = candidates(sf)
            if len(cs) <= 1: continue
            prons = {c[0] for c in cs}
            accs  = {c[1] for c in cs}
            if len(prons) > 1:
                amb_read[(sf, pron, tuple(sorted(prons)))].append((ln, s))
            elif len(accs) > 1:
                amb_acc[(sf, pron, acc, tuple(sorted(accs)))].append((ln, s))

    print(f"検査: {path}  ({len(lines)}行)  dict=naist-jdic\n")
    print(f"=== ① 辞書に複数の読みがある語 …… {len(amb_read)}種(全件を目視して確認) ===\n")
    for (sf, chosen, prons), hits in sorted(amb_read.items(), key=lambda x: -len(x[1])):
        others = [p for p in prons if norm(p) != chosen]
        print(f"■ {sf}  →  採用「{chosen}」   他候補: {' / '.join(others)}   ({len(hits)}箇所)")
        for ln, s in hits[:2]:
            print(f"     L{ln} {s[:52]}")
    print(f"\n=== ② 読みは一意だがアクセント型が複数ある語 …… {len(amb_acc)}種 ===\n")
    for (sf, pron, acc, accs), hits in sorted(amb_acc.items(), key=lambda x: -len(x[1]))[:25]:
        print(f"■ {sf}({pron})  採用 核{acc}   他候補: {' / '.join(a for a in accs if a != acc)}   ({len(hits)}箇所)")
    print(f"\n目視が必要な語: 読み {len(amb_read)}種 / アクセント {len(amb_acc)}種")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親.md")
