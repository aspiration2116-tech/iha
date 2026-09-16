#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台本からカット表を読み、Lovart用プロンプト集を生成する。
   時刻・行数は台本から自動計算するので、台本を直したら再実行すること。
     python3 gen_prompts.py ../台本/01_披露宴_定食屋の親_原稿.md > lovart_プロンプト集.md
"""
import re, sys

STYLE = ("Japanese manga illustration for a narrated story video, cel shading, "
         "clean bold ink outlines, muted desaturated palette, soft cinematic key light, "
         "16:9 widescreen, no text, no speech bubbles")
NEG = ("text, letters, kanji, hiragana, captions, speech bubbles, watermark, signature, "
       "logo, extra fingers, malformed hands, blurry, lowres, 3d render, photo, "
       "western cartoon, chibi, oversaturated")

# id: (場面名, 英語プロンプト本体, 構図・注意)
P = {
1:("開宴の問い","wide shot of a hushed 120-guest hotel banquet hall, crystal chandeliers, round tables, an elderly man in a dark navy suit standing at the head table with a microphone, an older woman in a black kurotomesode kimono frozen mid-smile, all faces turned toward her","**最重要カット。サムネ候補。** 老人は後ろ姿ぎみ、義母の顔に焦点。義母の血の気が引く瞬間"),
2:("義母の宣告","medium shot of an older Japanese woman in a pastel twin-set and pearls, chin slightly raised, faint smile that does not reach her eyes, soft-focus hotel lounge background","義母の顔の寄り。上品さと侮蔑を同居させる"),
3:("みやこ食堂","interior of a small Showa-era shotengai diner, worn wooden counter seating eight, handwritten paper menus on the wall, an old man in a white cook coat and towel headband working behind the counter, steam rising","店の全景。看板・のれんは文字なしで形だけ"),
4:("父の手","extreme close-up of an old man's hands on a cutting board, thick knuckles, cracked skin, faded burn scars, holding a kitchen knife","手だけ。顔は入れない。この台本の中心の絵"),
5:("五歳の回想","warm sepia-toned memory scene, a small girl about five years old crying at the end of a diner counter, an elderly man in a grey jacket holding out a wrapped candy to her without looking at her","回想なのでセピア寄り。老人は目を合わせていない"),
6:("白い手袋","close-up of a young woman's hands placing a boxed pair of white formal gloves into a wooden drawer, evening light from a window","手元のみ。手袋は畳まれて箱の中"),
7:("とん汁","a young businessman in a navy suit at a diner counter, both hands around a bowl of pork miso soup, eyes closed, genuinely moved","涼介の善良だった頃。表情は本物の感動"),
8:("病院の廊下","a young man in a wrinkled suit asleep sitting upright on a hospital corridor bench at night, fluorescent light, an old man in pajamas standing in a doorway watching him","涼介の善良さの証拠。この絵が後半で効く"),
9:("常務が口ぐせ","a young businessman in a suit checking his phone on a station platform, expression gone cold, city lights bokeh","同じ人物が変わったことを、同じ服・違う目で見せる"),
10:("握られなかった手","**KEY** a formal tatami room in an expensive ryotei, an old man in an ill-fitting charcoal suit bowing slightly with his weathered hand extended forward, an older woman in a pale kimono seated upright, hands folded in her lap, not taking his hand, the extended hand hanging in empty air","**構図を必ず覚えておく。転落パートで同じ構図・同じ角度を使う。** 手が宙に浮いた瞬間"),
11:("帰りの電車","night train interior, an old man in a suit seated by the window, his own reflection in the dark glass, rubbing the back of one hand with the other thumb, a young woman seated beside him looking at his hands","父の背中と窓の反射。会話は見せない"),
12:("母の指輪","close-up of a thin worn gold ring with one small stone, held between an old man's fingers and a young woman's fingers, over a diner counter after closing","指輪は質素に。三十五年前のもの"),
13:("廊下のささやき","hotel corridor, an older woman in a kimono speaking quietly to a young man in a suit, a young woman standing further down the corridor within earshot, back turned","聞こえる距離。結衣は背中"),
14:("振込明細","close-up of a bank transfer receipt slip placed face-up on a diner counter, an old man's weathered hand withdrawing from it, a young woman's hand reaching toward it","紙の文字は書かない。形と余白だけ"),
15:("招待状の束","a bridal planning room, a stack of printed wedding invitations on a table, an older woman in a twin-set pushing them forward with two fingers, a young woman looking down at them, a young man beside her looking at his phone","三人の視線が全部バラバラなのが要点"),
16:("手術のあと","a hospital room, an old man just waking from anesthesia, oxygen tube, a young woman at the bedside holding the rail, morning light","八時間の心臓手術の三週間前"),
17:("鼻で笑う","close-up of a young man's face, a small dismissive laugh through the nose, eyes not smiling, blurred older woman behind him","涼介の転落点。小さく、鼻で"),
18:("受諾","medium close-up of a young woman, expression calm, the faintest smile, not sad, not angry, hotel meeting room background out of focus","**泣かせない。** ここから披露宴まで、この顔を崩さない"),
19:("プランナー","a wedding planner in a navy uniform suit at a counter, holding a clipboard, hesitating, a young woman facing her","プランナーはためらっている"),
20:("駅までの道","evening street, a young couple walking apart from each other, the man half-turned back speaking, the woman looking ahead","二人の距離が主題"),
21:("パンフレットの父","a living room in an old house, an old man in a cardigan seated at a low table looking at a glossy wedding-venue brochure, a framed photograph of a woman beside him, a young woman standing in the doorway","**母の写真をここで置く。顔は映さない**(写真立ての背または逆光)"),
22:("鷹野の家の門","night, the gate of an old wooden Japanese house, a young woman's hand gripping a single envelope, warm light from inside","門の前。人物は手だけ"),
23:("鷹野との約束","interior of an old Japanese house, an elderly man with swept-back white hair seated formally, looking steadily at a young woman seated across from him, a single envelope on the tatami between them","老人が長いこと見ている"),
24:("会長だと明かす","**KEY** a magazine-cover style portrait of an elderly Japanese man in a dark navy suit, white hair, sharp deep-set eyes, arms folded, corporate office background","正体を見せるカット。威厳を出す"),
25:("空席の親族席","**KEY** a grand hotel banquet hall filled with 120 guests, one table of empty chairs conspicuously untouched at the front left, chandeliers","空席だけが浮いて見える構図"),
26:("お守り","close-up of a small clutch bag on a bridal seat, two folded documents just visible inside","介添えに預けたバッグ。開けていない"),
27:("マウント","an older woman in a black kurotomesode kimono speaking to seated guests, one hand raised elegantly, guests smiling politely","義母の得意の絶頂"),
28:("常務に","the same older woman leaning toward a middle-aged man in a grey suit at the head table, confiding, the man looking uncomfortable","黒田は困っている"),
29:("ロビーの一時間","**KEY** a hotel lobby, an elderly man in a dark navy suit sitting alone upright on a chair, a single envelope resting on his knees, doors to the banquet hall closed behind him","動かない八十二歳。ここが反転のエンジン"),
30:("扉が開く","**KEY** the banquet hall doors opening, a hotel manager in black tailcoat and white gloves escorting an elderly man in a dark navy suit inside, guests turning, a man in a grey suit dropping a glass","黒田がグラスを落とす瞬間"),
31:("席を譲る","a middle-aged man in a grey suit standing up and gesturing to his own seat at the head table, an elderly man in a navy suit standing beside him, the hall watching","格の逆転を絵にする"),
32:("祝辞","**KEY** an elderly man in a dark navy suit standing with a microphone at the head table, speaking quietly, 120 guests listening, an older woman in black kimono clutching a folded fan tucked in her obi","**末広は開かせない。** 帯に挿したまま握る"),
33:("マイクを取る","**KEY** a bride in a colored formal gown standing and taking the microphone, face completely calm, the hall silent, an older woman in black kimono half-risen in panic","結衣は怒っていない。冷えている"),
34:("窓口係","an older woman in black kimono, mouth slightly open, all composure gone, another woman in a formal kimono beside her having just spoken, guests staring","義母が初めて本音を出す直前"),
35:("指輪をはめる","close-up of a bride's right hand sliding a thin old gold ring onto her own finger, the hall blurred behind","右手。婚約指輪ではないという宣言"),
36:("扇子が落ちる","**KEY** a folded Japanese fan slipping from an obi and lying on a banquet hall carpet, a black kimono hem beside it, nobody reaching for it","拾う人がいないことが要点。上から見た構図"),
37:("退場","a bride walking alone toward the banquet hall doors, back to camera, chin level, a young man in formal wear half-reaching after her","振り返らない"),
38:("宙に浮いた手","**KEY — 加害①の鏡** a banquet hall, an older woman in black kimono having rushed forward with her hand extended, an elderly man in a navy suit looking at the offered hand without taking it, bowing once, the hand hanging in empty air, guests watching","**カット10と同じ構図・同じ角度・手の主だけ入れ替える。** これが台本の円を閉じる絵"),
39:("転落","a corporate meeting room, three executives bowing deeply to an empty chair-side, grey atmosphere / a young man packing a desk box","契約打ち切りと九州行き。2枚に割ってもよい"),
40:("鳴り続ける電話","**KEY** the entrance of a house seen through frosted glass, the silhouette of a black formal kimono hanging on a garment rack, a telephone on a stand, nobody coming","**義母の顔は出さない。** 磨りガラス越しのシルエットだけ"),
41:("水曜の昼","the diner, an elderly man in a grey jacket ducking under the noren curtain, the old cook behind the counter looking up, warm daylight","二人の四十年が見える距離感"),
42:("臨時休業","**KEY** close-up of an old paper schedule sheet pinned to a kitchen wall, one square marked with two handwritten characters, kitchen out of focus behind","文字は書かない。書くなら墨で二文字のみ、崩して読めなくてよい"),
43:("玄関の袋","**KEY** a house entryway, a folded morning-coat rental bag left on the floor, a photo frame standing beside it turned away from the viewer, only its back and stand visible","**母の顔は絶対に映さない。** 写真立ての背だけ"),
44:("厨房に立つ","a young woman in a white chef coat standing behind the diner counter, an old man watching from the customer side, steam, warm light","立ち位置が入れ替わっている"),
45:("白い手袋をはめる","**KEY — ラスト** close-up under a noren curtain at night, a young woman sliding a white formal glove onto an old man's weathered hand","**エンドカード候補。** 手だけ。顔は入れない"),
46:("エンド","the diner noren curtain at night from outside, warm light inside, empty street","CTAとチャンネル名を乗せる下地。中央を空ける"),
}
# 長いブロックは2枚目・3枚目を推奨
EXTRA = {
10:["the same ryotei room from the old man's side, his own weathered hand in the foreground still extended, the seated woman small and distant"],
11:["close-up of an old man's hand rubbing his own knuckles on his lap, train window light moving across it"],
13:["close-up of an older woman's face in profile, speaking, faint satisfied smile"],
15:["close-up of a young man's face lit from below by a phone screen, not looking up"],
18:["close-up of a young woman's eyes, calm, a single unshed brightness, no tears"],
21:["close-up of an old man's hands quietly closing a glossy brochure"],
29:["close-up of an elderly man's hands resting on a single envelope on his knees, a hotel clock on the wall behind"],
30:["close-up of an older woman's face as recognition hits, all color gone"],
32:["close-up of an elderly man's face speaking, eyes down, remembering"],
33:["reverse shot from behind the bride toward 120 guests, all faces turned to her"],
39:["a small regional train platform, a young man alone with a suitcase, four relatives seeing him off"],
44:["close-up of a bowl of pork miso soup set down on a counter, a man's hands receiving it"],
}

def blocks(path):
    body = open(path, encoding="utf-8").read().split("# 台本本文")[1].split("# 概要欄")[0]
    out, cur = [], {"sec": "", "note": "", "lines": [], "n": 0.0}
    def push():
        if cur["lines"]: out.append(dict(cur))
    for raw in body.split("\n"):
        t = raw.strip()
        if t.startswith("## "):
            push(); cur.update(sec=re.sub(r'^##\s*', '', t), note="", lines=[], n=0.0); continue
        if t.startswith("### "): continue
        if t == "---":
            push(); cur.update(note="", lines=[], n=0.0); continue
        if t.startswith("> ト書き"):
            push(); cur.update(note=re.sub(r'^>\s*ト書き[::]\s*', '', t), lines=[], n=0.0); continue
        if t.startswith(">"): continue
        m = re.match(r'^\*\*【無音([\d.]+)秒】\*\*$', t)
        if m: cur["n"] += float(m.group(1)) * 5; continue
        m = re.match(r'^\*\*([^*]{1,8})\*\*(.+)$', t)
        if m: cur["lines"].append((m.group(1), m.group(2))); cur["n"] += len(m.group(2))
    push()
    return out

def mmss(x): return f"{int(x)//60}:{int(x)%60:02d}"

def main(path):
    bs = blocks(path)
    assert len(bs) == len(P), f"ブロック数 {len(bs)} と プロンプト数 {len(P)} が不一致"
    print(open(__file__.replace("gen_prompts.py", "_header.md"), encoding="utf-8").read())
    t = 0.0; total_imgs = 0
    sec_now = None
    for i, b in enumerate(bs, 1):
        d = b["n"] / 5
        name, prompt, memo = P[i]
        if b["sec"] != sec_now:
            sec_now = b["sec"]
            print(f"\n## {sec_now}\n")
        extras = EXTRA.get(i, [])
        total_imgs += 1 + len(extras)
        print(f"### カット{i:02d} 「{name}」　`{mmss(t)}` 〜　{d:.0f}秒 / {len(b['lines'])}行")
        print()
        print(f"> **ト書き(台本):** {b['note'] or '(なし)'}")
        print(f">")
        print(f"> **メモ:** {memo}")
        print()
        print(f"**ファイル名 `images/cut{i:02d}.png`**")
        print()
        print("```")
        print(f"{STYLE}, {prompt}")
        print("```")
        for j, ex in enumerate(extras, 1):
            print(f"\n**追加 `images/cut{i:02d}{chr(96+j)}.png`**(この場面は{d:.0f}秒あるので2枚目を推奨)")
            print()
            print("```")
            print(f"{STYLE}, {ex}")
            print("```")
        print()
        t += d
    print(f"\n---\n\n**必須 {len(bs)}枚 / 推奨を含めて {total_imgs}枚。総尺 {mmss(t)}。**\n")
    print("## 共通ネガティブプロンプト\n")
    print("```")
    print(NEG)
    print("```")

main(sys.argv[1])
