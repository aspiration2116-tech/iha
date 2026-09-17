#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台本のVOICEVOX読み・アクセント検査(OpenJTalk実機版)

  apt-get install -y open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
  python3 njd_check.py 台本.md

VOICEVOXのG2Pは OpenJTalk + naist-jdic。本ツールはその実機を直接叩くので、
読み・アクセント型・アクセント句境界が「推測ではなく実測」で得られる。

NJD出力の各フィールド:
  表層, 品詞, 品詞細分類1..3, 活用型, 活用形, 原形, 読み, 発音, アクセント型/モーラ数, 連結規則, 連結フラグ
  ・発音       … 実際に喋られるカナ(連濁・促音・長音の適用後)
  ・アクセント型 … 核の位置。0=平板
  ・連結フラグ  … 0ならここから新しいアクセント句が始まる
"""
import re, subprocess, sys, tempfile, os, collections

DIC   = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"

def njd(text):
    """テキストを OpenJTalk に通し、NJD解析結果を返す"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text + "\n"); src = f.name
    tr = src + ".trace"
    subprocess.run(["open_jtalk", "-x", DIC, "-m", VOICE, "-ot", tr, "-ow", "/dev/null", src],
                   capture_output=True)
    out = open(tr, encoding="utf-8").read()
    os.unlink(src); os.unlink(tr)
    if "[Text analysis result]" not in out: return []
    body = out.split("[Text analysis result]")[1].split("[Output label]")[0]
    rows = []
    for line in body.strip().split("\n"):
        c = line.split(",")
        if len(c) < 13: continue
        rows.append({
            "surface": c[0], "pos": c[1], "pos1": c[2], "pos2": c[3],
            "read": c[8], "pron": c[9], "acc": c[10], "chain": c[12],
        })
    return rows

def norm(p):
    """アクセント核マーカーを除き、長音表記を統一して比較用に正規化"""
    p = p.replace("'", "").replace("\u2019", "")
    p = re.sub(r'([ウオコソトノホモヨロゴゾドボポョクグスズツヅヌフブプムユルュ])ウ', lambda m: m.group(1) + "ー", p)
    p = re.sub(r'([ケセテネヘメレゲゼデベペェ])イ', lambda m: m.group(1) + "ー", p)
    # オ段+オ も長音(十日 トオカ = トーカ)。期待リストの表記ゆれで誤検知していた。
    p = re.sub(r'([ウオコソトノホモヨロゴゾドボポョ])オ', lambda m: m.group(1) + "ー", p)
    return p

def phrases(rows):
    """連結フラグからアクセント句に区切る"""
    out, cur = [], []
    for r in rows:
        if r["pos"] == "記号":
            if cur: out.append(cur); cur = []
            continue
        if r["chain"] == "0" and cur:
            out.append(cur); cur = []
        cur.append(r)
    if cur: out.append(cur)
    return out

SPEAKER = re.compile(r'\*\*[^*]{1,10}\*\*')
KANJI   = re.compile(r'[一-鿿]')

def load(path):
    src = open(path, encoding="utf-8").read()
    body = src.split("# 台本本文")[1].split("# 概要欄")[0] if "# 台本本文" in src else src
    out = []
    for i, l in enumerate(body.split("\n")):
        s = l.strip()
        if not s or s == "---" or s.startswith((">", "#", "|", "-", "`")): continue
        if s.startswith("**【無音"): continue
        s = SPEAKER.sub("", s).replace("**", "")
        s = re.sub(r'\((小声で|心の声)\)', '', s)
        if s: out.append((i + 1, s))
    return out

