#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手元の VOICEVOX で本番音声を書き出す

  1. VOICEVOX を起動しておく(エンジンが http://localhost:50021 で待ち受ける)
  2. python3 voicevox_audio.py ../台本/01_披露宴_定食屋の親.md out_audio/

カードごとに wav を書き出し、timing.json に尺を残す。
そのまま make_video.py の build/ に差し込めば、本番音声の動画になる。

話者IDはバージョンで変わるので埋め込まない。起動中のエンジンの /speakers から
「話者名 + スタイル名」で毎回引き直す。
"""
import json, os, re, sys, urllib.request, urllib.parse

BASE = os.environ.get("VOICEVOX_URL", "http://localhost:50021")

# 役 → (話者名, スタイル名, 話速, 音高, 抑揚)
CAST = {
    "結衣":      ("九州そら",   "ノーマル", 1.05, 0.00, 0.90),
    "政子":      ("WhiteCUL",  "たのしい", 1.10, 0.03, 1.15),
    "涼介":      ("青山龍星",   "ノーマル", 1.00, 0.00, 0.95),
    "父":        ("玄野武宏",   "ノーマル", 0.92, -0.02, 0.90),
    "鷹野":      ("玄野武宏",   "ノーマル", 0.88, -0.04, 0.85),
    "黒田":      ("白上虎太郎", "ふつう",   1.00, 0.00, 1.00),
    "プランナー": ("白上虎太郎", "ふつう",   1.00, 0.00, 1.00),
    "親族":      ("白上虎太郎", "ふつう",   0.95, 0.00, 1.00),
    "ナレ":      ("九州そら",   "ノーマル", 0.98, 0.00, 0.95),
}
# ラストの1箇所だけ、声を揺らす(全編で感情を殺してきた主人公が、ここだけ)
EMOTION_LINE = "そこで初めて、私は泣きました。"
EMOTION = (0.95, 0.00, 1.05)   # 話速 / 音高 / 抑揚

def api(path, data=None, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body or params else "GET",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=60).read()

def speaker_ids():
    """起動中のエンジンから {(話者名, スタイル名): id} を作る"""
    spk = json.loads(urllib.request.urlopen(BASE + "/speakers", timeout=30).read())
    out = {}
    for s in spk:
        for st in s["styles"]:
            out[(s["name"], st["name"])] = st["id"]
    return out

def resolve(ids, name, style):
    if (name, style) in ids: return ids[(name, style)]
    cand = [k for k in ids if k[0] == name]
    if cand:
        print(f"  !! {name}/{style} が見つからないので {cand[0][1]} を使います")
        return ids[cand[0]]
    raise SystemExit(f"話者「{name}」がこのVOICEVOXに入っていません。"
                     f"利用可能: {sorted({k[0] for k in ids})}")

def parse(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0]
    items, speaker, lines = [], None, []
    def flush():
        nonlocal speaker, lines
        if speaker and lines:
            items.append(("card", speaker, "".join(lines)))
        speaker, lines = None, []
    for raw in body.split("\n"):
        t = raw.strip()
        if t.startswith(("## ", "### ", "> ")): flush(); continue
        m = re.match(r'^\*\*【無音([\d.]+)秒】\*\*$', t)
        if m: flush(); items.append(("silence", "", float(m.group(1)))); continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*$', t)
        if m: flush(); speaker = m.group(1); continue
        if raw.startswith("　"): lines.append(raw[1:].strip())
    flush()
    return items

def main(script, outdir):
    os.makedirs(outdir, exist_ok=True)
    try:
        ids = speaker_ids()
    except Exception as e:
        raise SystemExit(f"VOICEVOXに接続できません({BASE})。起動してから実行してください。\n{e}")
    print(f"接続OK。話者 {len({k[0] for k in ids})}名")
    items, timing, n = parse(script), [], 0
    for kind, speaker, payload in items:
        n += 1
        if kind == "silence":
            timing.append({"i": n, "type": "silence", "sec": payload})
            continue
        name, style, rate, pitch, inton = CAST.get(speaker, CAST["結衣"])
        if payload == EMOTION_LINE:
            rate, pitch, inton = EMOTION
        sid = resolve(ids, name, style)
        q = json.loads(api("/audio_query", params={"text": payload, "speaker": sid}))
        q["speedScale"], q["pitchScale"], q["intonationScale"] = rate, pitch, inton
        q["prePhonemeLength"], q["postPhonemeLength"] = 0.05, 0.25
        wav = api("/synthesis", data=q, params={"speaker": sid})
        path = os.path.join(outdir, f"{n:04d}_{speaker}.wav")
        open(path, "wb").write(wav)
        timing.append({"i": n, "type": "card", "speaker": speaker,
                       "voice": f"{name}/{style}", "text": payload, "file": os.path.basename(path)})
        if n % 25 == 0: print(f"  ... {n}/{len(items)}")
    json.dump(timing, open(os.path.join(outdir, "timing.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"✅ {outdir} に {sum(1 for t in timing if t['type']=='card')} ファイル + timing.json")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "../台本/01_披露宴_定食屋の親.md",
         a[1] if len(a) > 1 else "out_audio")
