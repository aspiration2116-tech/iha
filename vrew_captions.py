#!/usr/bin/env python3
"""Vrewプロジェクト(.vrew)の字幕に、日本語の文節を考慮した改行を入れる。

使い方:
    python3 vrew_captions.py 入力.vrew 出力.vrew [レポート.md]
    python3 vrew_captions.py 入力.vrew 出力.vrew レポート.md --uniform 120

方針:
    - フォントは全クリップ150で固定。絶対に変更しない
    - 字幕はできる限り1行または2行に収める
    - 150では1行21文字・2行42文字が上限。43文字以上のクリップだけ3行になる
      (フォントを下げずに2行にする方法は、クリップ分割しかない)
    - 3行になったクリップは、レポートに分割位置の提案を出力する

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
FONT_SIZE = 150       # 全クリップ固定。変更しないこと
MAX_LINES = 3

BREAK_W = 3.5         # 改行位置の質の重み
TARGET_RATIO = 0.85   # 1行の目標文字数 = 上限 * この比率
LINE_PENALTY = 20.0   # 行を1つ増やすコスト。3行は数学的に避けられない時だけにする

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


CPL = chars_per_line(FONT_SIZE)           # 21文字
TARGET = int(CPL * TARGET_RATIO)          # 17文字


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
        return 0.01 if qlen <= CPL else _plain(s, i) * 0.5

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


def layout(s: str):
    """フォント150固定で行に分ける。行数は最小限に抑える。"""
    n = len(s)
    if n <= CPL:
        return [s]
    need = -(-n // CPL)
    best = None
    for lines in range(need, MAX_LINES + 1):
        r = _dp(s, lines)
        if not r:
            continue
        cost = r[0] + LINE_PENALTY * (lines - need)
        if best is None or cost < best[0]:
            best = (cost, r[1])
    if best:
        return best[1]
    return [s[i:i + CPL] for i in range(0, n, CPL)]


def _dp(s: str, lines: int):
    """s を lines 行に分ける最小コストの組み方を返す。"""
    n = len(s)
    INF = float('inf')
    best = [[INF] * (n + 1) for _ in range(lines + 1)]
    prev = [[-1] * (n + 1) for _ in range(lines + 1)]
    best[0][0] = 0.0
    for k in range(1, lines + 1):
        for i in range(1, n + 1):
            for j in range(max(0, i - CPL), i):
                if best[k - 1][j] == INF:
                    continue
                ln = i - j
                if ln < 2:
                    continue
                pr = break_priority(s, j) if j > 0 else 5.0
                cost = (best[k - 1][j] + BREAK_W * (5.0 - pr)
                        + ((ln - TARGET) / TARGET) ** 2 * 2.0)
                if cost < best[k][i]:
                    best[k][i] = cost
                    prev[k][i] = j
    if best[lines][n] == INF:
        return None
    out, i = [], n
    for k in range(lines, 0, -1):
        j = prev[k][i]
        out.append(s[j:i])
        i = j
    return best[lines][n], out[::-1]


def suggest_split(s: str):
    """クリップを2つに分けるならどこか。(前半, 後半) または None。"""
    n = len(s)
    limit = CPL * 2                      # 分割後の各クリップが2行に収まる長さ
    best = None
    for i in range(2, n - 1):
        if max(i, n - i) > limit:
            continue
        pr = break_priority(s, i)
        if pr < 2.0:                     # 文の切れ目と言える場所だけ
            continue
        bal = ((max(i, n - i) - n / 2) / (n / 2)) ** 2
        score = pr - bal
        if best is None or score > best[0]:
            best = (score, s[:i], s[i:])
    return (best[1], best[2]) if best else None


def process(src, dst, report=None):
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
        lines = layout(body)
        parts[0]['insert'] = '\n'.join(lines) + trailing
        for t in parts[1:]:
            t['insert'] = ''
        # フォントは常に150に揃える(過去に変更されていても元に戻す)
        for cc in c['captions']:
            for t in cc['text']:
                t['attributes']['size'] = str(FONT_SIZE)
        rows.append((idx, body, lines))

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


def weak_break(body, lines):
    """語の途中など、不自然な位置で切らざるを得なかったか。"""
    pos = 0
    for ln in lines[:-1]:
        pos += len(ln)
        if break_priority(body, pos) < 1.0:
            return True
    return False


def _write_report(path, rows):
    three = [r for r in rows if len(r[2]) >= 3]
    weak = [r for r in rows if len(r[2]) == 2 and weak_break(r[1], r[2])]
    todo = sorted(three + weak, key=lambda r: r[0])
    with open(path, 'w') as f:
        f.write('# 字幕レイアウト結果（フォント150固定）\n\n')
        f.write(f'- 1行: {sum(1 for r in rows if len(r[2]) == 1)}件\n')
        f.write(f'- 2行: {sum(1 for r in rows if len(r[2]) == 2)}件\n')
        f.write(f'- 3行: {len(three)}件（43文字以上のため2行に収まらない）\n\n')
        f.write('フォント150では **1行21文字・2行42文字** が上限です。\n')
        f.write('フォントを変えずにこれを超える文を2行にする方法は、\n')
        f.write('**クリップを2つに分割する**ことだけです。\n\n')
        if todo:
            f.write(f'## 分割をおすすめするクリップ（{len(todo)}件）\n\n')
            f.write('Vrewで分割位置にカーソルを置き、Enterを押すとクリップが分かれます。\n')
            f.write('分割するとAI音声もその位置で分かれるので、音声は作り直し不要です。\n\n')
            for idx, body, lines in todo:
                reason = '3行になっている' if len(lines) >= 3 else '語の途中で改行されている'
                f.write(f'### clip {idx}（{len(body)}文字・{reason}）\n\n')
                f.write('現状:\n```\n' + '\n'.join(lines) + '\n```\n\n')
                sp = suggest_split(body)
                if sp:
                    f.write('分割案:\n\n')
                    for k, half in enumerate(sp, 1):
                        f.write(f'クリップ{k}\n```\n' + '\n'.join(layout(half)) + '\n```\n')
                    f.write('\n')
                else:
                    f.write('適切な分割位置が見つかりません。手動で判断してください。\n\n')
        f.write('---\n\n## 全クリップ\n\n')
        for idx, body, lines in rows:
            mark = ' ★3行' if len(lines) >= 3 else ''
            f.write(f'### {idx}{mark}\n```\n' + '\n'.join(lines) + '\n```\n\n')


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    src, dst = argv[1], argv[2]
    report = argv[3] if len(argv) > 3 else None

    rows = process(src, dst, report)
    cnt = Counter(len(r[2]) for r in rows)
    print(f'{len(rows)}クリップ（フォント150固定）: '
          f'1行={cnt[1]} 2行={cnt[2]} 3行={cnt[3]}')
    over = [(i, l) for i, _, ls in rows for l in ls if len(l) > CPL]
    print('はみ出し:', over or 'なし')
    todo = [r[0] for r in rows
            if len(r[2]) >= 3 or (len(r[2]) == 2 and weak_break(r[1], r[2]))]
    if todo:
        print(f'分割推奨 {len(todo)}件: clip {todo}')
    print(f'出力: {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
