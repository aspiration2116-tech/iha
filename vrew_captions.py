#!/usr/bin/env python3
"""Vrewプロジェクト(.vrew)の字幕に、日本語の文節を考慮した改行を入れる。

使い方:
    python3 vrew_captions.py 入力.vrew 出力.vrew [レポート.md]
    python3 vrew_captions.py 入力.vrew 出力.vrew レポート.md --uniform 120

方針(既定):
    - 字幕は必ず1行または2行。3行は作らない
    - フォントは150のまま維持する。2行に収まらないクリップだけ、
      収まる最大サイズまで下げる(145/140/135/130/125/120)
    - --uniform を付けると全クリップを同じサイズに統一する

安全性:
    書き換えるのは captions[].text[].insert と attributes["size"] だけ。
    mp3(AI音声)・png(画像)・words・tracks・ttsClipInfosMap には触れないので、
    音声・尺・タイムラインは元のまま変わらない。
"""
import json
import math
import re
import sys
import zipfile
from collections import Counter

# ---- 字幕ボックスの実寸から算出した定数 ----
FRAME_W = 1920
BOX_W = 0.96          # captions[].style.width
SCALE = 0.5625        # captions[].style.scaleFactor
USABLE = FRAME_W * BOX_W          # 1843.2 px
BASE_SIZE = 150
SIZE_STEP = 5
MIN_SIZE = 115

BREAK_W = 3.5         # 改行位置の質の重み
SIZE_W = 3.0          # フォントを5下げるごとのコスト
SHRINK_FLAT = 1.5     # 150から下げること自体のコスト(揃っている方が望ましい)

HIRA = re.compile(r'[ぁ-ん]')
KANJI = re.compile(r'[一-鿿々]')
KATA = re.compile(r'[ァ-ヶー]')
KANJI_KATA = re.compile(r'[一-鿿ァ-ヶー]')

SMALL = 'ゃゅょぁぃぅぇぉっャュョァィゥェォッーヽゞ々'
CLOSE = '」』）)、。！？!?・'
OPEN = '「『（('
# 行頭に置きたい接続詞・副詞
LEAD = ['でも', 'ただし', 'また', 'そして', 'つまり', 'だから', 'しかし', 'ちなみに',
        '実は', '特に', '逆に', 'さらに', 'あくまで', '実際', 'むしろ', 'そのため',
        'もし', 'まずは', 'まず', 'たとえば', '例えば', 'なぜなら', 'ですから',
        'それでも', 'こちらは', 'こちらの', 'ここが', 'ここを', 'ここで',
        'これが', 'これは', 'それが']
# 直前で切ってよい接続助詞
P_STRONG = ['ので', 'ため', 'ても', 'ては', 'から', 'まで', 'より', 'けれど',
            'ながら', 'たら', 'なら']
P_MID = list('はがをにでともへ')
# 行頭に置いてはいけない助詞
P_HEAD_NG = 'はがをにでともへのやかもばぞねよわ'


