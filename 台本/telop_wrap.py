#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本をテロップ(画面字幕)用に自動改行し、長すぎる文を検出する

  python3 telop_wrap.py 台本.md            # 改行済み台本を出力
  python3 telop_wrap.py 台本.md --check     # 要短縮の文だけ一覧

改行位置は OpenJTalk のアクセント句境界から求める。
日本語のアクセント句境界はほぼ文節境界と一致するので、
ここで折れば「助詞だけが行頭に来る」「連体修飾が途中で切れる」事故が減る。

ルール(スマホ視聴前提):
  ・1文=1カード。句点をまたいで1行にしない
  ・1行 最大18文字 / 1カード 最大2行 = 36文字
  ・2行になるときは読点を最優先の折り位置にし、上下の長さを均す
  ・行頭に句読点・閉じカッコを置かない(禁則処理)
  ・3行必要な文は【要短縮】として報告する。台本側を書き直すのが正解
"""
import re, sys, subprocess, tempfile, os

DIC   = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"
MAX_CHARS, MAX_LINES = 18, 2
KINSOKU_HEAD = "、。」』）】!?…・ー"

def njd(text):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text + "\n"); src = f.name
    tr = src + ".trace"
    subprocess.run(["open_jtalk","-x",DIC,"-m",VOICE,"-ot",tr,"-ow","/dev/null",src],
                   capture_output=True)
    out = open(tr, encoding="utf-8").read(); os.unlink(src); os.unlink(tr)
    body = out.split("[Text analysis result]")[1].split("[Output label]")[0]
    return [{"s":c[0],"pos":c[1],"chain":c[12]}
            for c in (l.split(",") for l in body.strip().split("\n")) if len(c) >= 13]

def bunsetsu(text):
    """アクセント句境界で文節に割る。カギカッコ等は解析前に外して後で戻す"""
    head = ""; tail = ""
    m = re.match(r'^([「『（【]*)(.*?)([」』）】。?!…・]*)$', text, re.S)
    if m: head, core, tail = m.group(1), m.group(2), m.group(3)
    else: core = text
    rows = njd(core)
    out, cur = [], ""
    for r in rows:
        if r["pos"] == "記号": cur += r["s"]; continue
        if r["chain"] == "0" and cur: out.append(cur); cur = ""
        cur += r["s"]
    if cur: out.append(cur)
    strip = lambda s: re.sub(r'[、。\s]', '', s)
    if strip("".join(out)) != strip(core): return [text]
    if out: out[0] = head + out[0]; out[-1] = out[-1] + tail
    else: out = [text]
    return out

def split_sentences(text):
    """句点・疑問符・感嘆符で文に割る(閉じカッコは直前の文に付ける)"""
    parts = re.split(r'(?<=[。?!])(?![」』])', text)
    out = []
    for p in parts:
        p = p.strip()
        if not p: continue
        if out and p in ("」", "』"): out[-1] += p
        else: out.append(p)
    return out or [text]

def kinsoku(lines):
    out = []
    for l in lines:
        if out and l and l[0] in KINSOKU_HEAD:
            out[-1] += l[0]; l = l[1:]
        if l: out.append(l)
    return out

def pack(units):
    """単位列を、1行MAX_CHARS以内になるよう貪欲に詰める"""
    lines, cur = [], ""
    for u in units:
        if not cur: cur = u
        elif len(cur) + len(u) <= MAX_CHARS: cur += u
        else: lines.append(cur); cur = u
    if cur: lines.append(cur)
    return lines

def wrap_sentence(s):
    """1文 → (行リスト, 要短縮か)

    折り位置の優先順位:
      ① 読点(、)の直後   ② アクセント句(文節)境界   ③ 強制分割
    読点で折れる限り読点で折る。意味のかたまりが最も壊れにくい。
    """
    if len(s) <= MAX_CHARS:
        return [s], False
    # ① 読点で割る
    segs = [x for x in re.split(r'(?<=、)', s) if x]
    if len(segs) > 1:
        lines = pack(segs)
        if all(len(l) <= MAX_CHARS for l in lines):
            lines = kinsoku(lines)
            return lines, len(lines) > MAX_LINES
    # ② 文節で割る(長すぎる読点区間だけ文節に落とす)
    units = []
    for seg in segs or [s]:
        units.extend([seg] if len(seg) <= MAX_CHARS else bunsetsu(seg))
    lines = kinsoku(pack(units))
    if all(len(l) <= MAX_CHARS for l in lines):
        return lines, len(lines) > MAX_LINES
    # ③ 強制分割
    out = []
    for l in lines:
        while len(l) > MAX_CHARS:
            out.append(l[:MAX_CHARS]); l = l[MAX_CHARS:]
        if l: out.append(l)
    return out, True

def cards(text):
    """1発話 → [(カード行リスト, 要短縮)]"""
    out = []
    for s in split_sentences(text):
        ls, over = wrap_sentence(s)
        for i in range(0, len(ls), MAX_LINES):
            out.append((ls[i:i+MAX_LINES], over))
    return out

SPEAKER = re.compile(r'^(\*\*[^*]{1,8}\*\*)(.*)$')

def iter_body(path):
    src = open(path, encoding="utf-8").read()
    head, rest = src.split("# 台本本文", 1)
    body, tail = rest.split("# 概要欄", 1)
    return head, body, tail

def main(path, check=False):
    head, body, tail = iter_body(path)
    out, over_list = [head, "# 台本本文"], []
    for line in body.split("\n"):
        s = line.rstrip(); t = s.strip()
        if not t or t.startswith((">", "#", "|", "`")) or t == "---" or t.startswith("**【無音"):
            out.append(s); continue
        m = SPEAKER.match(t)
        if not m: out.append(s); continue
        sp, txt = m.group(1), m.group(2).strip()
        if not txt: out.append(s); continue
        out.append(sp)
        first = True
        for card, over in cards(txt):
            if not first: out.append("")
            first = False
            for l in card: out.append(f"　{l}")
            if over: over_list.append(txt)
    out.append("# 概要欄" + tail)
    if check:
        print(f"【要短縮】テロップ2行(36字)に収まらない文: {len(set(over_list))}件\n")
        for t in dict.fromkeys(over_list): print(f"  ({len(t)}字) {t}")
        print("\n" + ("✅ すべてテロップ2行に収まる" if not over_list else "❌ 上記を短く書き直す"))
    else:
        print("\n".join(out))

if __name__ == "__main__":
    a = sys.argv[1:] or ["01_披露宴_定食屋の親.md"]
    main(a[0], "--check" in a)
