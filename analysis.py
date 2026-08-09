#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集めたデータの分析。research.py と server.py の両方から使う。

見たいのは「何が伸びたか」ではなく「いま何を作るべきか」なので、
  ・再生数そのものより 時速(VPH)と そのチャンネルの平均に対する倍率
  ・伸びたタイトルに共通する型
  ・競合が当てていて自分がまだ触っていないネタ
を出す。
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- 共通

def _dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return 0
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def fmt_views(n):
    if n is None:
        return "-"
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return "{:,}".format(int(n))


# ---------------------------------------------------------------- 素材読み込み

# 検索は思わぬ方向にドリフトする(「洗濯 裏技」で中国ドラマが出る等)。
# 追跡外チャンネルの動画は、タイトルがこのジャンルに触れているものだけ採用する。
NICHE_RE = re.compile(
    r"掃除|洗濯|排水|カビ|臭|汚れ|収納|片付|エアコン|冷蔵庫|洗濯機|扇風機|室外機|電子レンジ|"
    r"コンセント|給湯|トイレ|風呂|布団|ベランダ|網戸|窓|"
    r"ゴキブリ|蚊|ハチ|蜂|虫|ダニ|ネズミ|アリ|カメムシ|"
    r"節約|電気代|水道|ガス代|光熱費|100均|百均|ダイソー|セリア|"
    r"健康|睡眠|血圧|血糖|疲れ|老化|寿命|腸|自律神経|熱中症|"
    r"食べ|料理|野菜|肉|米|パン|冷凍|保存|調味|弁当|"
    r"裏技|裏ワザ|知らないと|知らなきゃ|やってはいけない|ダメ|逆効果|"
    r"だけで|するだけ|置くだけ|入れるだけ|得する|損|節|ライフハック|雑学|豆知識|生活の知恵")


_JA_RE = re.compile(r"[ぁ-んァ-ヴ]")

# 「裏技」等でジャンル判定をすり抜けてくる別ジャンル(ゲーム実況・中華ドラマ等)
EXCLUDE_TITLE_RE = re.compile(
    r"ロブロックス|Roblox|マイクラ|マインクラフト|フォートナイト|ゲーム実況|"
    r"実況プレイ|MULTISUB|一口气看完|短剧|第\d+季|【海外の反応】|切り抜き",
    re.I)


def is_niche_title(title):
    # 日本語圏向けチャンネルなので、かなを含まないタイトルは対象外
    t = title or ""
    if not _JA_RE.search(t) or EXCLUDE_TITLE_RE.search(t):
        return False
    return bool(NICHE_RE.search(t))


