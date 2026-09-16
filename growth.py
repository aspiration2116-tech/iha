#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
growth.py — 直近3ヶ月に伸びている「国内・非属人」チャンネルを research.db から抽出する。

research.db のスナップショットは時間差が小さく実測の時速(VPH)が出せないため、
1時点のデータだけで成長を判定できる指標に絞っている。

  伸びトレンド … log10(再生数) を「公開の新しさ」に対して回帰した傾きを、30日あたりの
                 倍率にしたもの。1.0超で伸び、1.0未満で失速。単発のバズ動画に
                 引きずられないよう、全ペアの傾きの中央値をとる (Theil-Sen)。
  直近/成熟比 … 14-35日の中央値再生 ÷ 36-90日の中央値再生。トレンドの読みやすい版。

  いずれも公開後14日未満の動画は除外する。再生数が溜まりきっておらず、
  「新しいから低い」だけの動画を「失速」と誤判定するため (MATURE_DAYS 参照)。
  登録者比   … 期間中央値再生 ÷ 登録者数。3xを超えると非登録者への露出が主 = 拡散中。
                 ただし登録者数が取れていない/誤取得のチャンネルがあるため補助指標。

使い方:
  python3 growth.py                        # 直近90日で集計して一覧表示
  python3 growth.py --days 60
  python3 growth.py --md 伸びているチャンネル.md --json growth.json
