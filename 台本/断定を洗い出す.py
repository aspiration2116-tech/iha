#!/usr/bin/env python3
"""台本の本文から「事実の断定」を機械的に抜き出し、末尾の A表/B表 と突き合わせる。

    python3 台本/断定を洗い出す.py 台本/<台本>.md

**このコマンドを通さずに台本を公開しない。**
目視での突き合わせは10回連続で漏れた。漏れはいつも同じ場所で起きている
（尺を伸ばすために後から書き足した文）。だから機械で抜く。

出す情報は5つ。

1. **表から参照されていないシーン**のうち、事実の主張を含むもの
   → これが「表に無い断定」。1つずつ、A表に出典を足すか、B表に運用として書くか、
     表現を弱めるかを決める。判断はできないので、人が決める。
2. **表が参照しているのに存在しないシーン番号**（番号を振り直したあとの付け替え漏れ）
3. **空のシーン**（マーカーだけで本文が無い）
4. **枝番のまま残っているシーン**（振り直し漏れ）
5. **表の主張と、参照先の本文が噛み合っていない行**
   → 番号が生きていても、中身が入れ替わっていることがある。実際に起きた：
     本文から消した主張（「後ろに手をかざすと吸い寄せられる」）の行が表に残り、
     番号を振り直したせいで**無関係なシーンを指していた**。番号の存在確認だけでは
     絶対に見つからない。だから表の主張と本文の文字の重なりを測る。

判定はしない。「疑うべき場所」を漏れなく出すだけ。
"""
import re
import sys

# 事実の主張が入りうる文の目印。断定の語尾、数字、伝聞。
CLAIM = re.compile(r"ます。|です。|ません。|でした。|\d|と言われ|とされ|報告されて|パーセント|割")

# 事実の主張を含まない、定型・呼びかけ・段取りだけの文。
# 行頭一致だけだと「この動画が役に立ったら…高評価と」のようなCTAを拾ってしまうので、
# 定型の語が**どこかに**入っていて、かつ出典の要る語（数字・伝聞）が無い文を落とす。
BOILERPLATE = re.compile(
    r"ご視聴|チャンネル登録|高評価|HYPE|ハイプ|コメント欄|覚えて帰って|行きましょう|"
    r"お話しします|説明書|次の動画|最後までご覧"
)
# 出典が要る語。これが入っていたら定型でも落とさない。
NEEDS_SOURCE = re.compile(r"\d|[〇一二三四五六七八九十百千万]+(?:年|件|割|パーセント|度|%)|"
                          r"と言われ|とされ|報告されて|データ|調査|統計")


def scenes_of(body: str) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    cur = None
    for line in body.split("\n"):
        s = line.strip()
        m = re.fullmatch(r"\*\*(S\d+[a-z]?)\*\*", s)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        if not s or s[0] in "#|>" or s.startswith("---"):
            continue
        if cur:
            out[cur].append(s.replace("**", ""))
    return {k: "".join(v) for k, v in out.items()}


