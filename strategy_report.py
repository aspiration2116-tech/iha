#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""チャンネルの現在地と、次に何を作るかを1枚にまとめる (戦略レポート.md)。

ネタ候補.md が「いま伸びている個別の動画」を並べるのに対して、
こちらは一段引いて「自分のチャンネルがどうなっているか」を見る。

  ・月ごとの成績と、直近の連投がカニバっていないか
  ・タイトルの型は "ch内比"(そのチャンネルの中央値に対する倍率)で見る
    再生数そのままだと、大きいチャンネルがよく使う型が上に来るだけになる
  ・非属人チャンネルの伸び方(1本だけ跳ねる構造)の確認

使い方: python3 strategy_report.py  → 戦略レポート.md を書き出す
"""

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import analysis
import research
from analysis import fmt_views, median

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "戦略レポート.md")

# テーマ分類。ネタの偏り(カニバリ)と、テーマごとの地力を見るために使う
TOPICS = [
    ("エアコン・電気代", r"エアコン|電気代|室外機|冷房|暖房|光熱費"),
    ("暑さ・熱中症", r"熱中症|暑さ|猛暑|熱帯夜|涼し|夏バテ"),
    ("寒さ・結露・乾燥", r"寒|結露|乾燥|静電気|冷え|加湿"),
    ("害虫", r"ゴキブリ|蚊|ハチ|蜂|虫|ダニ|ムカデ|クモ|蜘蛛|アリ|コバエ|カメムシ|ノミ"),
    ("掃除・水回り", r"掃除|排水|カビ|ヌメリ|水垢|トイレ|風呂|換気扇"),
    ("洗濯・衣類", r"洗濯|洗剤|柔軟剤|部屋干し|衣替え|クローゼット|タンス"),
    ("収納・片付け", r"収納|片付|断捨離|捨て|手放"),
    ("食べ物・保存", r"食べ|料理|野菜|肉|米|パン|冷凍|保存|調味|弁当|冷蔵庫"),
    ("健康・睡眠・体", r"健康|睡眠|布団|寝|血圧|血糖|疲れ|老化|寿命|腸|自律神経|免疫"),
    ("お金・節約", r"節約|お金|年金|保険|税|家計|貯|安く|無料"),
    ("100均", r"100均|百均|ダイソー|セリア|キャンドゥ|スリコ"),
    ("スマホ・家電設定", r"スマホ|iPhone|Android|LINE|Google|Wi-?Fi|設定"),
    ("防犯・防災", r"空き巣|防犯|泥棒|台風|停電|防災|地震"),
    ("庭・雑草", r"雑草|庭|草|ベランダ|網戸"),
]


def topic_of(title):
    for name, pat in TOPICS:
        if re.search(pat, title or ""):
            return name
    return "その他"


def by_month(mine):
    d = defaultdict(list)
    for v in mine:
        if v["published_at"]:
            d[v["published_at"][:7]].append(v["views"] or 0)
    return d


def main():
    con = research.connect()
    cfg = research.load_config()
    videos = analysis.load_videos(con)
    mine = sorted([v for v in videos if v["is_self"]],
                  key=lambda v: v["published_at"] or "")
    rivals = [v for v in videos if not v["is_self"]]
    if not mine:
        print("自分の動画が記録されていません。先に python3 research.py を実行してください。")
        return 1

    subs = next((v["channel_subs"] for v in mine if v["channel_subs"]), None)
    self_med = median([v["views"] for v in mine if v["views"] is not None])
    L = []
    L.append("# 戦略レポート (%s 時点)\n" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    L.append("データ最終収集: %s\n" % (con.execute(
        "SELECT MAX(ts) FROM runs").fetchone()[0] or "-")[:16])

    # ---- 1. 現在地
    L.append("## 1. 現在地\n")
    L.append("- 自分の動画 %d本 / 中央値 %s回" % (len(mine), fmt_views(self_med)))
    if subs:
        L.append("- 登録者 %s人 に対して中央値 %s回 = **%.1f%%**  "
                 "(登録者が動画を見に来ているかの目安。低いほどバズ由来の登録者が戻って来ていない)"
                 % (fmt_views(subs), fmt_views(self_med), 100.0 * self_med / subs))
    L.append("- 同ジャンル(直近90日)の中央値: %s回" %
             fmt_views(median([v["views"] for v in rivals
                               if v["age_days"] and v["age_days"] <= 90])))
    L.append("\n| 月 | 本数 | 中央値 | 最大 |")
    L.append("|---|---:|---:|---:|")
    for m in sorted(by_month(mine)):
        vs = by_month(mine)[m]
        L.append("| %s | %d | %s | %s |" % (m, len(vs), fmt_views(median(vs)), fmt_views(max(vs))))

    # ---- 2. 直近の投稿とカニバリ
    L.append("\n## 2. 直近の投稿（新しい順）\n")
    L.append("| 公開 | 再生 | テーマ | タイトル |")
    L.append("|---|---:|---|---|")
    recent = list(reversed(mine))[:15]
    for v in recent:
        L.append("| %s | %s | %s | %s |" % (
            (v["published_at"] or "")[:10], fmt_views(v["views"]),
            topic_of(v["title"]), v["title"].replace("|", "/")[:48]))
    cann = defaultdict(list)
    for v in recent:
        cann[topic_of(v["title"])].append(v)
    heavy = sorted([(len(vs), t, vs) for t, vs in cann.items() if len(vs) >= 3], reverse=True)
    if heavy:
        L.append("\n**同じテーマの連投**（直近%d本のうち）" % len(recent))
        for n, t, vs in heavy:
            L.append("- %s: %d本 / 中央値 %s回 … 同じテーマを続けると後から出した方が食われる"
                     % (t, n, fmt_views(median([x["views"] or 0 for x in vs]))))

    # ---- 3. タイトルの型
    L.append("\n## 3. タイトルの型（ch内比で評価）\n")
    L.append("ch内比 = その動画がそのチャンネルの中央値の何倍か、の中央値。"
             "チャンネルの大小を打ち消しているので、**次に付けるタイトルはこの数字で選ぶ**。1.0 = 平均的な動画。\n")
    pats = [p for p in analysis.title_patterns(rivals, min_n=6) if p["median_multiple"]]
    pats.sort(key=lambda p: -p["median_multiple"])
    self_titles = [v["title"] for v in mine]
    L.append("| 型 | 競合での本数 | ch内比 | 再生中央値 | 自分の使用 |")
    L.append("|---|---:|---:|---:|---:|")
    for p in pats:
        rx = re.compile(dict(analysis.PATTERNS)[p["name"]])
        used = sum(1 for t in self_titles if rx.search(t or ""))
        L.append("| %s | %d | **%.2fx** | %s | %d/%d本 |" % (
            p["name"], p["count"], p["median_multiple"],
            fmt_views(p["median_views"]), used, len(mine)))

    # ---- 4. テーマ別の地力
    L.append("\n## 4. テーマ別の成績（競合・直近180日）\n")
    L.append("| テーマ | 本数 | 中央値 | 最大 | 自分の本数 |")
    L.append("|---|---:|---:|---:|---:|")
    rec_r = [v for v in rivals if v["age_days"] and v["age_days"] <= 180]
    tv = defaultdict(list)
    for v in rec_r:
        tv[topic_of(v["title"])].append(v)
    mt = defaultdict(int)
    for v in mine:
        mt[topic_of(v["title"])] += 1
    for t, vs in sorted(tv.items(), key=lambda kv: -median([x["views"] or 0 for x in kv[1]])):
        if len(vs) < 4 or t == "その他":
            continue
        L.append("| %s | %d | %s | %s | %d |" % (
            t, len(vs), fmt_views(median([x["views"] or 0 for x in vs])),
            fmt_views(max(x["views"] or 0 for x in vs)), mt.get(t, 0)))

    # ---- 5. 非属人チャンネルの伸び方
    L.append("\n## 5. competitors: 1本だけ跳ねている構造\n")
    L.append("顔出しなしのチャンネルは「平均は数百回、たまに1本が10万回」という形になりやすい。"
             "その跳ねた1本が何だったかを見ると、狙うべき形が分かる。\n")
    spikes = [v for v in rivals if v["multiple"] and v["multiple"] >= 10
              and v["views"] and v["views"] >= 20000]
    spikes.sort(key=lambda v: -(v["multiple"] or 0))
    L.append("| ch中央値 | この1本 | 倍率 | タイトル |")
    L.append("|---:|---:|---:|---|")
    for v in spikes[:15]:
        L.append("| %s | %s | %.0fx | [%s](%s) |" % (
            fmt_views(v["channel_median"]), fmt_views(v["views"]), v["multiple"],
            v["title"].replace("|", "/")[:46], v["url"]))

    # ---- 6. 次に作るネタ
    L.append("\n## 6. 次に作るネタ（競合が当てていて自分が未着手）\n")
    for i, v in enumerate(analysis.opportunities(videos, self_titles)[:12], 1):
        L.append("%d. **%s**" % (i, v["title"]))
        L.append("   - %s / %s回 / そのチャンネル比 %sx / 未使用: %s" % (
            v["channel_title"], fmt_views(v["views"]), v["multiple"] or "-",
            " / ".join(v["fresh_words"])))
        L.append("   - %s" % v["url"])

    # ---- 7. 投稿頻度と登録者あたりの再生
    # 「毎日出すべきか」「登録者が増えれば再生も増えるか」を毎回その場のデータで確かめる
    L.append("\n## 7. 投稿頻度と登録者は、成績とどう関係しているか\n")
    per_ch = defaultdict(list)
    for v in videos:
        if v["published_at"]:
            per_ch[v["channel_id"]].append(v)
    stat = []
    for cid, vs in per_ch.items():
        if len(vs) < 8:
            continue
        ds = sorted(x["published_at"][:10] for x in vs if x["published_at"])
        span = max(1, (datetime.fromisoformat(ds[-1]) - datetime.fromisoformat(ds[0])).days)
        stat.append({
            "per_week": len(vs) * 7.0 / span,
            "med": median([x["views"] for x in vs if x["views"] is not None]),
            "subs": next((x["channel_subs"] for x in vs if x["channel_subs"]), 0) or 0,
            "title": vs[0]["channel_title"], "is_self": vs[0]["is_self"],
        })
    band = [("〜2本/週", 0, 2), ("2-4本/週", 2, 4), ("4-7本/週", 4, 7), ("7本〜/週", 7, 99)]
    L.append("| 投稿頻度 | ch数 | その帯の中央値 |")
    L.append("|---|---:|---:|")
    for lab, lo, hi in band:
        g = [x["med"] for x in stat if lo <= x["per_week"] < hi]
        if g:
            L.append("| %s | %d | %s |" % (lab, len(g), fmt_views(median(g))))
    L.append("\n頻度の帯で中央値が単調に増減していなければ、**投稿本数を変えても成績は動かない**。"
             "その場合に効くのはテーマと型（§3・§4）。\n")
    L.append("| 登録者に対する再生 | 登録者 | 中央値 | チャンネル |")
    L.append("|---:|---:|---:|---|")
    for x in sorted([x for x in stat if x["subs"] >= 1000],
                    key=lambda x: -(x["med"] / x["subs"])):
        L.append("| %.1f%% | %s | %s | %s%s |" % (
            100.0 * x["med"] / x["subs"], fmt_views(x["subs"]), fmt_views(x["med"]),
            x["title"][:24], " ←自分" if x["is_self"] else ""))
    L.append("\nこの比率が数%から数百%までばらつく限り、**登録者数はチャンネルの状態を表さない**ので追わない。")

    L.append("\n---")
    L.append("検索キーワード(config.json): %s" % " / ".join(cfg.get("keywords", [])))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("書き出しました: %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