# 正しい発音が確定している語(ここに足していく)
EXPECT = {
    "話": "ハナシ",   # 「こんな話」→ コンナバナシ の連濁を拾う
    "中村":"ナカムラ","結衣":"ユイ","健一":"ケンイチ","神崎":"カンザキ","政子":"マサコ",
    "涼介":"リョウスケ","鷹野":"タカノ","誠一":"セイイチ","黒田":"クロダ",
    "通帳":"ツウチョウ","入口":"イリグチ","司会者":"シカイシャ","女房":"ニョウボウ",
    "主賓":"シュヒン","一言":"ヒトコト","半年":"ハントシ","実家":"ジッカ","義母":"ギボ",
    "背筋":"セスジ","宛名":"アテナ","飴":"アメ","箸":"ハシ","髪":"カミ",
    "金":"カネ","司会":"シカイ","白髪":"シラガ","日本":"ニホン","方":"カタ",
    "十分":"ジップン","十五分":"ジューゴフン","一分":"イップン","十日":"トオカ",
    # 台本02(墓・法事)で実機確認した語
    "森口":"モリグチ","和夫":"カズオ","辰次":"タツジ","芳江":"ヨシエ","久美":"クミ",
    "大西":"オーニシ","泰然":"タイゼン","堤":"ツツミ","誠":"マコト",
    "数珠":"ジュズ","寄進":"キシン","施主":"セシュ","読経":"ドキョウ","位牌":"イハイ",
    "焼香":"ショウコウ","霊園":"レイエン","山門":"サンモン","戒名":"カイミョウ",
    "庫裏":"クリ","導師":"ドウシ","年忌":"ネンキ","回忌":"カイキ","法要":"ホウヨウ",
    "無縁仏":"ムエンボトケ","卒塔婆":"ソトバ","檀家":"ダンカ","彼岸":"ヒガン",
    "供養":"クヨウ","命日":"メイニチ","一座":"イチザ","本堂":"ホンドウ","土間":"ドマ",
    "墓石":"ハカイシ","石段":"イシダン","石屋":"イシヤ","墨染め":"スミゾメ",
    "形見":"カタミ","戸籍":"コセキ","名義":"メイギ","仏間":"ブツマ","喪服":"モフク",
    "遺骨":"イコツ","骨":"ホネ","過去":"カコ","帳":"チョウ","外柵":"ガイサク",
    "出生":"シュッショウ","白木":"シラキ","親父":"オヤジ","跡取り":"アトトリ",
}
# 固有名詞(1アクセント句にまとまっているべきもの)
NAMES = ["中村結衣","中村健一","神崎涼介","神崎政子","鷹野誠一","鷹野物産","東洋通商","みやこ食堂",
         "森口菜穂","森口辰次","森口和夫","大西泰然","堤芳江","妙相寺"]