"""
import argparse, json, math, os, re, signal, sqlite3, statistics
from datetime import datetime, timedelta

try:                      # head や less に渡したときに BrokenPipe で落ちないように
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
SHORT_SEC = 75          # これ未満はショートとして除外
MIN_VIDEOS = 5          # 期間内の本数がこれ未満のチャンネルは判定しない
# 再生数が頭打ちになるまでの日数。このDBの実測では 0-3日=0.36 / 3-7日=0.80 /
# 7-14日=1.00 / 以降14-120日は1.0-1.4でほぼ横ばい (チャンネル中央値比)。
# 公開直後の動画は「まだ伸びていない」だけなので、比較から外す。
MATURE_DAYS = 14
MIN_MATURE = 8          # トレンドを出すのに必要な成熟動画の本数
MIN_SPAN = 30           # トレンドを出すのに必要な成熟動画の期間(日)

# ── 属人性の判定 ────────────────────────────────────────────────
# 非属人 = 特定の人物の存在が集客の核になっていないチャンネル
#          (合成音声ナレーション / ゆっくり・ずんだもん / 文字＋素材 / 企業運営 など)
NONPERSONAL_WORDS = (r"雑学|ライフハック|豆知識|知恵|裏ワザ|裏技|知らな|損する|得する|"
                     r"ゆっくり|ずんだもん|解説|給付金|補助金|物語|ストーリー|怪異|昔話|朗読|聞き流し")
PERSONAL_WORDS = r"チャンネル$|さん|ちゃんねる$|ルーティン|vlog|Vlog|VLOG"
# 自動判定より優先する人手の確定値
OVERRIDE = {
    "ずんだもんとまなぼう": "非属人", "えだまめストーリー": "非属人",
    "歴史怪異館": "非属人", "カップ麺を待つ間に見たい雑学": "非属人",
    "みんなの給付金・補助金ちゃんねる": "非属人", "暮らし上手ノート": "非属人",
    "ぽかぽか長寿ライフ": "非属人", "農家直伝！家庭菜園らいふ": "非属人",
    "孤独のシニアまち子の暮らし": "非属人",   # 顔出しなし・合成音声の創作人格
    "杏と猫の小さな暮らし": "非属人", "心に灯る言葉": "非属人",
    "くらしのマーケット大学": "非属人",       # 企業(くらしのマーケット)運営
    "楽待 RAKUMACHI": "非属人",              # 企業(楽待)運営
    "ミニマリストしぶ": "属人", "カズチャンネル/Kazu Channel": "属人",
    "節約お姉さんういうい": "属人", "みずおじさん / 誰でも分かるスマホ講座": "属人",
    "みやじぃ iPhone / ショートカット": "属人", "サトシの趣味部屋": "属人",
    "寿チャンネルDIY in沖縄": "属人", "野口智也チャンネル": "属人",
    "DIYをめぐる冒険": "属人", "森の家 / Mori's house": "属人",
    "きのっこ / Kinocco": "属人", "まんまるなライフ": "属人", "My-Room": "属人",
    "おもちのゆる節約とミニマリスト。": "属人", "気軽にハンドメイド生活": "属人",
    "スマトク": "属人",
    # 100均レビューは「手元＋声」で演者ブランドが効くため準属人
    "ちまき / 100均紹介": "準属人", "とも【100均紹介】": "準属人",
    "ヨッパン・100均紹介": "準属人", "おもち100均マニア": "準属人",
    "しずく / 100均といい暮らし紹介": "準属人", "はるチャンネル【100均】": "準属人",
}
OUT_OF_SCOPE = r"ニュース|news|NEWS|ANN|FNN|TBS|メ〜テレ|海外の反応|短剧|海外不動産"

# ── 国内 / 海外運営の判定 ──────────────────────────────────────
JP = re.compile(r"[ぁ-んァ-ヶ一-龠]")
FOREIGN_HANDLE = re.compile(r"^@[a-z]{6,}\d{3,}$", re.I)   # 海外の量産アカウントで頻出
MT_MARKERS = ["なぜ私たちは", "でしょうか？", "のでしょう", "あなたの見方",
              "完全に変える", "初公開", "秘訣から", "彼女の庭", "隣人に教わった",
              "空海の教え", "――"]


def classify_person(title):
    t = (title or "").replace("&#39;", "'")
    if t in OVERRIDE:
        return OVERRIDE[t]
    if re.search(NONPERSONAL_WORDS, t):
        return "非属人"
    if re.search(PERSONAL_WORDS, t):
        return "属人"
    return "不明"


def foreign_score(ch_title, handle, titles):
    """海外運営の疑いスコアと、その根拠。"""
    score, why = 0, []
    if handle and FOREIGN_HANDLE.match(handle):
        score += 2; why.append("ハンドルがローマ字人名＋数字")
    if not JP.search(ch_title or ""):
        score += 1; why.append("チャンネル名が非日本語")
    n_en = sum(1 for t in titles if not JP.search(t or ""))
    if titles and n_en / len(titles) >= 0.3:
        score += 2; why.append("英語タイトルが%d/%d本" % (n_en, len(titles)))
    n_mt = sum(1 for t in titles if any(m in (t or "") for m in MT_MARKERS))
    if titles and n_mt / len(titles) >= 0.25:
        score += 2; why.append("機械翻訳調が%d/%d本" % (n_mt, len(titles)))
    return score, why


# ── 指標 ────────────────────────────────────────────────────────
def med(xs):
    return statistics.median(xs) if xs else 0


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def trend_per_30d(points):
    """[(age_days, views)] → 30日あたりの再生数の伸び倍率。

    log10(views) を「新しさ(-age)」に対して回帰する。ライフハック系は月に1〜2本
    だけ跳ねる動画が出るため、最小二乗だとその1本で傾きが決まってしまう。
    全ペアの傾きの中央値(Theil-Sen)をとって外れ値の影響を落とす。
    成熟した動画(MATURE_DAYS 以上経過)だけを使う。"""
    pts = [(-a, math.log10(v + 1)) for a, v in points if v and v > 0]
    if len(pts) < MIN_MATURE:
        return None
    if max(p[0] for p in pts) - min(p[0] for p in pts) < MIN_SPAN:
        return None
    slopes = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dx = pts[j][0] - pts[i][0]
            if abs(dx) > 1e-9:
                slopes.append((pts[j][1] - pts[i][1]) / dx)
    if not slopes:
        return None
    return round(10 ** (statistics.median(slopes) * 30), 2)


def analyze(con, days=90):
    con.row_factory = sqlite3.Row
    # 基準日 = 収集済み動画の最新公開日 (DBが古くても指標がずれないように)
    asof = parse_dt(con.execute(
        "SELECT MAX(published_at) FROM videos WHERE published_at IS NOT NULL").fetchone()[0])
    since = asof - timedelta(days=days)

    out = []
    for ch in con.execute("SELECT * FROM channels").fetchall():
        title = (ch["title"] or "").replace("&#39;", "'")
        if ch["is_muted"] or re.search(OUT_OF_SCOPE, title):
            continue
        rows = []
        for v in con.execute(
                "SELECT title, views, published_at, duration_sec, published_is_estimate "
                "FROM videos WHERE channel_id=? AND published_at IS NOT NULL",
                (ch["channel_id"],)).fetchall():
            if v["duration_sec"] is not None and v["duration_sec"] < SHORT_SEC:
                continue
            d = parse_dt(v["published_at"])
            if not d or v["views"] is None:
                continue
            rows.append({"title": v["title"], "views": v["views"],
                         "age": (asof - d).total_seconds() / 86400.0,
                         "est": v["published_is_estimate"]})
        win = [r for r in rows if r["age"] <= days]
        if len(win) < MIN_VIDEOS:
            continue

        # 伸びの判定は成熟動画(14日以上経過)のみで行う
        mat = [r for r in win if r["age"] >= MATURE_DAYS]
        views = [r["views"] for r in mat]
        m = med(views)
        if not views:
            continue
        recent = [r["views"] for r in mat if r["age"] <= 35]
        older = [r["views"] for r in mat if 36 <= r["age"] <= days]
        ratio = (round(med(recent) / med(older), 2)
                 if len(recent) >= 3 and len(older) >= 3 and med(older) > 0 else None)
        subs = ch["subs"] or 0
        mx = max(views)
        # 登録者が極端に少ないのに数百万再生 = 広告出稿か登録者の誤取得
        suspect = bool(subs and mx > 1_000_000 and mx > 20 * m)
        fs, why = foreign_score(title, ch["handle"], [r["title"] for r in win])
        out.append({
            "channel": title, "handle": ch["handle"], "subs": subs,
            "person": classify_person(title),
            "n": len(win), "n_mature": len(mat),
            # 成熟動画で実際にカバーできている期間 (短いほど判定が弱い)
            "span_days": round(max(r["age"] for r in mat) - min(r["age"] for r in mat)),
            "median_views": int(m), "max_views": mx,
            # 中央値の何倍のヒットがあるか。大きいほど「単発頼み」
            "hit_ratio": round(mx / m, 1) if m else None,
            "trend_30d": trend_per_30d([(r["age"], r["views"]) for r in mat]),
            "recent_vs_mature": ratio,
            "subs_ratio": round(m / subs, 2) if subs and not suspect else None,
            "subs_suspect": suspect,
            "post_per_week": round(len(win) / (max(max(r["age"] for r in win), 7) / 7.0), 1),
            "est_ratio": round(sum(1 for r in win if r["est"]) / len(win), 2),
            "foreign_score": fs, "foreign_why": why,
            "top": sorted(mat, key=lambda r: -r["views"])[0],
            # 判定に足るデータがあるか
            "judged": trend_per_30d([(r["age"], r["views"]) for r in mat]) is not None,
        })
    return asof, since, out


def score(r):
    """伸び順のスコア。トレンドを主、登録者比を従とする。"""
    s = 0.0
    if r["trend_30d"]:
        s += min(r["trend_30d"], 6) * 3
    if r["recent_vs_mature"]:
        s += min(r["recent_vs_mature"], 6) * 2
    if r["subs_ratio"]:
        s += min(r["subs_ratio"], 10)
    s += min(r["median_views"] / 20000.0, 5)
    return s


def build(days=90):
    con = sqlite3.connect(os.path.join(BASE, "research.db"))
    asof, since, rows = analyze(con, days)
    rows.sort(key=score, reverse=True)
    dom = [r for r in rows if r["person"] == "非属人" and r["foreign_score"] < 2]
    fore = [r for r in rows if r["person"] == "非属人" and r["foreign_score"] >= 2]
    return asof, since, rows, dom, fore


def fmt(x, dash="-"):
    return dash if x is None else x


def tier(r):
    """伸びの区分。判定材料が足りないものは分けて置く。"""
    if not r["judged"]:
        return "要観測"
    if (r["trend_30d"] or 0) >= 1.2 or (r["subs_ratio"] or 0) >= 3:
        return "伸長"
    if (r["trend_30d"] or 0) >= 0.8:
        return "横ばい"
    return "失速"


def write_md(path, asof, since, days, rows, dom, fore):
    L = []
    A = L.append
    A("# 直近%dヶ月で伸びている国内・非属人チャンネル" % round(days / 30))
    A("")
    A("`growth.py` が `research.db` から自動生成。再生成は `python3 growth.py --md %s`。"
      % os.path.basename(path))
    A("")
    A("- 基準日: **%s**（収集データ内で最も新しい動画の公開日）" % asof.strftime("%Y-%m-%d"))
    A("- 対象期間: %s 〜 %s" % (since.strftime("%Y-%m-%d"), asof.strftime("%Y-%m-%d")))
    A("- 母集団: research.db の追跡チャンネル。ニュース・切り抜き・ミュート済みは除外")
    lag = (datetime.now() - asof.replace(tzinfo=None)).days
    if lag > 7:
        A("- **データの鮮度**: 最終収集から %d 日経過している。"
          "最新の状況を見るには `python3 research.py --deep` で収集し直すこと。" % lag)
    A("- 判定対象 %d ch → 国内・非属人 **%d ch** / 海外運営の疑い %d ch" % (len(rows), len(dom), len(fore)))
    A("")
    A("## 読み方")
    A("")
    A("| 指標 | 意味 |")
    A("|---|---|")
    A("| 伸び | log10(再生数) を公開の新しさに回帰した傾きを30日あたりの倍率にしたもの。1.0超で伸長、1.0未満で失速 |")
    A("| 直近/成熟 | 14〜35日前の中央値再生 ÷ 36〜90日前の中央値再生 |")
    A("| 登録者比 | 期間中央値再生 ÷ 登録者数。3xを超えると非登録者への露出が主 = 拡散中 |")
    A("| 本数/日数 | 判定に使った成熟動画の本数と、それが覆う期間 |")
    A("| ヒット依存 | 最高再生 ÷ 中央値。10xを超えると常時の底上げではなく単発のバズ頼み |")
    A("")
    A("公開後 **%d日未満の動画は全指標から除外**している。このDBの実測で、"
      "チャンネル中央値に対する再生比は 0-3日=0.36 / 3-7日=0.80 / 7-14日=1.00 で、"
      "14日以降120日まで横ばい。新しいだけの動画を「失速」と読み違えないため。" % MATURE_DAYS)
    A("")

    for name, note in (("伸長", "伸びが1.2倍以上、または登録者比3x以上"),
                       ("横ばい", "伸びが0.8〜1.2倍"),
                       ("失速", "伸びが0.8倍未満")):
        grp = [r for r in dom if tier(r) == name]
        if not grp:
            continue
        A("## %s（%s）" % (name, note))
        A("")
        A("| チャンネル | 登録者 | 本数/日数 | 中央値 | 伸び | 直近/成熟 | 登録者比 | 最高再生 | ヒット依存 |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in grp:
            A("| %s | %s | %d本/%d日 | %s | %s | %s | %s | %s | %s |" % (
                r["channel"], "{:,}".format(r["subs"]) if r["subs"] else "-",
                r["n_mature"], r["span_days"], "{:,}".format(r["median_views"]),
                fmt(r["trend_30d"]), fmt(r["recent_vs_mature"]), fmt(r["subs_ratio"]),
                "{:,}".format(r["max_views"]),
                ("%sx" % r["hit_ratio"]) if r["hit_ratio"] else "-"))
        A("")
        for r in grp:
            A("- **%s** — 最高再生: 「%s」%s回" % (
                r["channel"], r["top"]["title"][:56], "{:,}".format(r["top"]["views"])))
        A("")

    watch = [r for r in dom if tier(r) == "要観測"]
    if watch:
        A("## 要観測（データ不足で3ヶ月の伸びを判定できない）")
        A("")
        A("RSSは直近15本しか返さないため、毎日投稿のチャンネルは2〜3週間分しか履歴がない。"
          "`python3 research.py --deep` を何回か回してスナップショットを貯めると判定できるようになる。")
        A("")
        A("| チャンネル | 登録者 | 成熟本数/日数 | 中央値 | 週あたり投稿 |")
        A("|---|---:|---:|---:|---:|")
        for r in sorted(watch, key=lambda x: -x["median_views"]):
            A("| %s | %s | %d本/%d日 | %s | %s |" % (
                r["channel"], "{:,}".format(r["subs"]) if r["subs"] else "-",
                r["n_mature"], r["span_days"], "{:,}".format(r["median_views"]),
                r["post_per_week"]))
        A("")

    if fore:
        A("## 海外運営の疑い（「国内」から除外）")
        A("")
        A("日本語のライフハック・雑学ジャンルには、海外から量産されている"
          "日本語チャンネルが混ざる。判定根拠つきで分離している。")
        A("")
        A("| チャンネル | ハンドル | 根拠 | 中央値 |")
        A("|---|---|---|---:|")
        for r in fore:
            A("| %s | %s | %s | %s |" % (
                r["channel"], r["handle"] or "-", " / ".join(r["foreign_why"]),
                "{:,}".format(r["median_views"])))
        A("")

    A("## この集計の限界")
    A("")
    A("- 母集団は config.json の検索キーワード（ライフハック・雑学・暮らし・節約系）で"
      "見つかったチャンネルに限られる。YouTube全体のランキングではない。")
    A("- `research.db` のスナップショットは時間差が最大2時間しかなく、実測の時速(VPH)は出せない。"
      "そのため累積再生数ベースの指標で代用している。")
    A("- 登録者数はチャンネルページから取得しており、未取得(-)や誤取得がある。"
      "登録者に対して極端な再生数を持つものは広告出稿の疑いとして登録者比を伏せている。")
    A("- 公開日の %d%% は「3週間前」等の相対表記からの推定値。" %
      round(100 * sum(r["est_ratio"] * r["n"] for r in rows) / max(sum(r["n"] for r in rows), 1)))
    A("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None, help="Markdownレポートの出力先")
    a = ap.parse_args()
    asof, since, rows, dom, fore = build(a.days)

    print("基準日(収集データ内の最新公開日): %s / 対象: %s〜" % (asof.strftime("%Y-%m-%d"),
                                                               since.strftime("%Y-%m-%d")))
    print("判定対象 %d ch → 国内・非属人 %d ch / 海外運営の疑い %d ch\n" % (len(rows), len(dom), len(fore)))
    hdr = "%-34s %8s %4s %5s %9s %7s %8s %8s %6s" % (
        "チャンネル", "登録者", "本数", "日数", "中央値", "伸び", "直近/成熟", "登録者比", "ヒット")
    judged = [r for r in dom if r["judged"]]
    short = [r for r in dom if not r["judged"]]
    print(hdr); print("-" * 92)
    for r in judged:
        print("%-34s %8s %4d %5d %9s %7s %8s %8s %6s" % (
            r["channel"][:32], ("{:,}".format(r["subs"]) if r["subs"] else "-"),
            r["n_mature"], r["span_days"], "{:,}".format(r["median_views"]),
            fmt(r["trend_30d"]), fmt(r["recent_vs_mature"]), fmt(r["subs_ratio"]),
            ("%sx" % r["hit_ratio"]) if r["hit_ratio"] else "-"))
    if short:
        print("\n[データ不足 — 成熟動画が%d本未満か期間%d日未満で伸びを判定できない]" % (MIN_MATURE, MIN_SPAN))
        for r in short:
            print("  %-32s 成熟%2d本/%2d日  中央値 %s" % (
                r["channel"][:30], r["n_mature"], r["span_days"],
                "{:,}".format(r["median_views"])))
    if fore:
        print("\n[海外運営の疑い — 「国内」から除外]")
        for r in fore:
            print("  %-30s %-24s %s" % (r["channel"][:28], r["handle"] or "-",
                                        " / ".join(r["foreign_why"])))
    if a.json:
        with open(os.path.join(BASE, a.json), "w", encoding="utf-8") as f:
            json.dump({"asof": asof.isoformat(), "days": a.days, "rows": rows},
                      f, ensure_ascii=False, indent=2, default=str)
    if a.md:
        path = os.path.join(BASE, a.md)
        write_md(path, asof, since, a.days, rows, dom, fore)
        print("\n→ %s" % path)


if __name__ == "__main__":
    main()
