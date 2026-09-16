#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全台本を一括検査して表で出す。

    python3 check_all.py            # 全部
    python3 check_all.py 02 03      # 番号を指定
"""
import glob, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def sh(*a):
    return subprocess.run([sys.executable, *a], capture_output=True, text=True, cwd=HERE).stdout

def length(path):
    s = open(path, encoding="utf-8").read()
    if "# 台本本文" not in s: return 0, 0.0
    body = s.split("# 台本本文")[1].split("# 概要欄")[0]
    n = sum(len(re.sub(r'^\*\*[^*]+\*\*', '', l))
            for l in body.split("\n") if l.startswith("**") and not l.startswith("**【"))
    sil = sum(float(x) for x in re.findall(r'【無音([\d.]+)秒】', body))
    return n, n / 5 + sil

def num(s, pat, default=None):
    m = re.search(pat, s)
    return m.group(1) if m else default

rows = []
want = sys.argv[1:]
for path in sorted(glob.glob(os.path.join(HERE, "*_原稿.md"))):
    base = os.path.basename(path)
    no = base.split("_")[0]
    if want and no not in want: continue
    n, sec = length(path)
    njd  = sh("njd_check.py", base)
    tel  = sh("telop_wrap.py", base, "--check")
    sty  = sh("style_check.py", base)
    bad_read = "0" if "✅ 読み事故なし" in njd else \
               str(len([l for l in njd.split("\n") if l.strip().startswith("L")]) or "?")
    over = num(tel, r'収まらない文:\s*(\d+)件', "?")
    runs = "0" if "=== ① 文末表現の連続(3回以上は要修正) ===\n  なし" in sty else "×"
    narr = "0" if re.search(r'=== ③ 地の文が続く最長区間\(8以上は要修正\) ===\n  なし', sty) else "×"
    mashita = num(sty, r'…ました\s+\d+回 \(\s*([\d.]+)%\)', "?")
    serifu  = num(sty, r'セリフ \d+/\d+ = (\d+)%', "?")
    short   = num(sty, r'12字以下 \d+\((\d+)%\)', "?")
    ok_len  = "✅" if 17*60 <= sec <= 19*60 + 30 else "⚠"
    rows.append((no, n, f"{int(sec)//60}:{int(sec)%60:02d}", ok_len,
                 bad_read, over, runs, narr, mashita, serifu, short, base))

print(f"{'#':<3}{'字数':>6}{'尺':>7} {'':2}{'読み':>5}{'超過':>5}{'文末':>5}{'地文':>5}"
      f"{'ました':>7}{'セリフ':>7}{'短文':>6}")
print("-" * 64)
ng = 0
for r in rows:
    flag = "" if (r[4] == "0" and r[5] == "0" and r[6] == "0" and r[7] == "0"
                  and r[3] == "✅"
                  and float(r[8] or 99) <= 30 and int(r[9] or 0) >= 50 and int(r[10] or 0) >= 25) else "  ← 要修正"
    if flag: ng += 1
    print(f"{r[0]:<3}{r[1]:>6}{r[2]:>7} {r[3]:2}{r[4]:>5}{r[5]:>5}{r[6]:>5}{r[7]:>5}"
          f"{r[8]+'%':>7}{r[9]+'%':>7}{r[10]+'%':>6}{flag}")
print("-" * 64)
print(f"{len(rows)}本中 {len(rows)-ng}本 合格 / {ng}本 要修正")
print("合格条件: 読み事故0 / テロップ超過0 / 文末3連続0 / 地の文8連続0 /"
      " ました30%以下 / セリフ50%以上 / 短文25%以上 / 尺17:00〜19:30")
