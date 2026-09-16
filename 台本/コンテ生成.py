#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""収録台本から「動くコンテ(尺見本)」の動画を書き出す。

  python3 台本/コンテ生成.py            # 冒頭(01〜02章)だけ
  python3 台本/コンテ生成.py --all      # 全章(約34分)

声も映像もまだ無い段階で、テロップの出方と尺の流れを目で確認するためのもの。
台詞は字幕として、実際に喋る速さで切り替わる。
編集のとき、これをタイムラインの一番下に敷いて目安にしてもいい。

出力: 台本/素材/コンテ_冒頭.mp4
"""
import io, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 素材生成 as A          # 描画関数を再利用

BASE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(BASE, "収録台本_沖縄旅行の注意点.md")
OUTDIR = os.path.join(BASE, "素材")

CPM = 300.0        # 字/分
GAP = 0.45         # 台詞と台詞の間
PAUSE = 1.6        # (間)


def parse():
    t = io.open(SCRIPT, encoding="utf-8").read()
    body = t.split("# 本編", 1)[1].split("# 収録前の最終チェック")[0]
    parts = re.split(r"■\s*(\d+)\s+(.+?)\s+(\d{2}:\d{2})〜(\d{2}:\d{2})", body)
    chapters = []
    for i in range(1, len(parts), 5):
        num, title, text = parts[i], parts[i + 1].strip(), parts[i + 4]
        # 映像メモ(章ヘッダ直後の「映像:」行)
        mv = re.search(r"映像:\s*(.+)", text)
        events = []
        for line in text.split("\n"):
            line = line.rstrip()
            m = re.match(r"^(夫|妻)　　(.+)$", line)
            if m:
                say = re.sub(r"\*\*|【.*?】", "", m.group(2)).strip()
                if say:
                    events.append(("say", m.group(1), say))
                continue
            if "(間" in line or "（間" in line:
                events.append(("pause", "", ""))
                continue
            mt = re.match(r"^▷テロップ[「\s](.*?)[」]?$", line.strip())
            if mt and mt.group(1).strip():
                events.append(("telop", "", mt.group(1).strip()))
        chapters.append({"num": num, "title": title,
                         "shot": (mv.group(1).strip() if mv else ""), "events": events})
    return chapters


def frame(ch, telop, speaker, line, t):
    img = A.gradient((A.W, A.H), (16, 20, 28), (30, 38, 52))
    d = ImageDraw.Draw(img)

    # 映像が入る場所のガイド
    d.rectangle([60, 150, A.W - 60, A.H - 300], outline=(255, 255, 255, 40), width=3)
    A.plain(d, (A.W // 2, 300), "【 ここに映像 】", A.font(46), fill=(255, 255, 255, 90), anchor="ma")
    if ch["shot"]:
        f = A.fit(d, ch["shot"], A.W - 300, start=40)
        A.plain(d, (A.W // 2, 366), ch["shot"], f, fill=(255, 255, 255, 70), anchor="ma")

    # 章とタイムコード
    A.plain(d, (60, 62), "%s  %s" % (ch["num"], ch["title"]), A.font(40), fill=(255, 255, 255, 190))
    A.plain(d, (A.W - 60, 62), "%02d:%02d" % (int(t) // 60, int(t) % 60), A.font(44),
            fill=(255, 221, 51, 230), anchor="ra")
    A.plain(d, (A.W - 60, A.H - 46), "動くコンテ(尺見本) — 声・映像は収録後に差し替え",
            A.font(28), fill=(255, 255, 255, 90), anchor="rs")

    # テロップ(実際の見え方)
    if telop:
        f = A.fit(d, telop, A.W - 300, start=96)
        A.bold(d, (A.W // 2, 520), telop, f, fill=A.WHITE, ow=9, bw=4, anchor="mm")

    # 台詞(字幕)
    if line:
        col = (120, 200, 255, 255) if speaker == "夫" else (255, 160, 190, 255)
        A.bold(d, (90, A.H - 232), speaker, A.font(46), fill=col, ow=5)
        f = A.fit(d, line, A.W - 280, start=62)
        A.bold(d, (180, A.H - 236), line, f, fill=A.WHITE, ow=7, bw=3)
    return img.convert("RGB")


def build(chapters, out_name):
    tmp = tempfile.mkdtemp()
    shots, t, telop = [], 0.0, ""
    for ch in chapters:
        for kind, sp, txt in ch["events"]:
            if kind == "telop":
                telop = txt
                dur = 0.6
                sp2, line = "", ""
            elif kind == "pause":
                dur = PAUSE
                sp2, line = "", ""
            else:
                dur = len(txt) / CPM * 60 + GAP
                sp2, line = sp, txt
            p = os.path.join(tmp, "f%04d.png" % len(shots))
            frame(ch, telop, sp2, line, t).save(p)
            shots.append((p, dur))
            t += dur

    lst = os.path.join(tmp, "list.txt")
    with io.open(lst, "w", encoding="utf-8") as f:
        for p, dur in shots:
            f.write("file '%s'\nduration %.3f\n" % (p, dur))
        f.write("file '%s'\n" % shots[-1][0])

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = os.path.join(OUTDIR, out_name)
    os.makedirs(OUTDIR, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-r", "12", out],
                   check=True)
    return out, t, len(shots)


if __name__ == "__main__":
    chs = parse()
    if "--all" in sys.argv:
        out, dur, n = build(chs, "コンテ_全編.mp4")
    else:
        out, dur, n = build(chs[:2], "コンテ_冒頭.mp4")
    print("%s  %.0f秒 / %dカット / %.1fMB" % (out, dur, n, os.path.getsize(out) / 1e6))
