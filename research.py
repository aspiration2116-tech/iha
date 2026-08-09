#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ライフハック雑学チャンネル リサーチ収集器

やること
  1. 自チャンネルと競合チャンネルの動画を集める(RSS + チャンネルページ)
  2. キーワード検索で「今伸びている新ネタ」と「新しい競合」を発見する
  3. 再生数を毎回スナップショットして、実測の伸び(時速)を出す
  4. 分析結果を ネタ候補.md に書き出す

使い方
  python3 research.py              # 通常の収集
  python3 research.py --quick      # 検索だけ(速い)
  python3 research.py --deep       # 競合チャンネルを全部ページ取得
  python3 research.py --add @xxxxx # 競合を手動追加
"""

import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime, timezone

import ytfetch

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "research.db")
CONFIG_PATH = os.path.join(BASE, "config.json")
LOG_PATH = os.path.join(BASE, "research.log")

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  channel_id   TEXT PRIMARY KEY,
  handle       TEXT,
  title        TEXT,
  subs         INTEGER,
  is_self      INTEGER DEFAULT 0,
  is_rival     INTEGER DEFAULT 0,
  is_muted     INTEGER DEFAULT 0,
  first_seen   TEXT,
  last_checked TEXT
);
CREATE TABLE IF NOT EXISTS videos (
  video_id     TEXT PRIMARY KEY,
  channel_id   TEXT,
  title        TEXT,
  published_at TEXT,
  published_is_estimate INTEGER DEFAULT 0,
  duration_sec INTEGER,
  views        INTEGER,
  first_seen   TEXT,
  last_seen    TEXT,
  found_by     TEXT
);
CREATE INDEX IF NOT EXISTS idx_videos_ch ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_pub ON videos(published_at);
CREATE TABLE IF NOT EXISTS snapshots (
  video_id TEXT, ts TEXT, views INTEGER,
  PRIMARY KEY (video_id, ts)
);
CREATE TABLE IF NOT EXISTS runs (
  ts TEXT PRIMARY KEY, ok INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS transcripts (
  video_id   TEXT PRIMARY KEY,
  lang       TEXT,
  kind       TEXT,
  text       TEXT,
  description TEXT,
  fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
  video_id   TEXT PRIMARY KEY,
  json       TEXT,
  summary    TEXT,
  fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS memos (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT DEFAULT '',
  body       TEXT DEFAULT '',
  video_id   TEXT,
  created_at TEXT,
  updated_at TEXT
);
"""

MIGRATIONS = [
    "ALTER TABLE channels ADD COLUMN is_favorite INTEGER DEFAULT 0",
]

DEFAULT_CONFIG = {
    "self_channels": ["@tomorrow_life_hack"],
    "rival_channels": [],
    "keywords": [
        "ライフハック 雑学", "知らないと損 生活", "生活の知恵 裏技",
        "掃除 裏技", "節約 術 電気代", "健康 雑学 医師",
        "害虫 対策 家", "暑さ対策 エアコン", "100均 便利 グッズ",
        "洗濯 やってはいけない", "食べ物 危険 組み合わせ", "スマホ 設定 裏技"
    ],
    "search_periods": ["today", "week", "month"],
    "auto_discover": True,
    "max_rivals": 45,
    "discover_min_views": 2000,
    "exclude_channel_words": [
        "ニュース", "news", "報道", "テレビ", "TBS", "ANN", "FNN", "NHK",
        "海外の反応", "切り抜き", "短剧", "不動産", "宝くじ", "競馬", "予想"
    ],
    "exclude_shorts": True,
    "request_interval_sec": 1.6,
    "deep_scan_top_n": 18,
    "notify_new_favorites": True,
    "port": 8770
}