def load_videos(con, days=365, include_self=True):
    now = datetime.now(timezone.utc)
    chans = {r["channel_id"]: dict(r) for r in con.execute("SELECT * FROM channels")}
    all_rows = con.execute("SELECT * FROM videos").fetchall()

    # 対象を絞る。追跡中(自分＋競合)のチャンネルは全部、
    # それ以外は検索で拾った「ジャンルに触れているタイトル」だけ。
    rows = []
    for r in all_rows:
        ch = chans.get(r["channel_id"])
        if ch and ch.get("is_muted"):
            continue
        tracked = bool(ch and (ch.get("is_self") or ch.get("is_rival") or ch.get("is_favorite")))
        if tracked and ch.get("is_self"):
            rows.append(r)
        elif tracked and _JA_RE.search(r["title"] or "") \
                and not EXCLUDE_TITLE_RE.search(r["title"] or ""):
            rows.append(r)
        elif (not ch or not r["channel_id"]):
            # チャンネルを特定できない動画は倍率も出せないので使わない
            continue
        elif (r["found_by"] or "").startswith("search:") and is_niche_title(r["title"]):
            rows.append(r)

    # チャンネルごとの中央値(公開48時間以上のものだけ = 立ち上がり途中を除く)
    by_ch = {}
    for r in rows:
        pub = _dt(r["published_at"])
        if not pub or r["views"] is None:
            continue
        if (now - pub).total_seconds() >= 48 * 3600:
            by_ch.setdefault(r["channel_id"], []).append(r["views"])
    med = {cid: median(v) for cid, v in by_ch.items() if len(v) >= 3}

    # 直近スナップショット2点から実測の時速を出す
    vel = {}
    for vid, ts, views in con.execute(
            "SELECT video_id, ts, views FROM snapshots ORDER BY video_id, ts"):
        if views is None:
            continue
        pts = vel.setdefault(vid, [])
        if pts and views < pts[-1][1]:
            continue  # 丸め値の混入(実際の再生数は下がらない)
        pts.append((ts, views))

    out = []
    for r in rows:
        ch = chans.get(r["channel_id"], {})
        if not include_self and ch.get("is_self"):
            continue
        pub = _dt(r["published_at"])
        age_h = (now - pub).total_seconds() / 3600.0 if pub else None
        views = r["views"]
        vph = (views / max(age_h, 3.0)) if (views is not None and age_h) else None

        recent_vph = None
        pts = vel.get(r["video_id"], [])
        if len(pts) >= 2:
            (t1, v1), (t2, v2) = pts[0], pts[-1]
            # 直近1週間の中で最も離れた2点
            for i in range(len(pts) - 1, 0, -1):
                if _dt(pts[i][0]) and _dt(pts[0][0]):
                    break
            d1, d2 = _dt(t1), _dt(t2)
            if d1 and d2:
                hrs = (d2 - d1).total_seconds() / 3600.0
                if hrs >= 3 and v2 is not None and v1 is not None:
                    recent_vph = max(0.0, (v2 - v1) / hrs)

        m = med.get(r["channel_id"])
        multiple = (views / m) if (m and views) else None
        speed = recent_vph if recent_vph is not None else vph
        score = 0.0
        if speed:
            score = speed * min(3.0, max(0.5, multiple or 1.0))
            if age_h and age_h < 24:      # 出たばかりは過大評価されやすい
                score *= 0.7

        out.append({
            "video_id": r["video_id"],
            "channel_id": r["channel_id"],
            "channel_title": ch.get("title") or "(不明)",
            "channel_subs": ch.get("subs"),
            "is_self": int(bool(ch.get("is_self"))),
            "title": r["title"] or "",
            "published_at": r["published_at"],
            "published_is_estimate": r["published_is_estimate"],
            "age_hours": round(age_h, 1) if age_h else None,
            "age_days": round(age_h / 24.0, 1) if age_h else None,
            "duration_sec": r["duration_sec"],
            "views": views,
            "vph": round(vph, 1) if vph else None,
            "recent_vph": round(recent_vph, 1) if recent_vph is not None else None,
            "channel_median": int(m) if m else None,
            "multiple": round(multiple, 2) if multiple else None,
            "score": round(score, 1),
            "first_seen": r["first_seen"],
            "url": "https://www.youtube.com/watch?v=%s" % r["video_id"],
            # i.ytimg.com を直接読むとブラウザ側で遮断される環境があるので自前で中継する
            "thumb": "/api/thumb?size=mq&video_id=%s" % r["video_id"],
        })
    if days:
        cutoff = now - timedelta(days=days)
        out = [v for v in out if not v["published_at"] or (_dt(v["published_at"]) or now) >= cutoff]
    return out


# ---------------------------------------------------------------- タイトルの型

PATTERNS = [
    ("〜するだけで", r"だけで"),
    ("9割が/ほとんどの人", r"[0-9０-９]\s*割|ほとんどの人|多くの人"),
    ("知らないと損", r"知らな|損し|損する"),
    ("やってはいけない/NG", r"やってはいけない|やめ[てた]|NG|ダメ|逆効果|間違"),
    ("危険・警告", r"危険|警告|命|事故|火事|中毒|後悔"),
    ("〇選(リスト型)", r"[0-9０-９]+\s*選"),
    ("実は/本当は", r"実は|本当は|正体"),
    ("二度と/もう〜ない", r"二度と|もう[^ぁ-ん]{0,4}(出|来|悩|困)|いなくなり|出なくなる|消える"),
    ("100均・ダイソー", r"100均|百均|ダイソー|セリア|キャンドゥ"),
    ("プロ・専門家の話", r"プロ|専門家|医師|職人|メーカー|業者|農家"),
    ("数字で効果を提示", r"[0-9０-９]+\s*[%％℃度円倍分秒円]"),
    ("【】でジャンル明示", r"【.+?】"),
    ("今すぐ/今日から", r"今すぐ|今日から|明日から|今年"),
    ("放置・置くだけ", r"置くだけ|入れるだけ|貼るだけ|かけるだけ|混ぜるだけ|放置"),
    ("season(季節ワード)", r"夏|冬|春|秋|梅雨|真夏|猛暑|寒|台風|[0-9０-９]+月"),
    ("お金(節約・電気代)", r"節約|電気代|水道|ガス代|得|安く|無料|タダ|お金"),
    ("健康・体", r"健康|体|血|睡眠|疲れ|痛|老化|病気|寿命"),
    ("害虫・生き物", r"ゴキブリ|蚊|ハチ|蜂|虫|ダニ|カビ|ネズミ|アリ"),
    ("掃除・家事", r"掃除|洗濯|排水|臭|汚れ|片付|収納"),
    ("家電・住まい", r"エアコン|冷蔵庫|洗濯機|扇風機|室外機|給湯|コンセント|電子レンジ"),
    ("食べ物", r"食べ|料理|野菜|肉|米|パン|冷凍|保存|調味"),
    ("問いかけ/伏せ", r"[?？]|なぜ|どっち|どれ"),
]