def bigrams(s: str) -> set[str]:
    # 数字は落とす。台本は「三十年」、表は出典どおり「30年」と書くので、
    # 数字を残すと同じ主張でも一致率が落ちて、本物の食い違いが埋もれる。
    # 数字そのものの正しさは出典欄で人が見る。ここで測るのは「同じ話をしているか」。
    s = re.sub(r"[、。「」──…・／/（）()＋\s*|]|S\d+[a-z]?|[0-9〇一二三四五六七八九十百千万年度件割%]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def table_rows(tail: str) -> list[tuple[str, list[str]]]:
    """A表/B表の各行から（主張のセル, その行が挙げるシーン番号）を取り出す。

    見るのは「## 事実の根拠」以降だけ。自己チェックや改稿ログの表は、
    1列目が「S49」「B表 S45」のような**見出しラベル**なので、主張として比べられない。
    """
    rows = []
    i = tail.find("## 事実の根拠")
    if i < 0:
        return rows
    for line in tail[i:].split("\n"):
        if not line.startswith("|") or re.fullmatch(r"[|\-: ]+", line.strip()):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        ids = re.findall(r"S\d+[a-z]?", cells[0]) if cells else []
        if ids:
            rows.append((cells[0], ids))
    return rows


def main() -> None:
    path = sys.argv[1]
    txt = open(path, encoding="utf-8").read()

    start = txt.index("## 【")
    rest = txt[start:]
    # 本編の終わり = 時刻のない「## 」見出し（タイトル・事実の根拠・改稿ログなど）
    end = next((m.start() for m in re.finditer(r"\n## (?!【)", rest)), len(rest))
    body, tail = rest[:end], rest[end:]

    scenes = scenes_of(body)
    # 参照とみなすのは A表/B表 だけ。改稿ログや自己チェックは「S40bを消した」と
    # **消した番号を書くのが正しい**ので、そこを参照に数えると必ず誤検出になる。
    i = tail.find("## 事実の根拠")
    referenced = set(re.findall(r"S\d+[a-z]?", tail[i:] if i >= 0 else ""))

    print(f"本編 {len(scenes)} シーン / 表が参照 {len(referenced & set(scenes))} シーン\n")
    if not referenced:
        print("⚠ A表/B表がシーン番号を1つも挙げていない。①は本編全体、⑤は検査不能。")
        print("  表を別の台本に委ねている場合は、**この台本にも シーン番号つきの表を持たせること。**")
        print("  番号が無い表は、本文を書き換えても食い違いが機械では見つからない。\n")

    # ① 表に無い断定
    flagged = [
        (sid, text) for sid, text in scenes.items()
        if sid not in referenced and CLAIM.search(text)
        and not (BOILERPLATE.search(text) and not NEEDS_SOURCE.search(text))
    ]
    if flagged:
        print(f"■ 表に無い断定の候補 — {len(flagged)}件（1つずつ処理すること）\n")
        for sid, text in flagged:
            print(f"  {sid}: {text[:78]}")
    else:
        print("■ 表に無い断定の候補: なし")

    # ② 表が参照しているのに存在しない番号
    ghosts = sorted(referenced - set(scenes), key=lambda s: int(re.match(r"S(\d+)", s).group(1)))
    print(f"\n■ 表が参照しているのに本文に無い番号: {ghosts or 'なし'}")

    # ③ 空のシーン
    empty = [s for s, t in scenes.items() if not t]
    print(f"■ 空のシーン: {empty or 'なし'}")

    # ④ 枝番（振り直し漏れ）
    branch = [s for s in scenes if re.search(r"[a-z]$", s)]
    print(f"■ 枝番のまま残っているシーン: {branch or 'なし'}")

    # ⑤ 表の主張と参照先の本文が噛み合っているか
    # 主張のセルと、その行が挙げるシーン本文の、2文字の重なりを見る。
    # 本文から消した主張が表に残っていると、ここで一致率が落ちる。
    stale = []
    for claim, ids in table_rows(tail):
        body_text = "".join(scenes.get(i, "") for i in ids)
        want = bigrams(claim)
        if len(want) < 6:  # 「S45」のような短いラベル。比べるだけの中身が無い
            continue
        hit = len(want & bigrams(body_text)) / len(want)
        if hit < 0.15:
            stale.append((ids, round(hit * 100), claim))
    if stale:
        print(f"\n■ 表の主張と本文が噛み合っていない行 — {len(stale)}件")
        print("  （本文から消した主張が表に残っていないか。番号の指し先が入れ替わっていないか）\n")
        for ids, pct, claim in stale:
            print(f"  {'・'.join(ids)}  一致 {pct}%  「{claim[:44]}」")
            print(f"      本文: {''.join(scenes.get(i, '') for i in ids)[:62]}")
    else:
        print("\n■ 表の主張と本文が噛み合っていない行: なし")

    # ①は「読む一覧」。つなぎ・問いかけ・段取りが必ず混ざるので、ゼロにはならないし、
    # ゼロを目指すと表が意味の無い行で膨れる。**毎回ぜんぶ目を通す**のが使い方。
    # ②〜⑤は機械的に間違っている。こちらだけで落とす。
    if ghosts or empty or branch or stale:
        print("\n✗ ②〜⑤に該当あり。直すまで公開しない。")
        sys.exit(1)
    print(f"\n✓ ②〜⑤は問題なし。①の{len(flagged)}件は目視で1件ずつ判断すること。")


if __name__ == "__main__":
    main()