def notify_mac(title, message):
    """macOS の通知センターに出す。"""
    import subprocess
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "%s" with title "%s" sound name "Glass"' % (
                 message.replace('"', "'")[:180], title.replace('"', "'"))],
            timeout=10, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def notify_new_favorite_videos(con, cfg, since_iso):
    """お気に入りチャンネルの新着(この収集で初めて見た動画)を通知する。"""
    if not cfg.get("notify_new_favorites"):
        return
    rows = con.execute("""
        SELECT v.title, c.title AS ch FROM videos v
        JOIN channels c ON c.channel_id = v.channel_id
        WHERE c.is_favorite=1 AND v.first_seen >= ?
        ORDER BY v.published_at DESC LIMIT 6""", (since_iso,)).fetchall()
    if not rows:
        return
    for r in rows[:3]:
        notify_mac("★ %s の新着" % r["ch"], r["title"])
    if len(rows) > 3:
        notify_mac("YouTubeリサーチ", "ほか%d本の新着があります" % (len(rows) - 3))
    log("お気に入り新着 %d本を通知" % len(rows))


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for mig in MIGRATIONS:
        try:
            con.execute(mig)
        except sqlite3.OperationalError:
            pass  # 適用済み
    return con


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- 保存

def upsert_channel(con, ch, **flags):
    ts = now_iso()
    row = con.execute("SELECT channel_id FROM channels WHERE channel_id=?",
                      (ch["channel_id"],)).fetchone()
    if row is None:
        con.execute(
            "INSERT INTO channels(channel_id,handle,title,subs,is_self,is_rival,first_seen,last_checked)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (ch["channel_id"], ch.get("handle"), ch.get("title"), ch.get("subs"),
             int(flags.get("is_self", 0)), int(flags.get("is_rival", 0)), ts, ts))
    else:
        sets, vals = [], []
        for col in ("handle", "title", "subs"):
            if ch.get(col) is not None:
                sets.append("%s=?" % col)
                vals.append(ch[col])
        for col in ("is_self", "is_rival"):
            if col in flags:
                sets.append("%s=MAX(%s,?)" % (col, col))
                vals.append(int(flags[col]))
        sets.append("last_checked=?")
        vals.append(ts)
        vals.append(ch["channel_id"])
        con.execute("UPDATE channels SET %s WHERE channel_id=?" % ",".join(sets), vals)


def upsert_video(con, v, found_by=""):
    ts = now_iso()
    old = con.execute("SELECT * FROM videos WHERE video_id=?", (v["video_id"],)).fetchone()
    if old is None:
        con.execute(
            "INSERT INTO videos(video_id,channel_id,title,published_at,published_is_estimate,"
            "duration_sec,views,first_seen,last_seen,found_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (v["video_id"], v.get("channel_id"), v.get("title"), v.get("published_at"),
             int(v.get("published_is_estimate", 0)), v.get("duration_sec"), v.get("views"),
             ts, ts, found_by or v.get("source", "")))
    else:
        sets, vals = ["last_seen=?"], [ts]
        if v.get("views") is not None:
            sets.append("views=?")
            vals.append(v["views"])
        if v.get("duration_sec"):
            sets.append("duration_sec=?")
            vals.append(v["duration_sec"])
        if v.get("channel_id") and not old["channel_id"]:
            sets.append("channel_id=?")
            vals.append(v["channel_id"])
        # 推定日時しか無かったところに RSS の正確日時が来たら上書き
        if v.get("published_at") and (
                not old["published_at"] or
                (old["published_is_estimate"] and not v.get("published_is_estimate"))):
            sets += ["published_at=?", "published_is_estimate=?"]
            vals += [v["published_at"], int(v.get("published_is_estimate", 0))]
        vals.append(v["video_id"])
        con.execute("UPDATE videos SET %s WHERE video_id=?" % ",".join(sets), vals)
    if v.get("views") is not None:
        con.execute("INSERT OR REPLACE INTO snapshots(video_id,ts,views) VALUES(?,?,?)",
                    (v["video_id"], ts, v["views"]))


# ---------------------------------------------------------------- 収集

def register_channels(con, cfg):
    """config のハンドルを channel_id に解決して登録する。"""
    iv = cfg["request_interval_sec"]
    for handle in cfg.get("self_channels", []):
        _register_one(con, handle, iv, is_self=1, is_rival=0)
    for handle in cfg.get("rival_channels", []):
        _register_one(con, handle, iv, is_self=0, is_rival=1)