def title_patterns(videos, min_n=3):
    res = []
    for name, pat in PATTERNS:
        rx = re.compile(pat)
        hit = [v for v in videos if rx.search(v["title"])]
        if len(hit) < min_n:
            continue
        vs = [v["views"] for v in hit if v["views"] is not None]
        vph = [v["vph"] for v in hit if v["vph"]]
        best = max(hit, key=lambda v: v.get("score") or 0)
        res.append({
            "name": name,
            "count": len(hit),
            "median_views": int(median(vs)),
            "median_vph": round(median(vph), 1),
            "best_title": best["title"],
            "best_url": best["url"],
            "best_views": best["views"],
        })
    base = median([r["median_views"] for r in res]) or 1
    for r in res:
        r["index"] = round(r["median_views"] / base, 2)   # 全体中央値=1.0
    res.sort(key=lambda r: r["median_views"], reverse=True)
    return res


BRACKET_RE = re.compile(r"[【\[]([^】\]]{1,12})[】\]]")


def bracket_words(videos, min_n=2):
    d = {}
    for v in videos:
        for w in BRACKET_RE.findall(v["title"]):
            e = d.setdefault(w.strip(), {"word": w.strip(), "count": 0, "views": []})
            e["count"] += 1
            if v["views"] is not None:
                e["views"].append(v["views"])
    out = [{"word": e["word"], "count": e["count"], "median_views": int(median(e["views"]))}
           for e in d.values() if e["count"] >= min_n]
    out.sort(key=lambda r: (r["count"], r["median_views"]), reverse=True)
    return out[:40]


# ---------------------------------------------------------------- ネタ(トピック)

STOP = set("""
ライフハック 雑学 動画 視聴 チャンネル 方法 理由 場合 自分 本当 意外 簡単 必見 完全 解説
紹介 最強 最新 実は 知識 生活 便利 効果 対策 注意 危険 情報 一覧 まとめ 徹底 驚愕 衝撃
これ それ あれ ため こと もの 人達 今回 以上 以下 全部 全て 大切 重要 有効 可能 不可能
おすすめ オススメ ポイント コツ テク テクニック プロ 世界 日本 令和 年版 大公開 公開
""".split())

TOKEN_RE = re.compile(r"[ァ-ヴー]{2,10}|[一-龥]{2,6}|[A-Za-z][A-Za-z0-9]{1,9}|[0-9]{2,4}均")


def tokenize(title):
    words = set()
    for w in TOKEN_RE.findall(title):
        w = w.strip("ー")
        if len(w) < 2 or w in STOP:
            continue
        words.add(w)
        # 「エアコン室外機」のような塊は前半3文字も拾っておく
        if len(w) >= 5 and re.match(r"^[一-龥]+$", w):
            for sub in (w[:3], w[-3:]):
                if sub not in STOP and len(sub) == 3:
                    words.add(sub)
    return words


def topics(videos, self_titles, min_n=2, limit=80):
    self_text = " ".join(self_titles)
    d = {}
    for v in videos:
        if v["is_self"]:
            continue
        for w in tokenize(v["title"]):
            e = d.setdefault(w, {"word": w, "count": 0, "views": [], "vph": [], "best": None})
            e["count"] += 1
            if v["views"] is not None:
                e["views"].append(v["views"])
            if v["vph"]:
                e["vph"].append(v["vph"])
            if e["best"] is None or (v.get("score") or 0) > (e["best"].get("score") or 0):
                e["best"] = v
    out = []
    for e in d.values():
        if e["count"] < min_n or not e["views"]:
            continue
        out.append({
            "word": e["word"],
            "count": e["count"],
            "median_views": int(median(e["views"])),
            "max_views": max(e["views"]),
            "median_vph": round(median(e["vph"]), 1),
            "self_used": e["word"] in self_text,
            "best_title": e["best"]["title"],
            "best_url": e["best"]["url"],
            "best_channel": e["best"]["channel_title"],
        })
    out.sort(key=lambda r: r["median_views"] * (1 + 0.15 * r["count"]), reverse=True)
    return out[:limit]


