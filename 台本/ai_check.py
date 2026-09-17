#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI感・無駄・テンポを機械で落とす

    python3 ai_check.py 台本.md

「AI感がある」は感想ではなく、**分布と語彙**に出る癖です。
台本01で人間味を出すためにやったことを、そのまま検査項目にしました。

  ① 感情の名指し   … 「悲しい」「悔しい」と書いた瞬間、読者は感じなくなる
  ② 既製品の比喩   … 「時間が止まったよう」「胸が締めつけられる」は誰の言葉でもない
  ③ 副詞の重ね     … 「ただ、静かに」「ゆっくりと、そっと」はAIの手癖
  ④ 説明の接続     … 「つまり」「だから」「それは」で始まる地の文は解説
  ⑤ 同語の近接反復 … 3文以内に同じ語が出ると、書き手が語彙で困って見える
  ⑥ 言い換えの重複 … 直前の文と語が6割かぶる文は、同じことを二度言っている
  ⑦ 「のです」癖   … 「〜のです/のでした」が多いと講義口調になる
  ⑧ 体言止めの連続 … 3つ続くと詩になって、物語が止まる
  ⑨ 主語の出しすぎ … 日本語は主語を省く。「私は」が多いと翻訳調
  ⑩ 語彙の狭さ     … 述べ語数に対する異なり語数
"""
import re, sys, collections

EMO = ["悲しい","悲しく","悔しい","悔しく","嬉しい","嬉しく","切ない","苦しい","辛い","つらい",
       "寂しい","寂しく","腹立たしい","情けない","恥ずかしい","怖い","怖く",
       "胸が","心が","胸の奥","心の奥","涙が出","涙がこぼれ","込み上げ","こみ上げ"]
CLICHE = ["時間が止まった","時が止まった","息を呑","息をのん","胸が締めつけ","胸を締めつけ",
          "凍りついた","凍り付いた","目の前が真っ暗","頭が真っ白",
          "血の気が引","背筋が凍","鳥肌が","言葉を失","立ち尽く","呆然と",
          "堰を切った","走馬灯","手に取るように","痛いほど","嵐のような","針のむしろ"]
ADV2 = re.compile(r'(ただ|そっと|ゆっくり|静かに|じっと|ふと|やがて|次第に|徐々に|ゆるやかに)'
                  r'[、,]\s*(そっと|ゆっくり|静かに|じっと|ただ|やがて|次第に|徐々に)')
CONJ = ("つまり","だから","それは","そして、","しかし、","なぜなら","要するに","ですから",
        "そのため","したがって","このように","そうして")

def load(path):
    s = open(path, encoding="utf-8").read()
    body = s.split("# 台本本文")[1].split("# 概要欄")[0]
    out = []
    for raw in body.split("\n"):
        t = raw.strip()
        if not t or t == "---" or t.startswith((">", "#", "|", "`")): continue
        if t.startswith("**【"): continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*(.+)$', t)
        if m: out.append((m.group(1), m.group(2).strip()))
    return out

def sents(text):
    return [x for x in re.split(r'(?<=[。！？!?])', text) if x.strip()]

def words(s):
    return set(re.findall(r'[一-鿿ぁ-んァ-ヴー]{2,}', s))

def main(path):
    items = load(path)
    narr = [(i, t) for i, (sp, t) in enumerate(items) if not t.lstrip().startswith("「")]
    alltext = "".join(t for _, t in items)
    hits = collections.defaultdict(list)
    print(f"検査: {path}\n発話 {len(items)} / 地の文 {len(narr)}\n")

    # ① 感情の名指し / ② 既製品の比喩
    for i, t in narr:
        for w in EMO:
            if w in t: hits["① 感情の名指し"].append((i, t, w))
        for w in CLICHE:
            if w in t: hits["② 既製品の比喩"].append((i, t, w))
        m = ADV2.search(t)
        if m: hits["③ 副詞の重ね"].append((i, t, m.group(0)))
        for c in CONJ:
            if t.startswith(c): hits["④ 説明の接続"].append((i, t, c))

    # ⑤ 同語の近接反復(地の文のみ・3発話以内)
    NG = {"ました","ません","でした","そうです","ところ","こと","もの","とき","ため"}
    for k in range(len(narr) - 1):
        i, a = narr[k]
        for j, b in narr[k+1:k+4]:
            common = (words(a) & words(b)) - NG
            common = {w for w in common if len(w) >= 3}
            if common: hits["⑤ 同語の近接反復"].append((i, f"{a} ／ {b}", "・".join(sorted(common))))
            break

    # ⑥ 言い換えの重複(直前の文と語が6割かぶる)
    for k in range(1, len(narr)):
        i, b = narr[k]; _, a = narr[k-1]
        wa, wb = words(a), words(b)
        if wa and wb:
            ov = len(wa & wb) / min(len(wa), len(wb))
            if ov >= 0.6: hits["⑥ 言い換えの重複"].append((i, f"{a} ／ {b}", f"{ov:.0%}かぶり"))

    # ⑦ のです癖
    NODA = re.compile(r'([るたいない]のです|[るたいない]のでした|(?<![まませ])んです|(?<![まませ])んでした)[。」]?$')
    nod = [(i, t) for i, t in narr if NODA.search(t)]
    # ⑧ 体言止めの連続
    run = 0
    for i, t in narr:
        end = t.rstrip("。」』)】!?…")
        taigen = bool(re.search(r'[一-鿿ァ-ヴー]$', end)) and not re.search(r'(ました|ます|です|ません|でした|ない|た|る)$', end)
        if taigen:
            run += 1
            if run >= 3: hits["⑧ 体言止めの連続"].append((i, t, f"{run}連続"))
        else: run = 0
    # ⑨ 主語の出しすぎ
    watashi = sum(1 for _, t in narr if t.startswith("私は") or t.startswith("私が"))

    for k in sorted(hits):
        v = hits[k]
        print(f"=== {k}  {len(v)}件")
        for i, t, w in v[:8]:
            print(f"  [{i:3d}] {t[:56]}   ← {w}")
        if len(v) > 8: print(f"  …ほか {len(v)-8}件")
        print()

    print(f"=== ⑦ 「のです」癖  {len(nod)}件 / 地の文{len(narr)} = {len(nod)/max(1,len(narr)):.0%}"
          f"  {'← 多い(8%以下に)' if len(nod)/max(1,len(narr)) > .08 else '✅'}")
    for i, t in nod[:5]: print(f"  [{i:3d}] {t[:56]}")
    print(f"\n=== ⑨ 「私は/私が」で始まる地の文  {watashi}件 = {watashi/max(1,len(narr)):.0%}"
          f"  {'← 多い(6%以下に)' if watashi/max(1,len(narr)) > .06 else '✅'}")
    STOP = {"ました","ません","でした","ですか","そうです","ところ","こと","もの","とき","ため",
            "ました。","します","そして","それで","でも、"}
    toks = [w for _, t in narr for w in re.findall(r'[一-鿿]{2,4}', t)]
    top = [(w, c) for w, c in collections.Counter(toks).most_common(40)
           if w not in STOP and c >= 5]
    print("\n=== ⑩ 地の文の頻出語(同じ語に頼っていないか。人名・題材語は除いて読む)")
    print("  " + " / ".join(f"{w}×{c}" for w, c in top[:12]))
    bad = sum(len(v) for v in hits.values())
    print(f"\n{'─'*60}\n①〜⑥⑧の指摘 {bad}件。**0件を目指す**。")

main(sys.argv[1])