def _register_one(con, handle, iv, **flags):
    known = con.execute(
        "SELECT channel_id FROM channels WHERE handle=? OR channel_id=?",
        (handle, handle)).fetchone()
    if known and not flags.get("force"):
        # 登録済み。登録者数の更新は週1回でよいので last_checked を見る
        return known["channel_id"]
    try:
        ch = ytfetch.resolve_channel(handle, interval=iv)
    except ytfetch.FetchError as e:
        log("  ! チャンネル解決に失敗 %s (%s)" % (handle, e))
        return None
    upsert_channel(con, ch, **{k: v for k, v in flags.items() if k != "force"})
    log("  + チャンネル登録 %s / %s" % (ch.get("handle") or ch["channel_id"], ch.get("title")))
    return ch["channel_id"]


def refresh_channel_meta(con, cfg, channel_ids):
    """登録者数など。全件やると重いので呼び出し側で絞る。"""
    iv = cfg["request_interval_sec"]
    for cid in channel_ids:
        try:
            ch = ytfetch.resolve_channel(cid, interval=iv)
            upsert_channel(con, ch)
        except ytfetch.FetchError as e:
            log("  ! meta取得失敗 %s (%s)" % (cid, e))


def collect_channels(con, cfg, deep=False):
    iv = cfg["request_interval_sec"]
    rows = con.execute(
        "SELECT * FROM channels WHERE is_muted=0 AND (is_self=1 OR is_rival=1 OR is_favorite=1)").fetchall()
    log("チャンネル収集: %d件" % len(rows))
    # RSS は全チャンネル。ページ取得は自チャンネル + 直近の伸びが良い上位のみ。
    deep_ids = _deep_targets(con, cfg, rows, deep)
    for r in rows:
        cid = r["channel_id"]
        try:
            ch_title, vids = ytfetch.fetch_channel_rss(cid, interval=iv)
            for v in vids:
                upsert_video(con, v, found_by="rss")
            if ch_title and not r["title"]:
                upsert_channel(con, {"channel_id": cid, "title": ch_title})
        except ytfetch.FetchError as e:
            log("  ! RSS失敗 %s (%s)" % (r["title"] or cid, e))
            continue
        if cid in deep_ids:
            try:
                page = ytfetch.fetch_channel_videos(cid, interval=iv)
                for v in page:
                    upsert_video(con, v, found_by="channel_page")
            except ytfetch.FetchError as e:
                log("  ! ページ失敗 %s (%s)" % (r["title"] or cid, e))
        con.execute("UPDATE channels SET last_checked=? WHERE channel_id=?", (now_iso(), cid))
        con.commit()


def _deep_targets(con, cfg, rows, deep):
    if deep:
        return {r["channel_id"] for r in rows}
    ids = {r["channel_id"] for r in rows if r["is_self"] or r["is_favorite"]}
    top = con.execute("""
        SELECT c.channel_id, AVG(v.views) AS av
        FROM channels c JOIN videos v ON v.channel_id=c.channel_id
        WHERE c.is_rival=1 AND c.is_muted=0 AND v.views IS NOT NULL
        GROUP BY c.channel_id ORDER BY av DESC LIMIT ?""",
        (cfg["deep_scan_top_n"],)).fetchall()
    ids.update(r["channel_id"] for r in top)
    return ids


def collect_search(con, cfg):
    iv = cfg["request_interval_sec"]
    found_channels = {}
    total = 0
    for kw in cfg.get("keywords", []):
        for period in cfg.get("search_periods", ["month"]):
            try:
                vids = ytfetch.search_videos(kw, period=period, interval=iv)
            except ytfetch.FetchError as e:
                log("  ! 検索失敗 %s/%s (%s)" % (kw, period, e))
                continue
            for v in vids:
                if cfg["exclude_shorts"] and v.get("duration_sec") and v["duration_sec"] < 75:
                    continue
                upsert_video(con, v, found_by="search:%s" % kw)
                if v.get("channel_id") and v.get("views"):
                    d = found_channels.setdefault(
                        v["channel_id"], {"title": v.get("channel_title"), "n": 0,
                                          "views": 0, "kws": set()})
                    d["n"] += 1
                    d["views"] += v["views"]
                    d["kws"].add(kw)
                total += 1
            log("  検索 %s (%s): %d本" % (kw, period, len(vids)))
        con.commit()
    log("検索から %d本を記録" % total)
    if cfg.get("auto_discover"):
        discover_rivals(con, cfg, found_channels)


GENRE_RE = None  # 遅延コンパイル