# ---------------------------------------------------------------- まとめ

def hot_videos(videos, days=45, limit=40, rivals_only=True):
    sel = []
    for v in videos:
        if rivals_only and v["is_self"]:
            continue
        if v["age_days"] is None or v["age_days"] > days:
            continue
        if v["duration_sec"] and v["duration_sec"] < 75:
            continue
        sel.append(v)
    sel.sort(key=lambda v: v["score"], reverse=True)
    return sel[:limit]


def opportunities(videos, self_titles, limit=25):
    """競合が当てていて、自分がまだタイトルに使っていないネタ。"""
    self_text = " ".join(self_titles)
    cands = []
    for v in hot_videos(videos, days=90, limit=400):
        words = [w for w in tokenize(v["title"]) if len(w) >= 2]
        fresh = [w for w in words if w not in self_text]
        if not fresh:
            continue
        if (v["multiple"] or 0) < 1.2 and (v["vph"] or 0) < 30:
            continue
        cands.append({**v, "fresh_words": sorted(fresh, key=len, reverse=True)[:6]})
    cands.sort(key=lambda v: v["score"], reverse=True)
    return cands[:limit]


# 批判・不満・改善要望のシグナル。台本づくりでは好評と同じくらい重要な情報
NEG_RE = re.compile(
    r"微妙|残念|嘘|ウソ|デマ|間違|違うと思|逆効果|信用できな|信じられな|怪しい|胡散|"
    r"わかりにく|分かりにく|聞き取りにく|聞きづら|読みにく|見にく|"
    r"長い|長すぎ|くどい|回りくど|前置き|結論(が|まで|を先)|まだるっこ|引っ張|"
    r"つまらな|飽き|退屈|眠く|"
    r"効果な(い|かった)|意味な(い|かった)|変わらな(い|かった)|治らな|直らな|"
    r"早口|音量|BGM|うるさ|声が|音が|AIっぽ|AI音声|機械音声|棒読み|合成音声|"
    r"パクリ|真似|既出|前に見た|同じ内容|使い回し|"
    r"常識|知ってた|当たり前|今さら|いまさら|"
    r"タイトル詐欺|サムネ詐欺|釣り|大げさ|大袈裟|誇張|時間の無駄|損した|"
    r"やめた方|やめとけ|おすすめしない|危な(い|かった)")


def summarize_comments(comments, top_n=15, max_len=150, neg_n=5):
    """LLMなしの抽出型要約。

    いいね順の上位(好評・共感)に加えて、批判・不満・改善要望のコメントを
    別枠で必ず拾う。少数でも台本の改善材料として価値が高いため。"""
    if not comments:
        return "(コメントが取得できませんでした)"

    def fmt(c):
        text = c["text"].replace("\r", "").replace("\n", " ").strip()
        if len(text) > max_len:
            text = text[:max_len] + "…"
        mark = "【投稿者】" if c.get("is_creator") else ""
        return "・(👍%d) %s%s" % (c.get("likes", 0), mark, text)

    negatives = [c for c in comments if NEG_RE.search(c["text"])]
    neg_ids = {id(c) for c in negatives}
    positives = [c for c in comments if id(c) not in neg_ids]

    lines = ["【反応が大きいコメント】"]
    lines += [fmt(c) for c in
              sorted(positives, key=lambda c: c.get("likes", 0), reverse=True)[:top_n]]
    lines.append("")
    lines.append("【批判・気になる点(改善のヒント)】")
    if negatives:
        lines += [fmt(c) for c in
                  sorted(negatives, key=lambda c: c.get("likes", 0), reverse=True)[:neg_n]]
    else:
        lines.append("・目立った批判コメントは見つかりませんでした")

    # 頻出ワード(コメント欄の話題の傾向)
    freq = {}
    for c in comments:
        for w in tokenize(c["text"]):
            freq[w] = freq.get(w, 0) + 1
    hot = sorted((w for w in freq if freq[w] >= 3), key=lambda w: -freq[w])[:10]
    if hot:
        lines.append("")
        lines.append("よく出る言葉: " + " / ".join("%s(%d)" % (w, freq[w]) for w in hot))
    return "\n".join(lines)


