#!/usr/bin/env python3
"""台本のナレーション文字数を数えて、各セクションの時刻を計算し直す。

    python3 台本/尺を数える.py 台本/2026-09_秋のダニ_台本.md          # 数えるだけ
    python3 台本/尺を数える.py 台本/2026-09_秋のダニ_台本.md --write   # 見出しの時刻を書き換える

台本を書き換えたら必ず --write で通すこと。手で書いた尺は、これまで4回とも間違っていた。
数えるのは「## 【時刻】見出し」から「## タイトル・サムネ」の直前まで。
見出し・シーン番号（**S01** など）・表・引用・区切り線は除外し、句読点も除いた実文字数で数える。
"""
import re
import sys

CPM = 320  # 1分あたりの文字数。50〜60代向けのゆったりした読みの目安


def mmss(minutes: float) -> str:
    return f"{int(minutes)}:{round((minutes - int(minutes)) * 60):02d}"


def count(section_body: str) -> int:
    lines = []
    for line in section_body.split("\n"):
        t = line.strip()
        if not t or t[0] in "#|>" or t.startswith("---"):
            continue
        if re.fullmatch(r"\*\*S[\w]+[^*]*\*\*", t):  # シーン番号
            continue
        lines.append(t.replace("**", ""))
    return len(re.sub(r"[、。「」──…・（）]", "", "".join(lines)))


def main() -> None:
    path = sys.argv[1]
    write = "--write" in sys.argv
    txt = open(path, encoding="utf-8").read()

    body = txt[txt.index("## 【"):txt.index("## タイトル・サムネ")]
    sections = [s for s in re.split(r"\n(?=## )", body) if s.strip()]

    total = sum(count(s) for s in sections)
    print(f"合計 {total:,}字 → {mmss(total / CPM)}（{CPM}字/分）")
    print(f"  350字/分なら {mmss(total / 350)} / 300字/分なら {mmss(total / 300)}\n")

    cumulative = 0
    for sec in sections:
        head = sec.split("\n")[0].strip()
        n = count(sec)
        start, cumulative = cumulative / CPM, cumulative + n
        title = re.sub(r"^## (【\d+:\d+〜\d+:\d+】)?", "", head)
        new_head = f"## 【{mmss(start)}〜{mmss(cumulative / CPM)}】{title}"
        print(f"{new_head}  ({n}字)")
        if write:
            txt = txt.replace(head + "\n", new_head + "\n", 1)

    if write:
        txt = re.sub(r"- \*\*想定尺: [\d:]+\*\*（ナレーション実測 [\d,]+字",
                     f"- **想定尺: {mmss(total / CPM)}**（ナレーション実測 {total:,}字", txt)
        txt = re.sub(r"※ 毎分320字は50〜60代向けのゆったりした読みの目安。350字/分なら[\d:]+、300字/分なら[\d:]+。",
                     f"※ 毎分320字は50〜60代向けのゆったりした読みの目安。"
                     f"350字/分なら{mmss(total / 350)}、300字/分なら{mmss(total / 300)}。", txt)
        open(path, "w", encoding="utf-8").write(txt)
        print("\n書き換えました。")


if __name__ == "__main__":
    main()
