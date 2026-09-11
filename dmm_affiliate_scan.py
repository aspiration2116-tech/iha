#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dmm_affiliate_scan.py — DMM/FANZA アフィリエイトリンクの検出・除去ツール

DMMアフィリエイトのサイト審査で
「アフィリエイトIDを登録外のサイトで使用されているため」
と不承認になったときに、申請サイトのローカルファイルから
DMM/FANZAのアフィリエイトリンクを洗い出して取り除くためのツール。

使い方:

    # 1) まず検出だけする（ファイルは一切変更しない）
    python3 dmm_affiliate_scan.py ~/サイトのフォルダ

    # 2) リンクを取り除くとどうなるかプレビュー（まだ変更しない）
    python3 dmm_affiliate_scan.py ~/サイトのフォルダ --strip

    # 3) 実際に取り除く（変更前のファイルは自動でバックアップされる）
    python3 dmm_affiliate_scan.py ~/サイトのフォルダ --strip --apply

    # 掲載記事ごと外したい場合（削除ではなく退避なので後から戻せる）
    python3 dmm_affiliate_scan.py ~/サイトのフォルダ --quarantine --apply

--apply を付けない限り、ファイルは絶対に変更されない。
"""

import argparse
import os
import re
import shutil
import sys
import json
import datetime

# ---------------------------------------------------------------- 走査対象

SKIP_DIRS = {
    '.git', '.svn', '.hg', 'node_modules', 'vendor', '.next', 'dist', 'build',
    '.cache', '__pycache__', '.idea', '.vscode', '.venv', 'venv', '.DS_Store',
}

# 中身を読むファイル
TEXT_EXTS = {
    '.html', '.htm', '.php', '.md', '.markdown', '.txt', '.js', '.jsx', '.mjs',
    '.cjs', '.ts', '.tsx', '.json', '.css', '.scss', '.sass', '.xml', '.yml',
    '.yaml', '.vue', '.svelte', '.ejs', '.erb', '.liquid', '.hbs', '.twig',
    '.rss', '.csv', '.tsv', '.sql', '.tpl', '.htaccess',
}

# 自動でリンク除去まで行うファイル（構文を壊す危険が低いもの）
STRIPPABLE_EXTS = {'.html', '.htm', '.php', '.md', '.markdown', '.txt'}

# ---------------------------------------------------------------- URL判定

URL_RE = re.compile(
    r'(?i)(?:https?:)?//(?:[a-z0-9_-]+\.)*'
    r'(?:dmm\.co\.jp|dmm\.com|fanza\.co\.jp|dmmapis\.com)'
    r'(?:[:/?#][^\s"\'<>)\]\\}]*)?'
)

AF_ID_RE = re.compile(r'(?i)\b(?:af_id|affiliate_id|affiliateid)=([A-Za-z0-9._-]+)')


def classify(url):
    """URLを (種別, af_id) に分類する。

    種別は 'affiliate'（アフィリエイトリンク）か 'plain'（ただのDMMリンク）。
    審査で問題になるのは 'affiliate' の方。
    """
    m = AF_ID_RE.search(url)
    if m:
        return 'affiliate', m.group(1)

    low = url.lower()
    host = re.sub(r'^(?:https?:)?//', '', low).split('/')[0].split(':')[0]

    # al.dmm.co.jp / al.fanza.co.jp はアフィリエイト専用の転送ドメイン
    if host.startswith('al.'):
        return 'affiliate', None
    # ウィジェット・API・バナー配信
    if host.startswith('widget-view.') or host.startswith('affiliate.') or host.startswith('api.'):
        return 'affiliate', None
    # バナー画像 https://p.dmm.co.jp/p/affiliate/...
    if '/affiliate/' in low or '/af/' in low:
        return 'affiliate', None

    return 'plain', None


def make_matcher(strip_all_dmm):
    """除去対象かどうかを判定する関数を返す。"""
    def is_target(url):
        kind, _ = classify(url)
        return True if strip_all_dmm else kind == 'affiliate'
    return is_target


# ---------------------------------------------------------------- 検出

class Hit:
    __slots__ = ('path', 'line', 'url', 'kind', 'af_id', 'context')

    def __init__(self, path, line, url, kind, af_id, context):
        self.path = path
        self.line = line
        self.url = url
        self.kind = kind
        self.af_id = af_id
        self.context = context


def iter_files(root, extra_exts):
    exts = TEXT_EXTS | set(extra_exts)
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.git')]
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext in exts or name.lower() in exts:
                yield os.path.join(dirpath, name)


def read_text(path):
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    if b'\x00' in raw[:8000]:          # バイナリは飛ばす
        return None
    for enc in ('utf-8', 'cp932', 'euc-jp'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def scan(root, extra_exts):
    hits = []
    scanned = 0
    for path in iter_files(root, extra_exts):
        text = read_text(path)
        if text is None:
            continue
        scanned += 1
        if 'dmm' not in text.lower() and 'fanza' not in text.lower():
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            line_ids = set(AF_ID_RE.findall(line))
            for m in URL_RE.finditer(line):
                url = m.group(0)
                kind, af_id = classify(url)
                # JSで "...&af_id=" + id のように連結されていると
                # URL文字列だけでは拾えないので、行に1つだけあるIDを充てる
                if af_id is None and len(line_ids) == 1:
                    af_id = next(iter(line_ids))
                ctx = line.strip()
                if len(ctx) > 160:
                    ctx = ctx[:157] + '...'
                hits.append(Hit(path, lineno, url, kind, af_id, ctx))
    return hits, scanned


# ---------------------------------------------------------------- 除去(HTML)

OPEN_TAG_END_RE = re.compile(r'>')
A_RE = re.compile(r'<a\b[^>]*>.*?</a\s*>', re.IGNORECASE | re.DOTALL)
IFRAME_RE = re.compile(r'<iframe\b[^>]*>.*?</iframe\s*>', re.IGNORECASE | re.DOTALL)
SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.IGNORECASE | re.DOTALL)
IMG_RE = re.compile(r'<img\b[^>]*?/?>', re.IGNORECASE)


def _opening_tag(element):
    m = OPEN_TAG_END_RE.search(element)
    return element[:m.end()] if m else element


def _tag_targets(fragment, is_target):
    return [m.group(0) for m in URL_RE.finditer(fragment) if is_target(m.group(0))]


def strip_html(text, is_target, removed):
    """HTML/PHPからアフィリエイトの要素を取り除く。

    - <script>/<iframe>/<img> はまるごと削除
    - <a> は中身が画像・iframeならまるごと削除、文字リンクなら文字だけ残す
    """
    def kill_if_target(m):
        element = m.group(0)
        if _tag_targets(_opening_tag(element), is_target):
            removed.append(element.strip()[:120])
            return ''
        return element

    text = SCRIPT_RE.sub(kill_if_target, text)
    text = IFRAME_RE.sub(kill_if_target, text)

    def a_repl(m):
        element = m.group(0)
        opening = _opening_tag(element)
        if not _tag_targets(opening, is_target):
            return element
        inner = element[len(opening):]
        inner = re.sub(r'</a\s*>$', '', inner, flags=re.IGNORECASE)
        removed.append(element.strip()[:120])
        # 画像バナーやiframeを包んだリンクは、中身ごと消す
        if re.search(r'<(?:img|iframe|picture|video)\b', inner, re.IGNORECASE):
            return ''
        # 文字リンクはリンクだけ外して文字を残す
        return inner

    text = A_RE.sub(a_repl, text)
    text = IMG_RE.sub(kill_if_target, text)
    return text


# ---------------------------------------------------------------- 除去(MD)

MD_IMG_RE = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)')
MD_LINK_RE = re.compile(r'(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)')


def strip_markdown(text, is_target, removed):
    def img_repl(m):
        if is_target(m.group(1)):
            removed.append(m.group(0)[:120])
            return ''
        return m.group(0)

    def link_repl(m):
        if is_target(m.group(2)):
            removed.append(m.group(0)[:120])
            return m.group(1)          # 文字だけ残す
        return m.group(0)

    text = MD_IMG_RE.sub(img_repl, text)
    text = MD_LINK_RE.sub(link_repl, text)
    return text


def strip_bare_urls(text, is_target, removed):
    """本文中に裸で書かれたURLを消す。"""
    def repl(m):
        if is_target(m.group(0)):
            removed.append(m.group(0)[:120])
            return ''
        return m.group(0)
    return URL_RE.sub(repl, text)


def tidy(text):
    """除去後に残った空行・空タグを軽く整える。"""
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def strip_file(path, text, is_target):
    ext = os.path.splitext(path)[1].lower()
    removed = []
    if ext in ('.html', '.htm', '.php'):
        out = strip_html(text, is_target, removed)
        out = strip_bare_urls(out, is_target, removed)
    elif ext in ('.md', '.markdown'):
        out = strip_markdown(text, is_target, removed)
        out = strip_bare_urls(out, is_target, removed)
    elif ext == '.txt':
        out = strip_bare_urls(text, is_target, removed)
    else:
        return None, []
    return tidy(out), removed


# ---------------------------------------------------------------- 出力

def backup_dir_name(base):
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(base, 'dmm_affiliate_backup_' + stamp)


def report(hits, scanned, root):
    print('=' * 68)
    print('DMM/FANZA アフィリエイトリンク 検出結果')
    print('=' * 68)
    print('対象フォルダ : %s' % os.path.abspath(root))
    print('読んだファイル: %d 件' % scanned)
    print()

    affiliate = [h for h in hits if h.kind == 'affiliate']
    plain = [h for h in hits if h.kind == 'plain']

    if not affiliate and not plain:
        print('DMM/FANZA のリンクは1件も見つからなかった。')
        print('このフォルダが申請サイトの中身で間違いないか確認すること。')
        return affiliate, plain

    # --- アフィリエイトID別（審査で問題になるのはここ）
    if affiliate:
        ids = {}
        for h in affiliate:
            key = h.af_id or '(IDなし: バナー/ウィジェット/API)'
            ids.setdefault(key, []).append(h)
        print('■ 検出されたアフィリエイトID')
        print('  DMMは登録サイトごとに専用IDを発行する。')
        print('  このサイト用に発行されたID以外が出ていたら、それが不承認の原因。')
        print()
        # IDが判明しているものを先に、多い順で
        def sort_key(k):
            return (k.startswith('('), -len(ids[k]), k)
        for key in sorted(ids, key=sort_key):
            group = ids[key]
            files = len({h.path for h in group})
            print('    %s  →  %d箇所 / %d ファイル' % (key, len(group), files))
        print()

    # --- ファイル別（= 削除対象の「掲載記事」）
    if affiliate:
        by_file = {}
        for h in affiliate:
            by_file.setdefault(h.path, []).append(h)
        print('■ アフィリエイトリンクを含むファイル（=削除対象の掲載記事） %d件' % len(by_file))
        print()
        for path in sorted(by_file):
            rel = os.path.relpath(path, root) if os.path.isdir(root) else path
            print('  %s  (%d箇所)' % (rel, len(by_file[path])))
            for h in by_file[path][:5]:
                print('      L%-5d %s' % (h.line, h.url[:110]))
            if len(by_file[path]) > 5:
                print('      ... 他 %d箇所' % (len(by_file[path]) - 5))
        print()

    # --- 参考: アフィリエイトではないDMMリンク
    if plain:
        pf = sorted({h.path for h in plain})
        print('■ 参考: アフィリエイトIDなしのDMMリンク %d箇所 / %d ファイル' % (len(plain), len(pf)))
        print('  審査の直接の原因ではないが、念のため中身は確認しておくこと。')
        for path in pf[:10]:
            rel = os.path.relpath(path, root) if os.path.isdir(root) else path
            print('    %s' % rel)
        if len(pf) > 10:
            print('    ... 他 %d ファイル' % (len(pf) - 10))
        print()

    # --- 自動除去できないファイル
    manual = sorted({h.path for h in affiliate
                     if os.path.splitext(h.path)[1].lower() not in STRIPPABLE_EXTS})
    if manual:
        print('■ 手動で直す必要があるファイル %d件' % len(manual))
        print('  JS/JSON/テンプレート等は自動で消すと壊れる可能性があるため対象外にしている。')
        for path in manual:
            rel = os.path.relpath(path, root) if os.path.isdir(root) else path
            print('    %s' % rel)
        print()

    return affiliate, plain


# ---------------------------------------------------------------- 実行

def do_strip(hits, root, apply_changes, is_target):
    targets = sorted({h.path for h in hits
                      if os.path.splitext(h.path)[1].lower() in STRIPPABLE_EXTS})
    if not targets:
        print('自動除去の対象ファイルはなかった。')
        return

    base = root if os.path.isdir(root) else os.path.dirname(os.path.abspath(root))
    bdir = backup_dir_name(base)

    print('=' * 68)
    print('リンク除去 %s' % ('【実行】' if apply_changes else '【プレビュー / 変更しません】'))
    print('=' * 68)

    changed = 0
    total_removed = 0
    for path in targets:
        text = read_text(path)
        if text is None:
            continue
        out, removed = strip_file(path, text, is_target)
        if out is None or out == text:
            continue
        changed += 1
        total_removed += len(removed)
        rel = os.path.relpath(path, base)
        print('  %s  (%d箇所を除去)' % (rel, len(removed)))
        for r in removed[:3]:
            print('      - %s' % r.replace('\n', ' ')[:100])
        if len(removed) > 3:
            print('      - ... 他 %d箇所' % (len(removed) - 3))
        if apply_changes:
            dest = os.path.join(bdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(path, dest)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(out)

    print()
    print('  ファイル %d件 / 合計 %d箇所' % (changed, total_removed))
    if apply_changes:
        print('  変更前のファイルは %s に退避した。' % bdir)
    else:
        print('  実際に書き換えるには --apply を付けて再実行する。')
    print()


def do_quarantine(hits, root, apply_changes):
    targets = sorted({h.path for h in hits})
    if not targets:
        print('隔離対象のファイルはなかった。')
        return

    base = root if os.path.isdir(root) else os.path.dirname(os.path.abspath(root))
    bdir = backup_dir_name(base)

    print('=' * 68)
    print('記事の隔離 %s' % ('【実行】' if apply_changes else '【プレビュー / 変更しません】'))
    print('=' * 68)
    print('  アフィリエイトリンクを含むファイルを、削除せず退避先へ移動する。')
    print()
    for path in targets:
        rel = os.path.relpath(path, base)
        print('  %s' % rel)
        if apply_changes:
            dest = os.path.join(bdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(path, dest)
    print()
    print('  %d ファイル' % len(targets))
    if apply_changes:
        print('  退避先: %s' % bdir)
        print('  （戻したくなったらこのフォルダから元の場所へコピーし直す）')
    else:
        print('  実際に移動するには --apply を付けて再実行する。')
    print()


def next_steps():
    print('=' * 68)
    print('このあとの手順')
    print('=' * 68)
    print("""
  1. 上のリンクを全て消した状態でサイトを本番環境にアップする
     （ローカルだけ直しても審査は公開中のページを見るので意味がない）

  2. 消し忘れがないか、公開中のサイトをブラウザで再確認する
     見落としやすいのは本文以外:
       - サイドバー / フッター / ヘッダーのバナー
       - 共通テンプレート、ウィジェット
       - 過去記事、下書きではなく公開済みの古い記事
       - RSS / サイトマップ / AMPページ
       - 検索エンジンのキャッシュではなく実ページ

  3. DMMアフィリエイトの管理画面からサイトの再審査を申請する

  4. 承認されたら、そのサイト専用に発行された af_id で
     リンクを貼り直す（ここで初めてリンクを置ける）

  重要: 3 と 4 の順番は入れ替えられない。
  リンクを置いたまま再申請すると、同じ理由でまた落ちる。