def is_relevant_channel(title, cfg):
    """チャンネル名だけで明らかに畑違いのものを弾く。"""
    t = (title or "").lower()
    for w in cfg.get("exclude_channel_words", []):
        if w.lower() in t:
            return False
    return True


def is_same_genre(title, cfg):
    """チャンネル名に同ジャンルの語が入っているか(=直接competitorの可能性が高い)。"""
    global GENRE_RE
    if GENRE_RE is None:
        import re as _re
        GENRE_RE = _re.compile(cfg.get(
            "genre_channel_pattern",
            r"雑学|ライフハック|知恵|暮らし|生活|節約|裏ワザ|裏技|得する|知らな|豆知識"))
    return bool(GENRE_RE.search(title or ""))


def discover_rivals(con, cfg, found):
    """検索に繰り返し出てくる＝同じ土俵のチャンネルだけを競合として自動登録。

    単発でヒットしただけのニュースや実写vlogを入れると、追跡が無駄になり
    「そのチャンネルの平均比」も意味を失うので、
      ・複数キーワードにまたがって出る、または同一キーワードで3本以上
      ・平均再生数が下限以上
      ・チャンネル名が除外ワードを含まない
    の全部を満たしたものだけ登録する。
    """
    current = con.execute("SELECT COUNT(*) c FROM channels WHERE is_rival=1").fetchone()["c"]
    room = max(0, cfg["max_rivals"] - current)
    if room <= 0:
        return
    cands = []
    for cid, d in found.items():
        known = con.execute(
            "SELECT is_self,is_rival,is_muted FROM channels WHERE channel_id=?", (cid,)).fetchone()
        if known and (known["is_self"] or known["is_rival"] or known["is_muted"]):
            continue
        avg = d["views"] / max(1, d["n"])
        if avg < cfg["discover_min_views"]:
            continue
        if not is_relevant_channel(d["title"], cfg):
            continue
        genre = is_same_genre(d["title"], cfg)
        if not genre and len(d.get("kws", ())) < 2 and d["n"] < 3:
            continue
        cands.append((int(genre) * 1000 + len(d.get("kws", ())) * 100 + d["n"], avg, cid, d))
    cands.sort(reverse=True)
    for _, _, cid, d in cands[:room]:
        upsert_channel(con, {"channel_id": cid, "title": d["title"]}, is_rival=1)
        log("  ★ 新しい競合を発見: %s (%d本 / 平均%d回)" % (d["title"], d["n"], d["views"] // d["n"]))
    con.commit()


# ---------------------------------------------------------------- main

def run(quick=False, deep=False):
    cfg = load_config()
    con = connect()
    started = now_iso()
    try:
        register_channels(con, cfg)
        con.commit()
        collect_search(con, cfg)
        if not quick:
            collect_channels(con, cfg, deep=deep)
        # 登録者数が未取得のチャンネルを少しずつ埋める
        missing = [r["channel_id"] for r in con.execute(
            "SELECT channel_id FROM channels WHERE subs IS NULL AND is_muted=0 LIMIT 8")]
        if missing:
            refresh_channel_meta(con, cfg, missing)
        con.commit()
        notify_new_favorite_videos(con, cfg, started)
        import analysis
        report = analysis.write_report(con, BASE)
        con.execute("INSERT OR REPLACE INTO runs(ts,ok,detail) VALUES(?,1,?)",
                    (started, "ok"))
        con.commit()
        log("完了。レポート: %s" % report)
    except Exception as e:  # noqa: BLE001
        log("!! 異常終了: %s\n%s" % (e, traceback.format_exc()))
        con.execute("INSERT OR REPLACE INTO runs(ts,ok,detail) VALUES(?,0,?)", (started, str(e)))
        con.commit()
        raise
    finally:
        con.close()


def main():
    args = sys.argv[1:]
    if "--add" in args:
        i = args.index("--add")
        handles = [a for a in args[i + 1:] if not a.startswith("--")]
        cfg = load_config()
        con = connect()
        for h in handles:
            _register_one(con, h, cfg["request_interval_sec"], is_rival=1, force=True)
        con.commit()
        con.close()
        # config にも残す
        cfg.setdefault("rival_channels", [])
        for h in handles:
            if h not in cfg["rival_channels"]:
                cfg["rival_channels"].append(h)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return
    run(quick="--quick" in args, deep="--deep" in args)


if __name__ == "__main__":
    main()
