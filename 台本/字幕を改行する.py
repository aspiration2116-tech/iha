#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vrewの.vrewファイルの字幕を「1〜2行」に改行し、削れる「、」を落とす。

    python3 台本/字幕を改行する.py 入力.vrew 出力.vrew [1行の上限字数=29]

**字幕(captions)だけを書き換える。** words / assets / tracks / ttsClipInfosMap /
メディア(mp3・png) には一切触らないので、**音声はそのまま使える**（字幕と音声は別フィールド）。
文字サイズ(globalCaptionStyle)も触らない。

上限は29字。30字だと実機で行があふれて3行になる恐れがある（150サイズ時）。

`integrity` は再計算できないため据え置き。前回も据え置きでVrewが受け付けた。
"""

# ── 改行の方針 ──────────────────────────────────────────────
# 文節境界でしか切らない（語の途中で切らない）。そのうえで意味のまとまりを守る:
#   ・連体修飾は割らない          「〜の／名詞」「終わった／株」
#   ・補助動詞の前で割らない      「応援して／いただける」
#   ・複合動詞を割らない          「重ねて／置いた」（て・で＋動詞）
#   ・並立は割らない              「物と／物」「枝豆や／大豆」
#   ・「にも・とも」は句の一部    ただし「では・には」は主題の切れ目なので切ってよい
#   ・格助詞の直後は避ける        「さやが／できた」は述語が離れる
# 「、」は、削ると語がくっついて読めなくなるものと、列挙のものだけ残す。
from janome.tokenizer import Tokenizer
_t = Tokenizer()

CONTENT = {"名詞","動詞","形容詞","副詞","連体詞","接続詞","感動詞","接頭詞"}
AUX = {"なく","ない","にくい","やすい","たい","ほしい","よい","いい","なる","なり","ある","あり",
       "いる","おく","くる","みる","しまう","ください","くれる","もらう","過ぎ","すぎ","始め","出し",
       "こと","もの","とき","ところ","ため","はず","わけ","うち","まま","だけ","ほど","くらい"}

def toks(s):
    out=[]; pos=0
    for t in _t.tokenize(s):
        sf=t.surface; ps=t.part_of_speech.split(',')
        out.append((pos, sf, ps, t.infl_form)); pos+=len(sf)
    return out

def starts(s):
    T=toks(s); st=set()
    for i,(p,sf,ps,_f) in enumerate(T):
        if i==0 or ps[0] not in CONTENT: continue
        if len(ps)>1 and ps[1] in ("接尾","非自立"): continue
        if sf in AUX: continue
        prev=T[i-1]
        if prev[2][0] in ("助詞","助動詞") or prev[1] in ("、","。","」","）"):
            st.add(p)
    return st

def _enum_commas(s):
    """列挙の「、」（体言を並べているもの）は全部残す"""
    T=toks(s)
    cpos=[i for i,(p,sf,ps,_f) in enumerate(T) if sf=="、"]
    keep=set()
    for a,b in zip(cpos, cpos[1:]):
        seg=T[a+1:b]
        if not seg or sum(len(x[1]) for x in seg)>9: continue
        if seg[-1][2][0]=="名詞":
            keep.add(T[a][0]); keep.add(T[b][0])
    return keep

def must_keep(s):
    T=toks(s); keep=_enum_commas(s)
    for i,(p,sf,ps,_f) in enumerate(T):
        if sf!="、" or i==0 or i+1>=len(T): continue
        a=T[i-1][2]; b=T[i+1][2]; asf=T[i-1][1]
        if a[0]=="動詞" and b[0]=="名詞" and (len(b)<2 or b[1] not in ("非自立",)):
            keep.add(p); continue
        if a[0]!="名詞" or (len(a)>1 and a[1] in ("非自立","副詞可能","接尾")): continue
        if len(asf)>3: continue
        if b[0] in ("名詞","連体詞","形容詞"): keep.add(p)
    return keep

def strip_commas(s):
    keep=must_keep(s)
    return ''.join(ch for i,ch in enumerate(s) if ch!='、' or i in keep)

FORBID_PREV = {"の"}

def _tokmap(s):
    T=toks(s); end={}; start={}
    for i,(q,sf,ps,f) in enumerate(T):
        end[q+len(sf)]=i; start[q]=i
    return T, end, start

def _penalty(s, p):
    T,end,start = _tokmap(s)
    if p not in end: return 100
    i=end[p]; sf,ps,f = T[i][1],T[i][2],T[i][3]
    nxt = T[start[p]] if p in start else None
    prev2 = T[i-1] if i>0 else None

    # 連体修飾は割らない（「〜の／名詞」「終わった／株」）
    if sf in FORBID_PREV: return 1000
    if nxt and nxt[2][0]=="名詞" and (
        (ps[0]=="助動詞" and sf in ("た","だ","な")) or
        (ps[0]=="動詞" and f and ("連体" in f or "基本形" in f)) or
        (ps[0]=="形容詞" and f and ("連体" in f or "基本形" in f))):
        return 300
    # 補助動詞の前では割らない（応援して／いただける、立てて／おかない）
    if nxt and nxt[2][0]=="動詞" and len(nxt[2])>1 and nxt[2][1]=="非自立": return 300
    # 「て・で＋動詞」の複合動詞は割らない（重ねて／置いた、持ち上げて／見る）
    if sf in ("て","で") and ps[0]=="助詞" and nxt and nxt[2][0]=="動詞": return 20
    # 並立（物と物／枝豆や大豆）は割らない
    if ps[0]=="助詞" and ps[1]=="並立助詞": return 20
    # 係助詞は、直前が助詞なら句の一部（にも・とも・では）。名詞直後なら主題の切れ目
    # 「にも・とも」は句の一部。「では・には」は主題の切れ目として自然
    if ps[0]=="助詞" and ps[1]=="係助詞":
        return 20 if (sf=="も" and prev2 and prev2[2][0]=="助詞") else 0
    if ps[0]=="助詞" and ps[1]=="接続助詞": return 0
    if sf=="、": return 0
    if ps[0]=="助動詞": return 1
    if ps[0]=="動詞" and f and ("連用" in f or "基本形" in f): return 1
    if ps[0]=="助詞" and ps[1]=="格助詞": return 8
    if ps[0]=="助詞" and ps[1]=="副助詞": return 6
    return 4

def split2(s, limit=30):
    if len(s)<=limit: return [s]
    cand=[]
    for p in sorted(q for q in starts(s) if 0<q<len(s)):
        a,b=s[:p],s[p:]
        if not a.strip() or not b.strip(): continue
        if len(a)>limit or len(b)>limit: continue
        cand.append((_penalty(s,p), abs(len(a)-len(b)), [a,b]))
    if not cand:   # limit に収まる割り方が無ければ、収まらなくても最善を採る
        for p in sorted(q for q in starts(s) if 0<q<len(s)):
            a,b=s[:p],s[p:]
            if not a.strip() or not b.strip(): continue
            cand.append((_penalty(s,p)+max(0,max(len(a),len(b))-limit)*3, abs(len(a)-len(b)), [a,b]))
    if not cand: return [s]
    cand.sort(key=lambda x:(x[0],x[1]))
    return [x.strip('、') for x in cand[0][2]]

def layout(s, limit=29):
    """1〜2行に整えた行のリストを返す。行頭・行末の「、」は必ず落とす
    （Vrewで読点の位置でクリップを分割すると、末尾が「、」で終わる字幕ができる）。"""
    out = split2(strip_commas(s), limit)
    return [x.strip('、') for x in out]


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json, zipfile, collections
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src_path, dst_path = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 29

    src = zipfile.ZipFile(src_path)
    p = json.loads(src.read("project.json"))
    clips = p["transcript"]["clips"]
    before = after = 0
    n1 = n2 = 0
    for c in clips:
        cur = "".join("".join(i.get("insert", "") for i in b["text"])
                      for b in (c.get("captions") or [])).replace("\n", "")
        before += cur.count("、")
        L = layout(cur, limit)
        after += sum(x.count("、") for x in L)
        if len(L) == 1:
            c["captions"] = [{"text": [{"insert": L[0] + "\n"}]},
                             {"text": [{"insert": "\n"}]}]
            n1 += 1
        else:
            c["captions"] = [{"text": [{"insert": L[0] + "\n"}]},
                             {"text": [{"insert": L[1] + "\n"}]}]
            n2 += 1
        d = c.get("dirty") or {}
        c["dirty"] = {"blankDeleted": d.get("blankDeleted", False),
                      "caption": True, "video": d.get("video", False)}

    body = json.dumps(p, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8")
    out = zipfile.ZipFile(dst_path, "w", zipfile.ZIP_STORED)
    for info in src.infolist():
        data = body if info.filename == "project.json" else src.read(info.filename)
        ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        ni.compress_type = zipfile.ZIP_STORED
        ni.external_attr = info.external_attr
        out.writestr(ni, data)
    out.close()

    # 検証（落ちたら書き出したファイルを使わないこと）
    b = zipfile.ZipFile(dst_path)
    assert src.namelist() == b.namelist(), "エントリの構成が変わった"
    media = [f for f in src.namelist() if f != "project.json" and src.read(f) != b.read(f)]
    assert not media, f"メディアが変化した: {media[:3]}"
    pb = json.loads(b.read("project.json"))
    assert pb["props"]["globalCaptionStyle"]["quillStyle"]["size"] == \
           p["props"]["globalCaptionStyle"]["quillStyle"]["size"], "文字サイズが変わった"
    L = [[ "".join(i.get("insert", "") for i in bl["text"]).replace("\n", "")
           for bl in c["captions"]] for c in pb["transcript"]["clips"]]
    L = [[y for y in x if y.strip()] for x in L]
    assert not [x for x in L if len(x) > 2], "3行になった字幕がある"
    assert not [x for x in L if not x], "空の字幕がある"
    mx = max(len(y) for x in L for y in x)
    assert mx <= limit, f"上限{limit}字を超えた行がある（{mx}字）"
    # 語の途中で切っていないか
    for i, x in enumerate(L):
        if len(x) < 2:
            continue
        j = "".join(x)
        bnd = {q for q, _sf, _ps, _f in toks(j)} | {len(j)}
        assert len(x[0]) in bnd, f"clip{i}: 語の途中で改行した"
    print(f"1行 {n1}件 ／ 2行 {n2}件 ／ 最長 {mx}字 ／ 3行 0件 ／ 語中改行 0件")
    print(f"「、」 {before} → {after}")
    print(f"メディア{len(src.namelist())-1}件はバイト一致。文字サイズと音声（words/tts）は不変。")