def chars_per_line(size: int) -> int:
    """そのフォントサイズで1行に入る全角文字数。"""
    return int(USABLE // (size * SCALE))


def size_for(maxline: int) -> int:
    """maxline文字を1行に収めるのに必要なサイズ(5刻みで切り下げ)。"""
    return min(BASE_SIZE, int((USABLE / (maxline * SCALE)) // SIZE_STEP) * SIZE_STEP)


BASE_CPL = chars_per_line(BASE_SIZE)      # 21


def break_priority(s: str, i: int) -> float:
    """s を s[:i] / s[i:] に切るときの適切さ。大きいほど良い。"""
    if i <= 0 or i >= len(s):
        return 0.0
    prev, nxt = s[i - 1], s[i]

    if nxt in SMALL or nxt in CLOSE:
        return 0.01
    if prev in OPEN:
        return 0.01
    if prev.isdigit() and nxt.isdigit():
        return 0.01

    # 「」の内側では切らない。ただし引用そのものが1行に収まらない長さなら、
    # 切るのが避けられないので通常のルールで評価して減点するだけにする。
    if s.count('「', 0, i) != s.count('」', 0, i):
        st = s.rfind('「', 0, i)
        en = s.find('」', i)
        qlen = (len(s) if en < 0 else en) - st + 1
        return 0.01 if qlen <= BASE_CPL else _plain(s, i) * 0.5

    return _plain(s, i)


def _plain(s: str, i: int) -> float:
    prev, nxt = s[i - 1], s[i]

    if prev in '、。！？':
        return 5.0
    if prev in '」』）)':
        return 3.2
    for w in LEAD:
        if s.startswith(w, i):
            return 3.4
    for w in P_STRONG:
        if s.endswith(w, 0, i):
            return 3.0

    # --- 禁則 ---
    if nxt in P_HEAD_NG:                              # 行頭が助詞
        return 0.02
    if KANJI.match(prev) and HIRA.match(nxt):         # 送り仮名の分断
        return 0.05
    if KATA.match(prev) and KATA.match(nxt):          # カタカナ語の途中
        return 0.02

    if prev == 'の':                                   # 修飾関係を断つ
        return 0.35
    if prev in P_MID and (i < 2 or s[i - 2] not in P_MID):
        return 2.4
    if prev in 'てで':                                 # 動詞のて形
        return 2.0
    if HIRA.match(prev) and KANJI_KATA.match(nxt):
        return 1.4
    if KANJI.match(prev) and KANJI.match(nxt):        # 熟語の途中
        return 0.2
    if KATA.match(prev) and KANJI.match(nxt):         # 「チャンネル登録」など
        return 0.3
    if HIRA.match(prev) and HIRA.match(nxt):          # 語の途中の可能性が高い
        return 0.1
    return 0.5


def layout(s: str, uniform=None):
    """(行のリスト, フォントサイズ) を返す。必ず1行または2行。"""
    n = len(s)
    if uniform:
        cpl = chars_per_line(uniform)
        if n <= cpl:
            return [s], uniform
        best = None
        for i in range(2, n - 1):
            if max(i, n - i) > cpl:
                continue
            c = BREAK_W * (5.0 - break_priority(s, i))
            if best is None or c < best[0]:
                best = (c, [s[:i], s[i:]])
        if best is None:
            i = math.ceil(n / 2)
            return [s[:i], s[i:]], uniform
        return best[1], uniform

    if n <= BASE_CPL:
        return [s], BASE_SIZE

    # 改行位置とフォントサイズを同時に最適化する
    best = None
    for i in range(2, n - 1):
        size = size_for(max(i, n - i))
        if size < MIN_SIZE:
            continue
        cost = BREAK_W * (5.0 - break_priority(s, i))
        cost += SIZE_W * (BASE_SIZE - size) / SIZE_STEP
        if size < BASE_SIZE:
            cost += SHRINK_FLAT
        if best is None or cost < best[0]:
            best = (cost, [s[:i], s[i:]], size)
    if best is None:
        i = math.ceil(n / 2)
        return [s[:i], s[i:]], MIN_SIZE
    return best[1], best[2]


def process(src, dst, report=None, uniform=None):
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        infos = {i.filename: i for i in z.infolist()}
        data = {n: z.read(n) for n in names}

    proj = json.loads(data['project.json'])
    rows = []
    for idx, c in enumerate(proj['transcript']['clips'], 1):
        parts = c['captions'][0]['text']
        body = ''.join(t['insert'] for t in parts)
        trailing = '\n' if body.endswith('\n') else ''
        body = body.rstrip('\n')
        if not body:
            continue
        lines, size = layout(body, uniform)
        parts[0]['insert'] = '\n'.join(lines) + trailing
        for t in parts[1:]:
            t['insert'] = ''
        for cc in c['captions']:
            for t in cc['text']:
                t['attributes']['size'] = str(size)
        rows.append((idx, lines, size))

    data['project.json'] = json.dumps(
        proj, ensure_ascii=False, separators=(',', ':')).encode()

    # 元と同じ格納順・同じ圧縮方式で書き戻す
    with zipfile.ZipFile(dst, 'w') as z:
        for n in names:
            zi = zipfile.ZipInfo(n, date_time=infos[n].date_time)
            zi.compress_type = infos[n].compress_type
            zi.external_attr = infos[n].external_attr
            z.writestr(zi, data[n])

    if report:
        _write_report(report, rows)
    return rows


def _write_report(path, rows):
    shrunk = [r for r in rows if r[2] != BASE_SIZE]
    weak = []
    for idx, lines, size in rows:
        if len(lines) < 2:
            continue
        pr = break_priority(''.join(lines), len(lines[0]))
        if pr < 1.0:
            weak.append((idx, round(pr, 2), lines))
    with open(path, 'w') as f:
        f.write('# 字幕レイアウト結果\n\n')
        f.write(f'- 1行: {sum(1 for r in rows if len(r[1]) == 1)}件\n')
        f.write(f'- 2行: {sum(1 for r in rows if len(r[1]) == 2)}件\n')
        f.write(f'- 3行: {sum(1 for r in rows if len(r[1]) >= 3)}件\n')
        f.write(f'- フォントを下げたクリップ: {len(shrunk)}件\n\n')
        if weak:
            f.write('## 手直し推奨(文が長く、語の途中で切らざるを得なかった)\n\n')
            f.write('クリップを2つに分割すると自然になります。\n\n')
            for idx, pr, lines in weak:
                f.write(f'- **clip {idx}** … `{lines[0][-10:]}／{lines[1][:10]}`\n')
            f.write('\n')
        if shrunk:
            f.write('## フォントを下げたクリップ\n\n| clip | サイズ | 字幕 |\n|---|---|---|\n')
            for idx, lines, size in shrunk:
                f.write(f'| {idx} | {size} | {"<br>".join(lines)} |\n')
            f.write('\n')
        f.write('---\n\n## 全クリップ\n\n')
        for idx, lines, size in rows:
            tag = f'（フォント{size}）' if size != BASE_SIZE else ''
            f.write(f'### {idx}{tag}\n```\n' + '\n'.join(lines) + '\n```\n\n')


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    src, dst = argv[1], argv[2]
    report = argv[3] if len(argv) > 3 and not argv[3].startswith('--') else None
    uniform = int(argv[argv.index('--uniform') + 1]) if '--uniform' in argv else None

    rows = process(src, dst, report, uniform)
    n1 = sum(1 for r in rows if len(r[1]) == 1)
    n2 = sum(1 for r in rows if len(r[1]) == 2)
    n3 = sum(1 for r in rows if len(r[1]) >= 3)
    shrunk = [r[2] for r in rows if r[2] != BASE_SIZE]
    print(f'{len(rows)}クリップ: 1行={n1} 2行={n2} 3行={n3}')
    print(f'フォント変更={len(shrunk)}件 {dict(sorted(Counter(shrunk).items()))}')
    over = [(i, l) for i, ls, s in rows for l in ls if len(l) > chars_per_line(s)]
    print('はみ出し:', over or 'なし')
    print(f'出力: {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