def main(path):
    lines = load(path)
    unknown, mism, splits = [], [], collections.Counter()
    longph = []
    # 同じ表記が、台本の中で別の読みになっていないか(白石 → シライシ / ハクセキ)
    seen_read = collections.defaultdict(dict)
    for ln, s in lines:
        rows = njd(s)
        for r in rows:
            sf, pr = r["surface"], r["pron"]
            if KANJI.search(sf) and (pr in ("*", "") or r["pos1"] == "サ変接続" and pr == "*"):
                unknown.append((ln, sf, s[:46]))
            # 接尾辞は複合語の一部(奨学金=ショーガクキン、退職金=タイショクキン)。
            # 単独の語として立っているときだけ期待読みと比べる。
            if sf in EXPECT and r["pos1"] != "接尾" and norm(pr) != norm(EXPECT[sf]):
                mism.append((ln, sf, pr, EXPECT[sf], s[:46]))
            if KANJI.search(sf) and pr not in ("*", ""):
                seen_read[sf].setdefault(norm(pr), (ln, pr, s[:46]))
        # 固有名詞のアクセント句分割
        for ph in phrases(rows):
            txt = "".join(x["surface"] for x in ph)
            if len(ph) >= 1:
                mora = sum(int(x["acc"].split("/")[1]) for x in ph if "/" in x["acc"])
                if mora >= 13:
                    longph.append((ln, txt, mora))
        joined = [x["surface"] for x in rows]
        for nm in NAMES:
            if nm in s and nm not in joined:
                # nm が複数アクセント句にまたがるか
                ph_txts = ["".join(x["surface"] for x in p) for p in phrases(rows)]
                if not any(nm in p for p in ph_txts):
                    splits[nm] += 1

    print(f"検査: {path}  ({len(lines)}行)  engine=open_jtalk/naist-jdic\n")
    print("=== ① 発音が生成できない語 ===");  print("  なし" if not unknown else "")
    for ln, sf, s in unknown: print(f"  L{ln}  {sf}\n        {s}")
    print("\n=== ② 期待発音と不一致 ===");  print("  なし" if not mism else "")
    for ln, sf, pr, want, s in mism: print(f"  L{ln}  「{sf}」→ {pr}  期待:{want}\n        {s}")
    print("\n=== ③ 固有名詞が複数アクセント句に分割 ===");  print("  なし" if not splits else "")
    for nm, c in splits.most_common(): print(f"  {nm}  ({c}箇所)  → 辞書登録で1句にまとめる")
    # ⑤ 1モーラのアクセント句 = 語の切れ目を間違えている強い兆候
    #    例「三年かよいました」→ サンネンカ / ヨイマシタ(「か」が前に吸われる)
    tiny = []
    for ln, s2 in lines:
        rows = njd(s2)
        for ph in phrases(rows):
            mora = sum(int(x["acc"].split("/")[1]) for x in ph if "/" in x["acc"])
            txt = "".join(x["surface"] for x in ph)
            # 助詞などのかな1文字は正常。漢字を含む1モーラ句だけが危険(手→シュ/テ など)
            if mora == 1 and KANJI.search(txt):
                tiny.append((ln, txt, "".join(x["pron"] for x in ph), s2[:40]))
    # ⑥ 数詞+助数詞で読みが割れやすい語(期待リストに無くても機械で拾う)
    RISK = ["一日", "二日", "七日", "八日", "二十日",
            "十分", "一分", "三分", "十日", "一行", "一目", "一手", "一言", "上手", "下手",
            "人気", "大事", "最中", "生物", "色紙", "一目散", "何時",
            "白髪", "見物", "風車"]
    risky = []
    for ln, s2 in lines:
        for w in RISK:
            if w in s2:
                rows = njd(w)
                risky.append((ln, w, "".join(x["pron"] for x in rows).replace("\u2019", ""), s2[:40]))

    print("\n=== ⑤ 1モーラのアクセント句(語の切れ目を誤っている兆候) ===")
    print("  なし" if not tiny else "")
    for ln, txt, pr, s2 in tiny[:20]:
        print(f"  L{ln}  「{txt}」→ {pr}\n        {s2}")
    if len(tiny) > 20: print(f"  …ほか {len(tiny)-20}件")

    print("\n=== ⑥ 読みが割れやすい語(出現したら必ず実機で確認) ===")
    print("  なし" if not risky else "")
    seen_r = set()
    for ln, w, pr, s2 in risky:
        if w in seen_r: continue
        seen_r.add(w)
        print(f"  「{w}」→ 単独では {pr}   (L{ln} ほか)")

    # ⑦ 助詞の「は・へ・を」が隣の語に飲まれる事故
    #   助詞の「は」はワと読む。名詞(漢字・カタカナ)の直後の「は」が
    #   助詞として立っていなければ、次の語に飲まれている。
    #   例:「私はね」→ ワタシ・ハネ、「手に職はね」→ テニショク・ハネ
    NOUN_END = re.compile(r'[\u4e00-\u9fff\u30a0-\u30ff\u3005]')
    KANA_ONLY = re.compile(r'^[\u3041-\u3093]+$')
    eaten, eaten_maybe = [], []
    for ln, s2 in lines:
        if not any(c in s2 for c in "はへを"):
            continue
        at = 0
        for r in njd(s2):
            sf = r["surface"]
            i = s2.find(sf, at)
            if i < 0: continue
            at = i + len(sf)
            if r["pos"] == "助詞": continue
            if not (sf and sf[0] in "はへを" and KANA_ONLY.match(sf)): continue
            if i > 0 and NOUN_END.match(s2[i-1]):
                # 名詞どうしは複合語のことがある(往復はがき = オーフクハガキ で正しい)。
                # 助詞を飲んだ動詞・形容詞・副詞・感動詞だけを事故として数える。
                bucket = eaten if r["pos"] != "名詞" else eaten_maybe
                bucket.append((ln, s2[max(0,i-3):i] + sf, r["pron"], s2[:40]))

    # ⑧ 語句単位の期待読み(1語ずつでは正しくても、並ぶと崩れるもの)
    PHRASE = {
        "三分の一": "サンブンノイチ", "三分の二": "サンブンノニ",
        "二分の一": "ニブンノイチ", "四分の一": "ヨンブンノイチ",
        "四分の三": "ヨンブンノサン", "五分の一": "ゴブンノイチ",
        "十分の一": "ジュウブンノイチ",
    }
    phr = []
    for ln, s2 in lines:
        for w, exp in PHRASE.items():
            if w in s2:
                got = "".join(x["pron"] for x in njd(w))
                if norm(got) != norm(exp):
                    phr.append((ln, w, got, exp, s2[:40]))

    # ⑨ 同じ表記が台本の中で別々に読まれている
    #   台本03の 柏木「白石」が ハクセキ、「白石。」なら シライシ だった。
    #   期待リストに無い固有名詞は①②で拾えないので、台本の中の不一致で見つける。
    incon = [(sf, d) for sf, d in seen_read.items() if len(d) > 1]

    print("\n=== ⑨ 同じ表記が台本の中で別々に読まれている ===")
    print("  なし" if not incon else "")
    for sf, d in incon[:20]:
        print(f"  「{sf}」")
        for _, (ln, pr, s2) in sorted(d.items(), key=lambda kv: kv[1][0]):
            print(f"      L{ln}  → {pr}    {s2}")
    if len(incon) > 20: print(f"  …ほか {len(incon)-20}語")

    print("\n=== ⑦ 助詞が隣の語に飲まれている(は→ハ、へ→ヘ) ===")
    print("  なし" if not eaten else "")
    for ln, txt, pr, s2 in eaten[:20]:
        print(f"  L{ln}  「{txt}」→ {pr}   ※助詞ならワ/エ")
        print(f"        {s2}")
    if len(eaten) > 20: print(f"  …ほか {len(eaten)-20}件")
    if eaten_maybe:
        print("  (要確認・複合語なら正しい)")
        for ln, txt, pr, s2 in eaten_maybe[:10]:
            print(f"  L{ln}  「{txt}」→ {pr}")

    print("\n=== ⑧ 語句で崩れる読み ===")
    print("  なし" if not phr else "")
    seen_p = set()
    for ln, w, got, exp, s2 in phr:
        if w in seen_p: continue
        seen_p.add(w)
        print(f"  L{ln}  「{w}」→ {got}   (正しくは {exp})")
        print(f"        {s2}")

    print("\n=== ④ 長すぎるアクセント句(13モーラ超・不自然になりやすい) ===")
    print("  なし" if not longph else "")
    for ln, txt, m in longph[:20]: print(f"  L{ln}  {txt} ({m}モーラ)  → 読点で割る")
    ng = len(unknown) + len(mism) + len(eaten) + len(incon) + len({w for _, w, _, _, _ in phr})
    print(f"\n{'❌ 要修正 ' + str(ng) + '件' if ng else '✅ 読み事故なし'}")
    return 1 if ng else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "01_披露宴_定食屋の親.md"))
