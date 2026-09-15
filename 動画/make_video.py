#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テロップ台本から絵コンテ動画(アニマティック)を生成する

  python3 make_video.py ../台本/01_披露宴_定食屋の親.md out.mp4

やること:
  ① テロップ台本をカード単位に解析
  ② 話者ごとに音声を割り当てて Open JTalk で合成、長さを実測
  ③ カードごとに 1920x1080 のテロップ画像を描画
  ④ 音声の実尺に合わせて ffmpeg で連結

これは「完成動画」ではなく、**尺・間・テロップを実物で確認するための土台**。
漫画イラストを差し替え、音声を VOICEVOX に差し替えれば本番になる。
"""
import os, re, sys, subprocess, json, math, shutil

DIC   = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
HERE  = os.path.dirname(os.path.abspath(__file__))
FONT  = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
W, H  = 1920, 1080

# 話者 → (音声ファイル, 話速, 追加半音, 色)
CAST = {
    "結衣":     ("voices/mei/mei_normal.htsvoice",     1.00,  0.0, (255, 255, 255)),
    "政子":     ("voices/mei/mei_happy.htsvoice",      1.08,  0.3, (255, 170, 190)),
    "涼介":     ("voices/takumi/takumi_normal.htsvoice",1.02,  0.0, (150, 200, 255)),
    "父":       ("voices/takumi/takumi_sad.htsvoice",   0.92, -0.2, (255, 215, 150)),
    "鷹野":     ("hts/nitech.htsvoice",                 0.88, -0.3, (200, 255, 210)),
    "黒田":     ("voices/takumi/takumi_happy.htsvoice", 1.00,  0.0, (200, 200, 200)),
    "プランナー":("voices/mei/mei_bashful.htsvoice",    1.00,  0.0, (200, 200, 200)),
    "親族":     ("voices/mei/mei_bashful.htsvoice",     0.95,  0.0, (200, 200, 200)),
    "ナレ":     ("voices/mei/mei_normal.htsvoice",      0.98,  0.0, (235, 235, 235)),
}
DEFAULT = CAST["結衣"]

def parse(path):
    """テロップ台本 → [{'kind':..., ...}]"""
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0]
    items, section, note = [], "", ""
    speaker, lines = None, []
    def flush():
        nonlocal speaker, lines, note
        if speaker and lines:
            items.append({"kind": "card", "speaker": speaker, "lines": lines[:],
                          "section": section, "note": note})
        speaker, lines = None, []
    for raw in body.split("\n"):
        l = raw.rstrip()
        t = l.strip()
        if t.startswith("## "):
            flush()
            m = re.match(r'##\s*【([^】]*)】\s*(.*)', t)
            section = (m.group(2) if m else t[3:]).strip(); note = ""
            continue
        if t.startswith("### "):
            flush(); continue
        if t.startswith("> ト書き"):
            flush(); note = re.sub(r'^>\s*ト書き[::]\s*', '', t).strip(); continue
        if t.startswith("> "):
            continue
        m = re.match(r'^\*\*【無音([\d.]+)秒】\*\*$', t)
        if m:
            flush(); items.append({"kind": "silence", "sec": float(m.group(1))}); continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*$', t)
        if m:
            flush(); speaker = m.group(1); continue
        if l.startswith("　"):
            lines.append(l[1:].strip()); continue
        if not t:
            continue
    flush()
    return items

def synth(text, voice, rate, fm, out):
    vp = voice if os.path.isabs(voice) else os.path.join(HERE, voice)
    tf = out + ".txt"
    open(tf, "w", encoding="utf-8").write(text + "\n")
    subprocess.run(["open_jtalk", "-x", DIC, "-m", vp, "-r", str(rate),
                    "-fm", str(fm), "-ow", out, tf], capture_output=True)
    os.unlink(tf)
    return dur(out)

def dur(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 0.0

def render(item, path, idx, total):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), (11, 13, 20))
    d = ImageDraw.Draw(img)
    # 背景グラデーション
    for y in range(0, H, 4):
        v = int(11 + 26 * (1 - y / H) ** 2)
        d.rectangle([0, y, W, y + 4], fill=(v, v + 2, v + 9))
    f_sec  = ImageFont.truetype(FONT, 30)
    f_note = ImageFont.truetype(FONT, 38)
    f_sp   = ImageFont.truetype(FONT, 40)
    f_tel  = ImageFont.truetype(FONT, 78)
    # セクション名(左上)
    d.text((56, 44), item.get("section", ""), font=f_sec, fill=(120, 128, 150))
    d.text((W - 56, 44), f"{idx}/{total}", font=f_sec, fill=(90, 96, 115), anchor="ra")
    # 絵の指示(中央のプレースホルダ枠)
    box = (150, 160, W - 150, 640)
    d.rounded_rectangle(box, 18, outline=(52, 58, 78), width=3)
    note = item.get("note") or ""
    if note:
        d.text(((box[0] + box[2]) // 2, 200), "▼ ここに入る絵", font=f_sec,
               fill=(110, 118, 140), anchor="ma")
        wrapped, cur = [], ""
        for ch in note:
            cur += ch
            if len(cur) >= 26: wrapped.append(cur); cur = ""
        if cur: wrapped.append(cur)
        for i, ln in enumerate(wrapped[:6]):
            d.text(((box[0] + box[2]) // 2, 270 + i * 58), ln, font=f_note,
                   fill=(168, 178, 202), anchor="ma")
    # 話者
    sp = item["speaker"]
    col = CAST.get(sp, DEFAULT)[3]
    d.text((W // 2, 726), sp, font=f_sp, fill=col, anchor="ma")
    # テロップ(縁取り)
    y = 806
    for ln in item["lines"]:
        for dx in (-4, -2, 0, 2, 4):
            for dy in (-4, -2, 0, 2, 4):
                if dx or dy:
                    d.text((W // 2 + dx, y + dy), ln, font=f_tel, fill=(0, 0, 0), anchor="ma")
        d.text((W // 2, y), ln, font=f_tel, fill=(255, 255, 255), anchor="ma")
        y += 104
    img.save(path)

def main(script, outfile):
    work = os.path.join(HERE, "build")
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    items = parse(script)
    cards = [i for i in items if i["kind"] == "card"]
    print(f"カード {len(cards)} / 無音 {len(items)-len(cards)}")
    seq, n, total_sec = [], 0, 0.0
    for it in items:
        if it["kind"] == "silence":
            wav = f"{work}/s{n:04d}.wav"
            subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-f", "lavfi", "-i",
                            f"anullsrc=r=48000:cl=mono", "-t", str(it["sec"]), wav],
                           capture_output=True)
            if seq: seq[-1]["sec"] += it["sec"]; seq[-1]["wavs"].append(wav)
            n += 1; total_sec += it["sec"]; continue
        n += 1
        voice, rate, fm, _ = CAST.get(it["speaker"], DEFAULT)
        text = "".join(it["lines"])
        wav = f"{work}/a{n:04d}.wav"
        sec = synth(text, voice, rate, fm, wav)
        pad = f"{work}/p{n:04d}.wav"
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=48000:cl=mono", "-t", "0.28", pad], capture_output=True)
        png = f"{work}/f{n:04d}.png"
        render(it, png, len([s for s in seq]) + 1, len(cards))
        seq.append({"png": png, "sec": sec + 0.28, "wavs": [wav, pad]})
        total_sec += sec + 0.28
        if n % 40 == 0: print(f"  ... {n}/{len(items)}  ({total_sec/60:.1f}分)")
    # 画像の連結リスト
    with open(f"{work}/frames.txt", "w") as f:
        for s in seq:
            f.write(f"file '{s['png']}'\nduration {s['sec']:.3f}\n")
        f.write(f"file '{seq[-1]['png']}'\n")
    # 音声の連結リスト
    with open(f"{work}/audio.txt", "w") as f:
        for s in seq:
            for w in s["wavs"]: f.write(f"file '{w}'\n")
    print(f"合計 {total_sec/60:.2f}分 — 結合中…")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", f"{work}/audio.txt", "-c:a", "aac", "-b:a", "128k",
                    f"{work}/all.m4a"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", f"{work}/frames.txt", "-i", f"{work}/all.m4a",
                    "-fps_mode", "cfr", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "24", "-r", "24",
                    "-c:a", "copy", "-shortest", outfile], check=True)
    print(f"✅ {outfile}  ({dur(outfile)/60:.2f}分, {os.path.getsize(outfile)/1e6:.1f}MB)")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "../台本/01_披露宴_定食屋の親.md",
         a[1] if len(a) > 1 else "披露宴_定食屋の親_絵コンテ.mp4")
