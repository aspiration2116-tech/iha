#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""リサーチ結果を見るためのローカルダッシュボード。

  python3 server.py     → http://localhost:8770
"""

import json
import os
import threading
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import analysis
import research
import videogen
import websearch
import ytfetch

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = research.load_config()
PORT = int(CFG.get("port", 8770))

_run_lock = threading.Lock()
_run_state = {"running": False, "message": "", "last": None}

THUMB_DIR = os.path.join(BASE, "thumbs")

_video_lock = threading.Lock()
_video_state = {"running": False, "step": "", "message": "", "error": "",
                "output": None, "total_sec": None}


def _video_cfg():
    """config.json の video 設定を既定値に重ねる。"""
    cfg = dict(videogen.DEFAULTS)
    cfg.update(CFG.get("video", {}))
    if CFG.get("pixabay_key"):
        cfg.setdefault("pixabay_key", CFG["pixabay_key"])
    return cfg


def _video_run(fn, step):
    """重い処理をバックグラウンドで走らせる。同時に1本だけ。"""
    if not _video_lock.acquire(blocking=False):
        return False
    _video_state.update(running=True, step=step, message="準備しています",
                        error="", output=None)

    def worker():
        try:
            fn(lambda m: _video_state.update(message=m))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _video_state["error"] = str(e)
        finally:
            _video_state["running"] = False
            _video_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    return True

AI_PROMPT_HEADER = CFG.get("ai_prompt_header",
    "あなたはYouTubeの「ライフハック雑学」チャンネルの放送作家です。"
    "以下のリサーチ資料(伸びている競合動画の台本・コメント欄の反応・類似動画)を分析して、"
    "同じテーマでより面白い10〜11分の動画台本を作成してください。"
    "コメント欄で視聴者が反応しているポイントは必ず盛り込んでください。\n\n")


def get_transcript_cached(con, vid):
    row = con.execute("SELECT * FROM transcripts WHERE video_id=?", (vid,)).fetchone()
    if row:
        return {"lang": row["lang"], "kind": row["kind"], "text": row["text"],
                "description": row["description"]}
    tr = ytfetch.fetch_transcript(vid, interval=1.0)
    if tr is None:
        return None
    con.execute(
        "INSERT OR REPLACE INTO transcripts(video_id,lang,kind,text,description,fetched_at)"
        " VALUES(?,?,?,?,?,?)",
        (vid, tr["lang"], tr["kind"], tr["text"], tr["description"],
         datetime.now(timezone.utc).isoformat()))
    con.commit()
    return tr


def get_comments_cached(con, vid, refresh=False):
    row = con.execute("SELECT * FROM comments WHERE video_id=?", (vid,)).fetchone()
    if row and not refresh:
        comments = json.loads(row["json"])
        # 要約ロジックは改良されることがあるので、キャッシュした生コメントから毎回作り直す
        return comments, analysis.summarize_comments(comments)
    comments = ytfetch.fetch_comments(vid, max_comments=60, interval=1.0)
    summary = analysis.summarize_comments(comments)
    if comments:  # 空(取得失敗の可能性)はキャッシュせず、次回また試す
        con.execute("INSERT OR REPLACE INTO comments(video_id,json,summary,fetched_at) VALUES(?,?,?,?)",
                    (vid, json.dumps(comments, ensure_ascii=False), summary,
                     datetime.now(timezone.utc).isoformat()))
        con.commit()
    return comments, summary


# URLプレフィルの上限。日本語はURLエンコードで1文字9バイトになり、
# CDN側のURL上限(約32KB)を超えると開けないので、ここで頭打ちにする。
PREFILL_MAX = 3400

PREFILL_PROMPT = CFG.get("ai_prefill_prompt",
    "あなたはYouTube「ライフハック雑学」チャンネルの放送作家です。"
    "以下のリサーチ資料(参考動画の台本とコメント欄の反応)を読み、"
    "まず参考動画の【いいところ】と【改善点】を3つずつ挙げてください。"
    "そのあと、同じテーマでより面白い10〜11分の動画台本(タイトル案3つ+サムネ文言案+本文)を書いてください。"
    "コメント欄で視聴者が反応しているポイントは必ず台本に反映してください。\n\n")


def build_prefill(con, vid):
    """AIサイトの入力欄に直接入れる凝縮版パック。

    台本とコメント要約を最優先で入れ、残りの枠に分析結果と類似動画を詰める。
    返り値: {text(入力欄用), clip(続けて貼る台本全文), truncated}"""
    detail = analysis.video_detail(con, vid)
    if detail is None:
        return None
    v = detail["video"]
    tr = None
    try:
        tr = get_transcript_cached(con, vid)
    except Exception:  # noqa: BLE001
        pass
    try:
        comments, _ = get_comments_cached(con, vid)
    except Exception:  # noqa: BLE001
        comments = []

    # --- 固定部(プロンプト+動画情報+分析+コメント+類似) ---
    L = [PREFILL_PROMPT]
    L.append("■ 参考動画")
    L.append("タイトル: %s" % v.get("title", ""))
    L.append("チャンネル: %s / 再生: %s回 / 投稿: %s日前" % (
        v.get("channel_title", ""), v.get("views", "-"), v.get("age_days", "-")))
    L.append("サムネ: https://i.ytimg.com/vi/%s/maxresdefault.jpg" % vid)
    stats = []
    if v.get("recent_vph") or v.get("vph"):
        stats.append("時速%s回" % (v.get("recent_vph") or v.get("vph")))
    if v.get("multiple"):
        stats.append("通常回の%s倍" % v["multiple"])
    L.append("分析: 型[%s] / 伸び %s" % (
        " / ".join(detail.get("patterns", [])[:4]) or "-", "、".join(stats) or "-"))
    L.append("")
    L.append("■ コメント欄の反応(いいね順の要約)")
    L.append(analysis.summarize_comments(comments, top_n=5, max_len=60, neg_n=3))
    L.append("")
    L.append("■ 似たネタの動画")
    for s in detail.get("similar", [])[:4]:
        title = s.get("title", "")
        if len(title) > 38:
            title = title[:38] + "…"
        L.append("・%s%s — %s回" % (
            "[自分] " if s.get("is_self") else "", title, s.get("views", "-")))
    L.append("")
    head = "\n".join(L)

    # --- 残り枠を全部台本に使う ---
    full_tr = (tr or {}).get("text") or "(字幕がありません)"
    budget = PREFILL_MAX - len(head) - 130
    truncated = len(full_tr) > budget
    if truncated:
        # 冒頭(つかみ)と結末(まとめ・CTA)の両方を入れて、中間を省略する
        head_len = int(budget * 0.72)
        tail_len = max(budget - head_len, 150)
        L.append("■ 台本(長いため中略あり。全文はこの直後のメッセージで貼り付けるので、それを待ってから回答してください)")
        L.append(full_tr[:head_len] + "\n…(中略)…\n" + full_tr[-tail_len:])
    else:
        L.append("■ 台本(全文)")
        L.append(full_tr)
    clip = "■ 台本の全文(先ほどの続き)\n\n" + full_tr if truncated else ""
    return {"text": "\n".join(L), "clip": clip, "truncated": truncated}


def build_pack(con, vid):
    """台本作成用リサーチパック: 対象動画 + 台本 + コメント要約 + 類似動画。"""
    detail = analysis.video_detail(con, vid)
    if detail is None:
        return None
    v = detail["video"]
    L = []
    L.append("■ 対象動画")
    L.append("タイトル: %s" % v.get("title", ""))
    L.append("チャンネル: %s / 再生: %s回 / 投稿: %s日前 / チャンネル平均比: %sx" % (
        v.get("channel_title", ""), v.get("views", "-"),
        v.get("age_days", "-"), v.get("multiple", "-")))
    L.append("URL: %s" % v.get("url", ""))
    L.append("当てはまるタイトルの型: %s" % " / ".join(detail.get("patterns", []) or ["-"]))
    L.append("")
    tr = None
    try:
        tr = get_transcript_cached(con, vid)
    except Exception:  # noqa: BLE001
        pass
    L.append("■ 台本(%s)" % ({"asr": "自動生成字幕"}.get((tr or {}).get("kind"), "手動字幕") if tr else "取得失敗"))
    L.append(tr["text"] if tr else "(字幕がありません)")
    L.append("")
    try:
        _, summary = get_comments_cached(con, vid)
    except Exception:  # noqa: BLE001
        summary = "(コメント取得失敗)"
    L.append("■ コメント欄の反応(いいね順の上位)")
    L.append(summary)
    L.append("")
    L.append("■ 類似ネタの動画")
    for s in detail.get("similar", [])[:10]:
        L.append("・%s%s — %s回 (%s) %s" % (
            "[自分の動画] " if s.get("is_self") else "",
            s.get("title", ""), s.get("views", "-"),
            s.get("channel_title", ""), s.get("url", "")))
    return "\n".join(L)


def get_thumb(video_id, chain):
    """サムネをローカルにキャッシュしつつ返す。

    i.ytimg.com への直接アクセスがブラウザ側で遮断される環境があるため、
    画像は必ずこのサーバー経由(同一オリジン)で配る。"""
    os.makedirs(THUMB_DIR, exist_ok=True)
    cache = os.path.join(THUMB_DIR, "%s_%s.jpg" % (video_id, chain[0]))
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        with open(cache, "rb") as f:
            return f.read()
    for size in chain:
        try:
            req = urllib.request.Request("https://i.ytimg.com/vi/%s/%s.jpg" % (video_id, size),
                                         headers={"User-Agent": ytfetch.UA})
            with urllib.request.urlopen(req, timeout=15) as res:
                data = res.read()
            if len(data) < 1500:
                continue  # YouTube はサイズ違いに灰色のダミー画像を返すことがある
            with open(cache, "wb") as f:
                f.write(data)
            return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _background_run(quick):
    with _run_lock:
        if _run_state["running"]:
            return
        _run_state["running"] = True
        _run_state["message"] = "収集中..."

    def job():
        try:
            research.run(quick=quick)
            _run_state["message"] = "完了"
        except Exception as e:  # noqa: BLE001
            _run_state["message"] = "エラー: %s" % e
            traceback.print_exc()
        finally:
            _run_state["running"] = False

    threading.Thread(target=job, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def handle_one_request(self):
        # ブラウザが読み込みを途中でやめると接続が切れる。実害がないので黙って閉じる
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(BASE, "index.html"), encoding="utf-8") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/data":
                con = research.connect()
                try:
                    data = analysis.build_all(con)
                finally:
                    con.close()
                data["run_state"] = _run_state
                data["config"] = {"keywords": CFG.get("keywords", [])}
                return self._send(200, json.dumps(data, ensure_ascii=False))
            if path == "/api/run":
                _background_run(qs.get("quick", ["0"])[0] == "1")
                return self._send(200, json.dumps(_run_state))
            if path == "/api/state":
                # 収集中は何をしているか見えるようにログの最終行を返す
                tail = ""
                try:
                    with open(research.LOG_PATH, encoding="utf-8") as f:
                        lines = [l.strip() for l in f.readlines()[-40:] if l.strip()]
                    if lines:
                        tail = lines[-1].split("] ", 1)[-1]
                except OSError:
                    pass
                return self._send(200, json.dumps(dict(_run_state, log=tail),
                                                  ensure_ascii=False))
            if path == "/api/video/env":
                env = videogen.check_env(_video_cfg())
                env["folder"] = BASE
                env["work"] = videogen.WORK
                env["projects"] = sorted(os.listdir(videogen.WORK)) \
                    if os.path.isdir(videogen.WORK) else []
                return self._send(200, json.dumps(env, ensure_ascii=False))
            if path == "/api/video/progress":
                return self._send(200, json.dumps(_video_state, ensure_ascii=False))
            if path == "/api/video/plan":
                plan = videogen.load_plan(videogen.project_dir(qs.get("name", [""])[0]))
                return self._send(200, json.dumps(plan or {}, ensure_ascii=False))
            if path == "/api/video/file":
                # 作業フォルダの中だけを返す
                rel = qs.get("p", [""])[0]
                full = os.path.realpath(os.path.join(videogen.WORK, rel))
                if not full.startswith(os.path.realpath(videogen.WORK)) \
                        or not os.path.isfile(full):
                    return self._send(404, json.dumps({"error": "not found"}))
                ctype = {"mp4": "video/mp4", "jpg": "image/jpeg", "png": "image/png",
                         "wav": "audio/wav"}.get(full.rsplit(".", 1)[-1].lower(),
                                                 "application/octet-stream")
                with open(full, "rb") as f:
                    return self._send(200, f.read(), ctype)
            if path == "/api/mute":
                cid = qs.get("channel_id", [""])[0]
                con = research.connect()
                con.execute("UPDATE channels SET is_muted=1, is_rival=0 WHERE channel_id=?", (cid,))
                con.commit()
                con.close()
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/webthumb":
                # Yahoo検索のサムネ(yimg.jp)だけ中継する。外部画像を遮断する環境対策
                u = qs.get("u", [""])[0]
                host = urllib.parse.urlparse(u).netloc
                if not (u.startswith("https://") and
                        (host.endswith(".yimg.jp") or host.endswith(".ggpht.com") or
                         host.endswith(".ytimg.com"))):
                    return self._send(400, json.dumps({"error": "host not allowed"}))
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": ytfetch.UA})
                    with urllib.request.urlopen(req, timeout=15) as res:
                        ctype = res.headers.get("Content-Type", "image/jpeg")
                        return self._send(200, res.read(), ctype)
                except Exception:  # noqa: BLE001
                    return self._send(404, json.dumps({"error": "fetch failed"}))
            if path == "/api/websearch":
                kw = qs.get("q", [""])[0].strip()
                if not kw:
                    return self._send(400, json.dumps({"error": "q required"}))
                srcs = [s for s in qs.get("sources", [""])[0].split(",") if s]
                results = websearch.search_all(kw, srcs or None)
                return self._send(200, json.dumps(
                    {"q": kw, "results": results}, ensure_ascii=False))
            if path == "/api/search":
                kw = qs.get("q", [""])[0].strip()
                period = qs.get("period", ["all"])[0]
                if not kw:
                    return self._send(400, json.dumps({"error": "q required"}))
                vids = ytfetch.search_videos(kw, period=period, interval=1.0, limit=100)
                con = research.connect()
                try:
                    known = {}
                    for v in vids:
                        research.upsert_video(con, v, found_by="manual:%s" % kw)
                        if v.get("channel_id"):
                            row = con.execute(
                                "SELECT is_self,is_rival,is_favorite FROM channels WHERE channel_id=?",
                                (v["channel_id"],)).fetchone()
                            if row:
                                known[v["channel_id"]] = dict(row)
                    con.commit()
                finally:
                    con.close()
                now = datetime.now(timezone.utc)
                out = []
                for v in vids:
                    age_days = None
                    if v.get("published_at"):
                        try:
                            pub = datetime.fromisoformat(v["published_at"])
                            age_days = round((now - pub).total_seconds() / 86400.0, 1)
                        except ValueError:
                            pass
                    k = known.get(v.get("channel_id"), {})
                    out.append({
                        "video_id": v["video_id"],
                        "title": v.get("title", ""),
                        "channel_id": v.get("channel_id"),
                        "channel_title": v.get("channel_title") or "(不明)",
                        "views": v.get("views"),
                        "age_days": age_days,
                        "duration_sec": v.get("duration_sec"),
                        "is_self": int(bool(k.get("is_self"))),
                        "is_rival": int(bool(k.get("is_rival"))),
                        "url": "https://www.youtube.com/watch?v=%s" % v["video_id"],
                        "thumb": "/api/thumb?size=mq&video_id=%s" % v["video_id"],
                    })
                return self._send(200, json.dumps(
                    {"q": kw, "period": period, "results": out}, ensure_ascii=False))
            if path == "/api/video":
                vid = qs.get("video_id", [""])[0]
                con = research.connect()
                try:
                    d = analysis.video_detail(con, vid)
                finally:
                    con.close()
                if d is None:
                    return self._send(404, json.dumps({"error": "unknown video"}))
                return self._send(200, json.dumps(d, ensure_ascii=False))
            if path == "/api/transcript":
                vid = qs.get("video_id", [""])[0]
                if not vid:
                    return self._send(400, json.dumps({"error": "video_id required"}))
                con = research.connect()
                try:
                    row = con.execute("SELECT * FROM transcripts WHERE video_id=?",
                                      (vid,)).fetchone()
                    if row and qs.get("refresh", ["0"])[0] != "1":
                        return self._send(200, json.dumps({
                            "video_id": vid, "lang": row["lang"], "kind": row["kind"],
                            "text": row["text"], "description": row["description"],
                            "cached": True}, ensure_ascii=False))
                    tr = ytfetch.fetch_transcript(vid, interval=1.0)
                    if tr is None:
                        return self._send(200, json.dumps(
                            {"video_id": vid, "text": None,
                             "error": "この動画には字幕がありません"}, ensure_ascii=False))
                    con.execute(
                        "INSERT OR REPLACE INTO transcripts(video_id,lang,kind,text,description,fetched_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (vid, tr["lang"], tr["kind"], tr["text"], tr["description"],
                         datetime.now(timezone.utc).isoformat()))
                    con.commit()
                    return self._send(200, json.dumps({
                        "video_id": vid, "lang": tr["lang"], "kind": tr["kind"],
                        "text": tr["text"], "description": tr["description"],
                        "cached": False}, ensure_ascii=False))
                finally:
                    con.close()
            if path == "/api/thumb":
                vid = qs.get("video_id", [""])[0]
                if not vid or not vid.replace("-", "").replace("_", "").isalnum():
                    return self._send(400, json.dumps({"error": "bad video_id"}))
                # 一覧用は小さい mq、コピー用は maxres を優先する
                small = qs.get("size", [""])[0] == "mq"
                chain = (("mqdefault", "hqdefault") if small
                         else ("maxresdefault", "sddefault", "hqdefault"))
                data = get_thumb(vid, chain)
                if data is None:
                    return self._send(404, json.dumps({"error": "thumbnail not found"}))
                return self._send(200, data, "image/jpeg")
            if path == "/api/pack":
                vid = qs.get("video_id", [""])[0]
                mode = qs.get("mode", ["full"])[0]
                con = research.connect()
                try:
                    if mode == "prefill":
                        d = build_prefill(con, vid)
                        if d is None:
                            return self._send(404, json.dumps({"error": "unknown video"}))
                        d["video_id"] = vid
                        return self._send(200, json.dumps(d, ensure_ascii=False))
                    pack = build_pack(con, vid)
                finally:
                    con.close()
                if pack is None:
                    return self._send(404, json.dumps({"error": "unknown video"}))
                with_prompt = qs.get("prompt", ["0"])[0] == "1"
                text = (AI_PROMPT_HEADER + pack) if with_prompt else pack
                return self._send(200, json.dumps({"video_id": vid, "text": text},
                                                  ensure_ascii=False))
            if path == "/api/comments":
                vid = qs.get("video_id", [""])[0]
                con = research.connect()
                try:
                    comments, summary = get_comments_cached(
                        con, vid, refresh=qs.get("refresh", ["0"])[0] == "1")
                finally:
                    con.close()
                return self._send(200, json.dumps(
                    {"video_id": vid, "count": len(comments),
                     "summary": summary, "comments": comments}, ensure_ascii=False))
            if path == "/api/fav":
                cid = qs.get("channel_id", [""])[0]
                on = qs.get("on", ["1"])[0] == "1"
                con = research.connect()
                con.execute("UPDATE channels SET is_favorite=? WHERE channel_id=?",
                            (1 if on else 0, cid))
                con.commit()
                con.close()
                return self._send(200, json.dumps({"ok": True, "favorite": on}))
            if path == "/api/memos":
                con = research.connect()
                rows = [dict(r) for r in con.execute(
                    "SELECT * FROM memos ORDER BY updated_at DESC")]
                con.close()
                return self._send(200, json.dumps({"memos": rows}, ensure_ascii=False))
            if path == "/api/memo/delete":
                mid = qs.get("id", ["0"])[0]
                con = research.connect()
                con.execute("DELETE FROM memos WHERE id=?", (mid,))
                con.commit()
                con.close()
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/report":
                p = os.path.join(BASE, "ネタ候補.md")
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        return self._send(200, f.read(), "text/plain; charset=utf-8")
                return self._send(404, "まだレポートがありません", "text/plain; charset=utf-8")
            return self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if parsed.path == "/api/memo":
                now = datetime.now(timezone.utc).isoformat()
                con = research.connect()
                try:
                    if body.get("id"):
                        con.execute(
                            "UPDATE memos SET title=?, body=?, updated_at=? WHERE id=?",
                            (body.get("title", ""), body.get("body", ""), now, body["id"]))
                        mid = body["id"]
                    else:
                        cur = con.execute(
                            "INSERT INTO memos(title,body,video_id,created_at,updated_at)"
                            " VALUES(?,?,?,?,?)",
                            (body.get("title", ""), body.get("body", ""),
                             body.get("video_id"), now, now))
                        mid = cur.lastrowid
                    con.commit()
                finally:
                    con.close()
                return self._send(200, json.dumps({"ok": True, "id": mid}))
            if parsed.path == "/api/video/plan":
                pdir = videogen.project_dir(body.get("name", "project"))
                plan = videogen.build_plan(body.get("script", ""),
                                           body.get("topic", ""), _video_cfg())
                videogen.save_plan(pdir, plan)
                return self._send(200, json.dumps(plan, ensure_ascii=False))
            if parsed.path == "/api/video/clip":
                # 1クリップの字幕・読み上げ文・検索語・画像を差し替える
                pdir = videogen.project_dir(body.get("name", "project"))
                plan = videogen.load_plan(pdir)
                if not plan:
                    return self._send(404, json.dumps({"error": "台本がまだありません"}))
                c = plan["clips"][int(body["index"])]
                for key in ("caption", "speech", "keyword"):
                    if key in body:
                        c[key] = body[key]
                if "caption" in body:
                    c["caption_lines"] = body["caption"].split("\n")
                if body.get("image_url"):
                    path = os.path.join(pdir, "images", "%05d.jpg" % c["index"])
                    videogen.download(body["image_url"], path)
                    c["image"] = path
                if body.get("speech") is not None:
                    c["audio"] = None      # 読み上げ文が変わったので音声は作り直す
                    c["duration"] = None
                plan["stats"] = videogen.plan_stats(plan["clips"])
                videogen.save_plan(pdir, plan)
                return self._send(200, json.dumps(c, ensure_ascii=False))
            if parsed.path == "/api/video/imagesearch":
                cfg = _video_cfg()
                if not cfg.get("pixabay_key"):
                    return self._send(400, json.dumps(
                        {"error": "config.json に pixabay_key がありません"},
                        ensure_ascii=False))
                hits = videogen.pixabay_search(
                    body.get("keyword", ""), cfg["pixabay_key"],
                    body.get("image_type", cfg["image_type"]))
                return self._send(200, json.dumps(hits, ensure_ascii=False))
            if parsed.path in ("/api/video/audio", "/api/video/images",
                               "/api/video/render", "/api/video/all"):
                pdir = videogen.project_dir(body.get("name", "project"))
                plan = videogen.load_plan(pdir)
                if not plan:
                    return self._send(400, json.dumps(
                        {"error": "先に台本を読み込んでください"}, ensure_ascii=False))
                cfg = _video_cfg()
                cfg.update(body.get("config", {}))
                bgm = body.get("bgm", [])
                what = parsed.path.rsplit("/", 1)[-1]

                def job(progress, what=what, pdir=pdir, plan=plan, cfg=cfg, bgm=bgm):
                    if what == "audio":
                        videogen.make_audio(pdir, plan, cfg["voicevox_speaker"],
                                            cfg.get("voice_speed", 1.0), progress,
                                            overwrite=bool(body.get("overwrite")))
                    elif what == "images":
                        videogen.fetch_images(pdir, plan, cfg.get("pixabay_key"),
                                              cfg["image_type"], progress,
                                              overwrite=bool(body.get("overwrite")))
                    elif what == "render":
                        out, total = videogen.render(pdir, plan["clips"], cfg, bgm,
                                                     progress=progress)
                        _video_state.update(output=out, total_sec=total)
                    else:
                        out, total = videogen.run_all(pdir, plan, cfg, bgm, progress)
                        _video_state.update(output=out, total_sec=total)

                if not _video_run(job, what):
                    return self._send(409, json.dumps(
                        {"error": "いま別の処理を実行中です"}, ensure_ascii=False))
                return self._send(200, json.dumps(_video_state, ensure_ascii=False))
            return self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("リサーチダッシュボード: http://localhost:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
