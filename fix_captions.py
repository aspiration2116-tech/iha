#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, sys

SRC = 'project.json'

def eff(s):
    # full-width chars count 1, ascii (digits/letters/symbols) count 0.5
    return sum(0.5 if ord(ch) < 128 else 1 for ch in s)

MAX_LINE = 20  # target max effective chars per line at size 150

def process_text(t):
    # --- reduce ideographic commas ---
    keep = []
    out = []
    removed_pos = []  # candidate break positions in new text (index = break before this idx)
    i = 0
    n = len(t)
    while i < n:
        ch = t[i]
        if ch == '、':
            prev = t[i-1] if i > 0 else ''
            nxt = t[i+1] if i+1 < n else ''
            # keep comma in enumerations like 3、4  / あり、なし
            if (prev.isdigit() and nxt.isdigit()) or t[max(0,i-2):i+3] in ('あり、なし',):
                out.append(ch)
            else:
                removed_pos.append(len(out))  # break candidate where comma was
            i += 1
            continue
        out.append(ch)
        i += 1
    nt = ''.join(out)

    if eff(nt) <= MAX_LINE:
        return nt, None

    # --- collect break candidates ---
    cands = set(removed_pos)
    for m in re.finditer(r'」', nt):
        cands.add(m.end())
    # particle followed by non-hiragana (kanji/katakana/digit) => phrase boundary
    for m in re.finditer(r'(?<=[はがをにでとへも])(?=[^ぁ-ゖ、。」])', nt):
        cands.add(m.start())
    for m in re.finditer(r'(?:ので|けど|から|ながら|ように|ため|ですが|ますが)', nt):
        cands.add(m.end())
    cands = {c for c in cands if 2 <= c <= len(nt)-2}

    def score(c):
        a, b = eff(nt[:c]), eff(nt[c:])
        return (max(a, b), abs(a - b))

    if cands:
        c = min(cands, key=score)
    else:
        c = len(nt)//2
    return nt[:c] + '\n' + nt[c:], c

def main(write=False):
    d = json.load(open(SRC))
    clips = d['transcript']['clips']
    report = []
    for idx, clip in enumerate(clips):
        caps = clip.get('captions') or []
        if not caps:
            continue
        ops = caps[0].get('text', [])
        raw = ''.join(op.get('insert','') for op in ops)
        t = raw.rstrip('\n')
        if not t:
            continue
        if idx in OVERRIDES:
            new = OVERRIDES[idx]
        else:
            new, _ = process_text(t)
        lines = new.split('\n')
        report.append((idx, [round(eff(l),1) for l in lines], new))
        if write:
            caps[0]['text'] = [{'insert': new + '\n'}]
    if write:
        json.dump(d, open(SRC, 'w'), ensure_ascii=False)
        print('written')
    else:
        for idx, lens, new in report:
            flag = ' <== LONG' if any(l > MAX_LINE for l in lens) else ''
            print(f'{idx:3d} {lens}{flag} | ' + ' / '.join(new.split('\n')))

OVERRIDES = {
    23: "ある条件で行われた検証ではすだれを設置した窓の\nガラス表面温度におよそ9度の差が出ています",
    38: "同じような効果が続けば購入費以上の\n節電につながる可能性もあります",
    52: "すだれは窓ガラスにぴったり密着させるのではなく\n少し離して設置するのがおすすめです",
    60: "ただし外側への設置は管理規約で制限されている\n物件もあるので事前に確認してくださいね",
    78: "製品によってはすだれより日差しを\nしっかり遮れるタイプもあります",
    104: "シェードなどを使って風の通り道は\nしっかり確保したまま日陰だけを作ってあげてください",
    108: "外側に日よけを付けられない場合はカーテンの上や横の\n隙間を小さくするのも一つの方法です",
    143: "すだれやシェードはエアコンを使いやすくするための\n道具であってエアコンの代わりではありません",
    156: "チャンネル登録して\n次の動画をお待ちください",
}

if __name__ == '__main__':
    main(write='--write' in sys.argv)
