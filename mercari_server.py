#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""メルカリShops 自動出品アプリのローカルダッシュボード。

  python3 mercari_server.py   → http://localhost:8771

機能:
  - 出品キューの管理(追加/編集/削除、CSV一括取り込み)
  - ワンクリックで一括出品、毎日決まった時刻の自動出品
  - 出品済み商品の一覧(API取得)、接続テスト、実行ログ
"""

import json
import os
import threading
import traceback
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mercari_api
import mercari_autolist

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = mercari_api.load_config()
PORT = int(CFG.get("port", 8771))

_run_lock = threading.Lock()
_run_state = {"running": False, "last": None}


# ---------------------------------------------------------------- スケジューラ

def scheduler_loop():
    """30秒ごとに設定を確認し、毎日1回、指定時刻に自動出品する。"""
    while True:
        try:
            con = mercari_autolist.connect()
            cfg = mercari_api.load_config()
            enabled = mercari_autolist.get_setting(con, "schedule_enabled")
            if enabled is None:
                enabled = "1" if (cfg.get("schedule") or {}).get("enabled") else "0"
            sched_time = mercari_autolist.get_setting(
                con, "schedule_time",
                (cfg.get("schedule") or {}).get("time", "10:00"))
            today = datetime.now().strftime("%Y-%m-%d")
            last = mercari_autolist.get_setting(con, "schedule_last_run", "")
            now_hm = datetime.now().strftime("%H:%M")
            if enabled == "1" and last != today and now_hm >= sched_time:
                mercari_autolist.set_setting(con, "schedule_last_run", today)
                mercari_autolist.log(con, "info",
                                     "スケジュール出品を開始します(%s)" % sched_time)
                do_run(con, cfg)
            con.close()
        except Exception:
            traceback.print_exc()
        threading.Event().wait(30)


def do_run(con, cfg, limit=None):
    if not _run_lock.acquire(blocking=False):
        return {"error": "すでに出品処理が実行中です"}
    _run_state["running"] = True
    try:
        res = mercari_autolist.run_once(con, limit=limit, cfg=cfg)
        _run_state["last"] = res
        return res
    finally:
        _run_state["running"] = False
        _run_lock.release()


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -------------------------------------------------------------- GET

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(BASE, "mercari_index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/state":
                con = mercari_autolist.connect()
                cfg = mercari_api.load_config()
                sched = cfg.get("schedule") or {}
                state = {
                    "queue": mercari_autolist.list_queue(con),
                    "logs": mercari_autolist.get_logs(con, 100),
                    "running": _run_state["running"],
                    "last_run": _run_state["last"],
                    "has_token": bool(mercari_api.get_token(cfg)),
                    "use_sandbox": bool(cfg.get("use_sandbox")),
                    "endpoint": mercari_api.get_endpoint(cfg),
                    "settings": {
                        "schedule_enabled": mercari_autolist.get_setting(
                            con, "schedule_enabled",
                            "1" if sched.get("enabled") else "0"),
                        "schedule_time": mercari_autolist.get_setting(
                            con, "schedule_time", sched.get("time", "10:00")),
                        "items_per_run": sched.get("items_per_run", 5),
                    },
                    "product_defaults": {
                        k: v for k, v in (cfg.get("product_defaults") or {}).items()
                        if k != "_comment"},
                }
                con.close()
                self._json(state)
            elif path == "/api/test":
                try:
                    data = mercari_api.test_connection()
                    self._json({"ok": True, "data": data})
                except mercari_api.MercariAPIError as e:
                    self._json({"ok": False, "error": str(e)})
            elif path == "/api/products":
                try:
                    items = mercari_api.fetch_products(limit=100)
                    self._json({"ok": True, "products": items})
                except mercari_api.MercariAPIError as e:
                    self._json({"ok": False, "error": str(e)})
            elif path == "/api/schema":
                name = (qs.get("type") or ["CreateProductInput"])[0]
                try:
                    self._json({"ok": True,
                                "text": mercari_api.describe_type(name)})
                except mercari_api.MercariAPIError as e:
                    self._json({"ok": False, "error": str(e)})
            else:
                self._json({"error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception as e:
            traceback.print_exc()
            self._json({"error": str(e)}, 500)

    # -------------------------------------------------------------- POST

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._read_json()
            con = mercari_autolist.connect()
            try:
                if path == "/api/item":
                    item = body.get("item") or {}
                    if not (item.get("name") or "").strip():
                        self._json({"ok": False, "error": "商品名は必須です"})
                        return
                    try:
                        int(item.get("price"))
                    except (TypeError, ValueError):
                        self._json({"ok": False, "error": "価格は数値で入力してください"})
                        return
                    if body.get("id"):
                        mercari_autolist.update_item(con, int(body["id"]), item)
                        self._json({"ok": True, "id": int(body["id"])})
                    else:
                        new_id = mercari_autolist.add_item(con, item)
                        self._json({"ok": True, "id": new_id})
                elif path == "/api/item/delete":
                    mercari_autolist.delete_item(con, int(body["id"]))
                    self._json({"ok": True})
                elif path == "/api/item/requeue":
                    con.execute(
                        "UPDATE queue SET status='queued', error='' WHERE id=?",
                        (int(body["id"]),))
                    con.commit()
                    self._json({"ok": True})
                elif path == "/api/import":
                    try:
                        n = mercari_autolist.import_csv_text(
                            con, body.get("csv") or "")
                        self._json({"ok": True, "count": n})
                    except ValueError as e:
                        self._json({"ok": False, "error": str(e)})
                elif path == "/api/run":
                    cfg = mercari_api.load_config()
                    limit = body.get("limit")
                    res = do_run(con, cfg, limit=int(limit) if limit else None)
                    if "error" in res:
                        self._json({"ok": False, "error": res["error"]})
                    else:
                        self._json({"ok": True, "result": res})
                elif path == "/api/settings":
                    if "schedule_enabled" in body:
                        mercari_autolist.set_setting(
                            con, "schedule_enabled",
                            "1" if body["schedule_enabled"] else "0")
                    if body.get("schedule_time"):
                        mercari_autolist.set_setting(
                            con, "schedule_time", body["schedule_time"])
                    if body.get("token"):
                        mercari_api.save_token(body["token"])
                        mercari_autolist.log(con, "info",
                                             "アクセストークンを保存しました")
                    if "use_sandbox" in body:
                        cfg = mercari_api.load_config()
                        cfg["use_sandbox"] = bool(body["use_sandbox"])
                        mercari_api.save_config(cfg)
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found"}, 404)
            finally:
                con.close()
        except BrokenPipeError:
            pass
        except Exception as e:
            traceback.print_exc()
            self._json({"error": str(e)}, 500)


def main():
    threading.Thread(target=scheduler_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("メルカリShops自動出品アプリ: http://localhost:%d" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