""")


def main():
    p = argparse.ArgumentParser(
        description='DMM/FANZAアフィリエイトリンクを検出・除去する',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument('path', help='申請サイトのフォルダ（またはファイル）')
    p.add_argument('--strip', action='store_true',
                   help='リンクだけを取り除く（記事本文は残す）')
    p.add_argument('--quarantine', action='store_true',
                   help='リンクを含むファイルごと退避する')
    p.add_argument('--apply', action='store_true',
                   help='実際にファイルを変更する（付けなければプレビューのみ）')
    p.add_argument('--all-dmm', action='store_true',
                   help='アフィリエイトIDが無いDMMリンクも対象にする')
    p.add_argument('--ext', action='append', default=[],
                   help='走査する拡張子を追加（例: --ext .inc）')
    p.add_argument('--json', metavar='FILE',
                   help='検出結果をJSONで書き出す')
    args = p.parse_args()

    if not os.path.exists(args.path):
        print('見つからない: %s' % args.path, file=sys.stderr)
        return 2
    if args.strip and args.quarantine:
        print('--strip と --quarantine は同時に指定できない', file=sys.stderr)
        return 2

    extra = [e if e.startswith('.') else '.' + e for e in args.ext]
    hits, scanned = scan(args.path, extra)
    affiliate, plain = report(hits, scanned, args.path)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump([{'path': h.path, 'line': h.line, 'url': h.url,
                        'kind': h.kind, 'af_id': h.af_id, 'context': h.context}
                       for h in hits], f, ensure_ascii=False, indent=2)
        print('JSONを書き出した: %s' % args.json)
        print()

    work = hits if args.all_dmm else affiliate
    is_target = make_matcher(args.all_dmm)

    if args.strip:
        do_strip(work, args.path, args.apply, is_target)
    elif args.quarantine:
        do_quarantine(work, args.path, args.apply)

    if affiliate:
        next_steps()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
