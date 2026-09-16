#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lovartで作った絵 + テロップ + 音声 → 本番動画

  python3 compose_final.py                       # 既定のパスで組む
  python3 compose_final.py --script ../台本/01_披露宴_定食屋の親.md \
                           --images images --audio out_audio --out 完成.mp4

絵      images/cutNN.png(NNは1始まり)。cutNNb.png / cutNNc.png があれば
        その場面の中で自動的に切り替わる。無い番号は仮画像を自動生成するので、
        **1枚も無くても動画は組める**(尺とテロップの確認ができる)。
音声    out_audio/timing.json があればVOICEVOXのwavを使う。
        無ければ open_jtalk で仮の音声を作る(絵コンテ用)。
動き    静止画のままだと紙芝居になるので、カットごとに
        ゆっくり寄る/引く(Ken Burns)。寄る向きはカット番号で交互。
"""
import argparse, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
DIC  = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
W, H, FPS = 1920, 1080, 24

# 話者 → (open_jtalk音声, 話速, 半音, テロップの色)
CAST = {
    "結衣":      ("voices/mei/mei_normal.htsvoice",      1.00,  0.0, (255, 255, 255)),
    "政子":      ("voices/mei/mei_happy.htsvoice",       1.08,  0.3, (255, 176, 196)),
    "涼介":      ("voices/takumi/takumi_normal.htsvoice", 1.02,  0.0, (156, 202, 255)),
    "父":        ("voices/takumi/takumi_sad.htsvoice",    0.92, -0.2, (255, 216, 152)),
    "鷹野":      ("hts/nitech.htsvoice",                  0.88, -0.3, (186, 248, 202)),
    "黒田":      ("voices/takumi/takumi_happy.htsvoice",  1.00,  0.0, (206, 206, 206)),
    "支配人":    ("voices/takumi/takumi_happy.htsvoice",  0.98,  0.0, (206, 206, 206)),
    "受付":      ("voices/takumi/takumi_normal.htsvoice", 1.00,  0.0, (206, 206, 206)),
    "プランナー": ("voices/mei/mei_bashful.htsvoice",      1.00,  0.0, (206, 206, 206)),
    "親族A":     ("voices/mei/mei_bashful.htsvoice",      0.96,  0.0, (206, 206, 206)),
    "親族B":     ("voices/mei/mei_bashful.htsvoice",      0.94,  0.0, (206, 206, 206)),
    "ナレ":      ("voices/mei/mei_normal.htsvoice",       0.98,  0.0, (236, 236, 236)),
}
DEFAULT = CAST["結衣"]


def parse(path):
    """テロップ台本 → カード一覧。cut は 1 始まりの場面番号。"""
    body = open(path, encoding="utf-8").read().split("# 台本本文")[1].split("# 概要欄")[0]
    items, speaker, lines = [], None, []
    cut, started = 0, False

    def flush():
        nonlocal speaker, lines
        if speaker and lines:
            items.append({"kind": "card", "speaker": speaker, "lines": lines[:], "cut": cut})
            mark_started()
        speaker, lines = None, []

    def mark_started():
        nonlocal started
        started = True

    def newcut():
        """直前の場面に中身があったときだけ場面番号を進める(空の区切りを数えない)"""
        nonlocal cut, started
        if started or cut == 0:
            cut += 1; started = False

    for raw in body.split("\n"):
        t = raw.strip()
        if t.startswith("## "):
            flush(); newcut(); continue
        if t.startswith("### "):
            flush(); continue
        if t == "---":
            flush(); newcut(); continue
        if t.startswith("> ト書き"):
            flush(); newcut(); continue
        if t.startswith(">"):
            continue
        m = re.match(r'^\*\*【無音([\d.]+)秒】\*\*$', t)
        if m:
            flush(); items.append({"kind": "silence", "sec": float(m.group(1)), "cut": cut}); continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*$', t)
        if m:
            flush(); speaker = m.group(1); continue
        if raw.startswith("　"):
            lines.append(raw[1:].strip()); continue
    flush()
    return items


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:    return float(r.stdout.strip())
    except: return 0.0


def synth(text, voice, rate, fm, out):
    vp = voice if os.path.isabs(voice) else os.path.join(HERE, voice)
    tf = out + ".txt"
    open(tf, "w", encoding="utf-8").write(text + "\n")
    subprocess.run(["open_jtalk", "-x", DIC, "-m", vp, "-r", str(rate),
                    "-fm", str(fm), "-ow", out, tf], capture_output=True)
    os.unlink(tf)
    return dur(out)


def placeholder(path, cut, note=""):
    """絵が無い番号の仮画像。番号が大きく出るので、どれを作ればいいか分かる。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), (16, 18, 26))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        v = int(16 + 30 * (1 - y / H) ** 2)
        d.rectangle([0, y, W, y + 4], fill=(v, v + 2, v + 8))
    d.text((W // 2, H // 2 - 90), f"cut{cut:02d}.png", font=ImageFont.truetype(FONT, 110),
           fill=(70, 78, 100), anchor="mm")
    d.text((W // 2, H // 2 + 30), "この番号の絵がまだありません", font=ImageFont.truetype(FONT, 40),
           fill=(58, 64, 84), anchor="mm")
    img.save(path)


def telop_png(item, path):
    """テロップだけを描いた透過PNG。絵の上に重ねる。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(item["lines"])
    top = 760 if n > 1 else 830
    # 下半分を暗く落とす(テロップを読ませるため)
    for y in range(top - 120, H):
        a = int(210 * min(1.0, (y - (top - 120)) / 190.0))
        d.rectangle([0, y, W, y + 1], fill=(0, 0, 0, a))
    f_sp  = ImageFont.truetype(FONT, 38)
    f_tel = ImageFont.truetype(FONT, 78)
    sp = item["speaker"]
    if sp != "結衣":                      # 地の文の話者名は出さない
        d.text((W // 2, top - 62), sp, font=f_sp, fill=CAST.get(sp, DEFAULT)[3], anchor="ma")
    y = top
    for ln in item["lines"]:
        for dx in (-4, -2, 0, 2, 4):
            for dy in (-4, -2, 0, 2, 4):
                if dx or dy:
                    d.text((W // 2 + dx, y + dy), ln, font=f_tel, fill=(0, 0, 0, 255), anchor="ma")
        d.text((W // 2, y), ln, font=f_tel, fill=(255, 255, 255, 255), anchor="ma")
        y += 104
    img.save(path)


def pick_image(imgdir, cut, seq, work):
    """cutNN.png / cutNNb.png / cutNNc.png を順に使い回す"""
    cands = []
    for suf in ("", "b", "c", "d"):
        p = os.path.join(imgdir, f"cut{cut:02d}{suf}.png")
        if os.path.exists(p): cands.append(p)
        p = os.path.join(imgdir, f"cut{cut:02d}{suf}.jpg")
        if os.path.exists(p): cands.append(p)
    if not cands:
        p = os.path.join(work, f"ph{cut:02d}.png")
        if not os.path.exists(p): placeholder(p, cut)
        return p
    return cands[seq % len(cands)]


def segment(img, telop, audio, sec, out, cut):
    """1カード分の動画。絵をゆっくり寄せ/引きして、テロップを重ねる。"""
    frames = max(2, int(round(sec * FPS)))
    zin = (cut % 2 == 0)
    if zin:
        z = f"min(1.0+0.00060*on,1.10)"
    else:
        z = f"max(1.10-0.00060*on,1.0)"
    anchor = cut % 3            # 寄る位置を散らす
    ax = {0: "iw/2-(iw/zoom/2)", 1: "iw/2-(iw/zoom/2)-60", 2: "iw/2-(iw/zoom/2)+60"}[anchor]
    vf = (f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
          f"crop={W*2}:{H*2},setsar=1,"
          f"zoompan=z='{z}':x='{ax}':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}[bg];"
          f"[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
          f"[2:a]apad,atrim=0:{sec:.3f},asetpts=N/SR/TB[a]")
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-loop", "1", "-t", f"{sec:.3f}", "-i", img,
           "-loop", "1", "-t", f"{sec:.3f}", "-i", telop]
    if audio:
        cmd += ["-i", audio]
    else:
        cmd += ["-f", "lavfi", "-t", f"{sec:.3f}", "-i", "anullsrc=r=24000:cl=mono"]
    cmd += ["-filter_complex", vf, "-map", "[v]", "-map", "[a]",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "24000",
            "-t", f"{sec:.3f}", out]
    subprocess.run(cmd, check=True, capture_output=True)


def main(a):
    work = os.path.join(HERE, "build_final")
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    items = parse(a.script)
    cards = [x for x in items if x["kind"] == "card"]
    print(f"カード {len(cards)} / 場面 {max(x['cut'] for x in items)}")

    # VOICEVOXの音声があれば使う
    vv = None
    tj = os.path.join(a.audio, "timing.json")
    if os.path.exists(tj):
        vv = [t for t in json.load(open(tj, encoding="utf-8")) if t["type"] == "card"]
        if len(vv) != len(cards):
            print(f"⚠ timing.json のカード数 {len(vv)} が台本の {len(cards)} と違います。"
                  f"台本を直したら voicevox_audio.py を実行し直してください。")
            vv = None
        else:
            print(f"音声: VOICEVOX ({a.audio})")
    if vv is None:
        print("音声: open_jtalk(仮)。本番は voicevox_audio.py で差し替えてください")

    segs, seq, last_cut, total = [], 0, None, 0.0
    ci = 0
    for n, it in enumerate(items):
        if it["kind"] == "silence":
            # 直前の絵のまま、無音で止める
            img = pick_image(a.images, it["cut"], max(0, seq - 1), work)
            tp  = os.path.join(work, f"t{n:04d}.png")
            from PIL import Image
            Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(tp)
            out = os.path.join(work, f"s{n:04d}.mp4")
            segment(img, tp, None, it["sec"], out, it["cut"])
            segs.append(out); total += it["sec"]; continue

        if it["cut"] != last_cut:
            seq, last_cut = 0, it["cut"]
        if vv:
            wav = os.path.join(a.audio, vv[ci]["file"]) if "file" in vv[ci] else \
                  os.path.join(a.audio, f"{vv[ci]['i']:04d}_{vv[ci]['speaker']}.wav")
            sec = dur(wav)
        else:
            voice, rate, fm, _ = CAST.get(it["speaker"], DEFAULT)
            wav = os.path.join(work, f"a{n:04d}.wav")
            sec = synth("".join(it["lines"]), voice, rate, fm, wav)
        sec = max(sec, 0.6) + 0.22          # 語尾の余韻
        img = pick_image(a.images, it["cut"], seq, work)
        tp  = os.path.join(work, f"t{n:04d}.png")
        telop_png(it, tp)
        out = os.path.join(work, f"s{n:04d}.mp4")
        segment(img, tp, wav, sec, out, it["cut"])
        segs.append(out); total += sec; seq += 1; ci += 1
        if ci % 25 == 0:
            print(f"  {ci}/{len(cards)}  {int(total//60)}:{int(total%60):02d}")

    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in segs))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", a.out], check=True)
    d = dur(a.out)
    print(f"\n✅ {a.out}  {int(d//60)}:{int(d%60):02d}  "
          f"{os.path.getsize(a.out)/1e6:.1f}MB")
    miss = sorted({x["cut"] for x in items
                   if not any(os.path.exists(os.path.join(a.images, f"cut{x['cut']:02d}{s}{e}"))
                              for s in ("",) for e in (".png", ".jpg"))})
    if miss:
        print(f"⚠ 絵がまだ無い場面: {', '.join(f'cut{c:02d}' for c in miss)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--script", default=os.path.join(HERE, "..", "台本", "01_披露宴_定食屋の親.md"))
    p.add_argument("--images", default=os.path.join(HERE, "images"))
    p.add_argument("--audio",  default=os.path.join(HERE, "out_audio"))
    p.add_argument("--out",    default=os.path.join(HERE, "披露宴_定食屋の親_本番.mp4"))
    main(p.parse_args())
