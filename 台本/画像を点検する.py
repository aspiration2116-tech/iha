#!/usr/bin/env python3
"""生成した画像を点検する。抜け・重複・使い回しを機械的に見つける。

    python3 台本/画像を点検する.py [画像フォルダ]

既定のフォルダは 画像/扇風機/。ファイル名は C001.png / T-01.png の形式。

**使い回しの検出が主目的。** 同じ画像を別のカットに使うと、
「再利用されたコンテンツ」の判定に近づく。ハッシュで機械的に潰す。
"""
import hashlib
import re
import sys
from pathlib import Path

FOLDER = Path(sys.argv[1] if len(sys.argv) > 1 else "画像/扇風機")
PROMPTS = Path("台本/2026-10_扇風機しまう前_Lovart貼り付け用.txt")


def expected() -> list[str]:
    """貼り付け用ファイルから、あるべきカット番号を読む。"""
    if not PROMPTS.exists():
        sys.exit(f"{PROMPTS} が見つかりません")
    txt = PROMPTS.read_text(encoding="utf-8")
    return re.findall(r"^\[((?:T-\d+|C\d+))[^\]]*\]$", txt, re.M)


def labels() -> dict[str, str]:
    """カット番号 → 台本の文（どのシーンの絵か）。

    見出しは `[C001（S01）｜来年の夏、…。]` の形。「｜」の**後ろ**が台本の文。
    シーン番号だけ出しても、どの絵かは分からない。
    """
    txt = PROMPTS.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^\[((?:T-\d+|C\d+))([^\]]*)\]$", txt, re.M):
        parts = m.group(2).split("｜")
        out[m.group(1)] = parts[1].strip() if len(parts) > 1 else m.group(2).strip()
    return out


def main() -> None:
    want = expected()
    label = labels()

    if not FOLDER.exists():
        sys.exit(f"{FOLDER} がありません。画像を置いてから実行してください。")

    found: dict[str, Path] = {}
    for f in sorted(FOLDER.iterdir()):
        m = re.fullmatch(r"((?:T-\d+|C\d+))\.(png|jpg|jpeg|webp)", f.name, re.I)
        if m:
            found[m.group(1)] = f

    print(f"あるべき {len(want)} カット / 見つかった {len(found)} カット\n")

    # ① 抜け
    missing = [c for c in want if c not in found]
    if missing:
        print(f"■ 足りないカット — {len(missing)}件")
        for c in missing[:20]:
            print(f"  {c}  {label.get(c, '')[:50]}")
        if len(missing) > 20:
            print(f"  … 他 {len(missing) - 20}件（まだ作っていないだけなら気にしなくてよい）")
    else:
        print("■ 足りないカット: なし")

    # ② 余分（台本に無い番号）
    extra = sorted(set(found) - set(want))
    print(f"\n■ 台本に無い番号のファイル: {extra or 'なし'}")

    # ③ 中身が同じ画像（＝使い回し）
    by_hash: dict[str, list[str]] = {}
    small: list[str] = []
    for cut, path in found.items():
        data = path.read_bytes()
        if len(data) < 10_000:
            small.append(f"{cut} ({len(data):,}バイト)")
        by_hash.setdefault(hashlib.sha256(data).hexdigest(), []).append(cut)

    dupes = [v for v in by_hash.values() if len(v) > 1]
    if dupes:
        print(f"\n■ 中身が同じ画像 — {len(dupes)}組（**使い回し。作り直すこと**）")
        for group in dupes:
            print(f"  {' = '.join(sorted(group))}")
            for c in sorted(group):
                print(f"      {c}: {label.get(c, '')[:56]}")
    else:
        print("\n■ 中身が同じ画像: なし")

    # ④ 壊れ・極端に小さい
    print(f"■ 極端に小さいファイル: {small or 'なし'}")

    if missing or extra or dupes or small:
        print("\n✗ 直すところがあります。")
        sys.exit(1)
    print(f"\n✓ {len(found)}カット、すべて揃っていて重複なし。")


if __name__ == "__main__":
    main()
