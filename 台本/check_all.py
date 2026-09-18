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
    tpath = path.replace("_原稿.md", ".md")
    sty  = sh("style_check.py", base)
    bad_read = "0" if "✅ 読み事故なし" in njd else \
               str(len([l for l in njd.split("\n") if l.strip().startswith("L")]) or "?")
    over = num(tel, r'収まらない文:\s*(\d+)件', "?")
    def section_ok(text, head):
        m = re.search(re.escape(head) + r'\s*\n\s*(.*)', text)
        return "0" if (m and m.group(1).strip() == "なし") else "×"
    def runs_ok(text):
        # ①は v2 で [地の文]/[台詞] の小見出しに分かれた。両方が「なし」なら0。
        m = re.search(r'=== ① 文末表現の連続.*?===\n(.*?)\n\s*地の文 ', text, re.S)
        if not m: return "?"
        block = m.group(1)
        subs = re.findall(r'\[[^\]]+\]\s*\n\s*(\S+)', block)
        return "0" if subs and all(x == "なし" for x in subs) else "×"
    runs = runs_ok(sty)
    narr = section_ok(sty, "=== ③ 地の文が続く最長区間(8以上は要修正) ===")
    mashita = num(sty, r'…ました\s+\d+回 \(\s*([\d.]+)%\)', "?")
    serifu  = num(sty, r'セリフ \d+/\d+ = (\d+)%', "?")
    short   = num(sty, r'12字以下 \d+\((\d+)%\)', "?")
    # 競合実測: 17〜19分=103,500 / 19〜21分=100,000 / 21分以上=89,000 / 17分未満=50,000
    ok_len = "◎" if 17*60 <= sec <= 19*60 else ("○" if sec <= 21*60 else "⚠")
    rows.append((no, n, f"{int(sec)//60}:{int(sec)%60:02d}", ok_len,
                 bad_read, over, runs, narr, mashita, serifu, short, base,
                 "✓" if os.path.exists(tpath) else "—"))

print(f"{'#':<3}{'字数':>6}{'尺':>7} {'':2}{'読み':>5}{'超過':>5}{'文末':>5}{'地文':>5}"
      f"{'ました':>7}{'セリフ':>7}{'短文':>6}{'本番':>5}")
print("-" * 64)
ng = 0
for r in rows:
    flag = "" if (r[4] == "0" and r[5] == "0" and r[6] == "0" and r[7] == "0"
                  and r[3] in ("◎", "○")
                  and float(r[8] or 99) <= 30 and int(r[9] or 0) >= 50 and int(r[10] or 0) >= 25) else "  ← 要修正"
    if flag: ng += 1
    print(f"{r[0]:<3}{r[1]:>6}{r[2]:>7} {r[3]:2}{r[4]:>5}{r[5]:>5}{r[6]:>5}{r[7]:>5}"
          f"{r[8]+'%':>7}{r[9]+'%':>7}{r[10]+'%':>6}{r[12]:>5}{flag}")
print("-" * 64)
print(f"{len(rows)}本中 {len(rows)-ng}本 合格 / {ng}本 要修正")
print("合格条件: 読み事故0 / テロップ超過0 / 文末3連続0 / 地の文8連続0 /"
      " ました30%以下 / セリフ50%以上 / 短文25%以上")
print("尺 ◎=17:00〜19:00(中央値103,500の最上位帯) ○=〜21:00 ⚠=帯の外")