def channel_table(con, videos, limit=40):
    favs = {r["channel_id"]: r["is_favorite"] for r in
            con.execute("SELECT channel_id, is_favorite FROM channels")}
    stats = {}
    for v in videos:
        s = stats.setdefault(v["channel_id"], {
            "channel_id": v["channel_id"], "title": v["channel_title"],
            "subs": v["channel_subs"], "is_self": v["is_self"],
            "views": [], "recent": 0, "latest": None})
        if v["views"] is not None:
            s["views"].append(v["views"])
        if v["age_days"] is not None and v["age_days"] <= 30:
            s["recent"] += 1
        if v["published_at"] and (s["latest"] is None or v["published_at"] > s["latest"]):
            s["latest"] = v["published_at"]
    out = []
    for s in stats.values():
        if not s["views"]:
            continue
        out.append({
            "channel_id": s["channel_id"], "title": s["title"], "subs": s["subs"],
            "is_self": s["is_self"], "is_favorite": int(favs.get(s["channel_id"]) or 0),
            "videos": len(s["views"]),
            "median_views": int(median(s["views"])), "max_views": max(s["views"]),
            "posts_30d": s["recent"], "latest": s["latest"],
            "url": "https://www.youtube.com/channel/%s/videos" % s["channel_id"],
        })
    out.sort(key=lambda r: r["median_views"], reverse=True)
    return out[:limit]


def self_summary(videos):
    mine = [v for v in videos if v["is_self"]]
    mine.sort(key=lambda v: v["published_at"] or "", reverse=True)
    vs = [v["views"] for v in mine if v["views"] is not None]
    rivals = [v for v in videos if not v["is_self"] and v["views"] is not None
              and v["age_days"] is not None and v["age_days"] <= 90]
    return {
        "count": len(mine),
        "median_views": int(median(vs)),
        "best": max(mine, key=lambda v: v["views"] or 0) if mine else None,
        "worst": min([v for v in mine if v["views"] is not None],
                     key=lambda v: v["views"]) if vs else None,
        "latest": mine[:12],
        "rival_median_90d": int(median([v["views"] for v in rivals])),
    }


def match_patterns(title):
    """このタイトルが当てはまる型の一覧。"""
    return [name for name, pat in PATTERNS if re.search(pat, title or "")]


def video_detail(con, video_id):
    """1本の動画の分析: 伸び推移・当てはまる型・似た動画。"""
    videos = load_videos(con)
    me = next((v for v in videos if v["video_id"] == video_id), None)
    if me is None:
        # 追跡対象外(検索タブなどから来た動画)でも分析できるようにする
        row = con.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
        if row is None:
            return None
        ch = con.execute("SELECT title FROM channels WHERE channel_id=?",
                         (row["channel_id"],)).fetchone()
        pub = _dt(row["published_at"])
        age_h = (datetime.now(timezone.utc) - pub).total_seconds() / 3600.0 if pub else None
        me = {"video_id": video_id, "title": row["title"] or "",
              "channel_title": (ch["title"] if ch else None) or "",
              "views": row["views"], "is_self": 0,
              "age_days": round(age_h / 24.0, 1) if age_h else None,
              "duration_sec": row["duration_sec"],
              "vph": round(row["views"] / max(age_h, 3.0), 1) if (row["views"] and age_h) else None,
              "url": "https://www.youtube.com/watch?v=%s" % video_id,
              "thumb": "/api/thumb?size=mq&video_id=%s" % video_id}
    # 再生数は実際には単調増加。チャンネルページの「20万回」のような丸め値が
    # RSS の正確な値と混ざってギザギザになるので、下がって見える点は捨てる。
    snaps, peak = [], -1
    for r in con.execute(
            "SELECT ts, views FROM snapshots WHERE video_id=? ORDER BY ts", (video_id,)):
        if r["views"] is None or r["views"] < peak:
            continue
        peak = r["views"]
        snaps.append({"ts": r["ts"], "views": r["views"]})
    toks = tokenize(me.get("title", ""))
    similar = []
    for v in videos:
        if v["video_id"] == video_id:
            continue
        shared = toks & tokenize(v["title"])
        if shared:
            similar.append({**v, "shared": sorted(shared, key=len, reverse=True)[:4],
                            "shared_n": len(shared)})
    similar.sort(key=lambda v: (v["shared_n"], v["views"] or 0), reverse=True)
    tr = con.execute("SELECT lang, kind, fetched_at FROM transcripts WHERE video_id=?",
                     (video_id,)).fetchone()
    return {
        "video": me,
        "snapshots": snaps,
        "patterns": match_patterns(me.get("title", "")),
        "similar": similar[:12],
        "has_transcript": bool(tr),
        "transcript_kind": tr["kind"] if tr else None,
    }


def new_from_favorites(con, videos, days=21):
    """お気に入りチャンネルの新着(投稿が新しい順)。"""
    favs = {r["channel_id"] for r in con.execute(
        "SELECT channel_id FROM channels WHERE is_favorite=1")}
    if not favs:
        return []
    out = [v for v in videos if v["channel_id"] in favs
           and v["age_days"] is not None and v["age_days"] <= days]
    out.sort(key=lambda v: v["published_at"] or "", reverse=True)
    return out[:60]


def build_all(con):
    videos = load_videos(con)
    self_titles = [v["title"] for v in videos if v["is_self"]]
    rivals = [v for v in videos if not v["is_self"]]
    return {
        "new_videos": new_from_favorites(con, videos),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_count": len(videos),
        "hot": hot_videos(videos, days=90, limit=300),
        "opportunities": opportunities(videos, self_titles),
        "patterns": title_patterns(rivals + [v for v in videos if v["is_self"]]),
        "brackets": bracket_words(videos),
        "topics": topics(videos, self_titles),
        "channels": channel_table(con, videos),
        "self": self_summary(videos),
    }


# ---------------------------------------------------------------- レポート

def write_report(con, base_dir):
    d = build_all(con)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("# ライフハック雑学 リサーチ (%s 時点)\n" % now)
    s = d["self"]
    L.append("## 自チャンネルの現在地\n")
    L.append("- 記録している自分の動画: %d本 / 中央値 %s回" % (s["count"], fmt_views(s["median_views"])))
    L.append("- 同ジャンル(直近90日)の中央値: %s回" % fmt_views(s["rival_median_90d"]))
    if s["best"]:
        L.append("- 自分のベスト: %s回 「%s」" % (fmt_views(s["best"]["views"]), s["best"]["title"]))
    if s["worst"]:
        L.append("- 自分のワースト: %s回 「%s」" % (fmt_views(s["worst"]["views"]), s["worst"]["title"]))

    L.append("\n## いま作るべきネタ(競合が当てていて自分が未着手)\n")
    for i, v in enumerate(d["opportunities"][:12], 1):
        L.append("%d. **%s**" % (i, v["title"]))
        L.append("   - %s / %s回 / %.1f日経過 / そのチャンネル比 %sx / 時速%s" % (
            v["channel_title"], fmt_views(v["views"]), v["age_days"] or 0,
            v["multiple"] or "-", v["recent_vph"] or v["vph"] or "-"))
        L.append("   - 未使用キーワード: %s" % " / ".join(v["fresh_words"]))
        L.append("   - %s" % v["url"])

    L.append("\n## 直近で伸びている競合動画 TOP20\n")
    L.append("| 再生 | 経過 | 倍率 | タイトル | チャンネル |")
    L.append("|---:|---:|---:|---|---|")
    for v in d["hot"][:20]:
        L.append("| %s | %.1f日 | %s | [%s](%s) | %s |" % (
            fmt_views(v["views"]), v["age_days"] or 0, v["multiple"] or "-",
            v["title"].replace("|", "/"), v["url"], v["channel_title"]))

    L.append("\n## 効いているタイトルの型\n")
    L.append("| 型 | 本数 | 中央値 | 全体比 | 代表例 |")
    L.append("|---|---:|---:|---:|---|")
    for p in d["patterns"][:14]:
        L.append("| %s | %d | %s | %.2f | %s |" % (
            p["name"], p["count"], fmt_views(p["median_views"]), p["index"],
            p["best_title"][:34].replace("|", "/")))

    L.append("\n## 伸びているキーワード(自分が未使用のものに ★)\n")
    for t in d["topics"][:30]:
        mark = "" if t["self_used"] else " ★"
        L.append("- **%s**%s — %d本 / 中央値 %s回 / 最高 %s回 — 例: %s" % (
            t["word"], mark, t["count"], fmt_views(t["median_views"]),
            fmt_views(t["max_views"]), t["best_title"][:40]))

    path = os.path.join(base_dir, "ネタ候補.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(base_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    return path
