#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動出品エンジン: 出品キュー(SQLite)の管理と一括出品。

商品はいったん「出品キュー」に登録し(フォーム/CSV)、
run_once() がキューの商品をメルカリShops APIで順に出品する。
mercari_server.py のスケジューラから毎日決まった時刻に呼ばれるほか、
手動実行もできる。

コマンドライン:
  python3 mercari_autolist.py import 商品リスト.csv   # CSVからキューに登録
  python3 mercari_autolist.py list                    # キューを表示
  python3 mercari_autolist.py run [件数]              # 出品を実行
"""

import csv
import io
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import mercari_api

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "mercari.db")

CSV_COLUMNS = ["name", "description", "price", "stock",
               "category_id", "condition", "image_urls"]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price INTEGER NOT NULL,
        stock INTEGER DEFAULT 1,
        category_id TEXT DEFAULT '',
        condition TEXT DEFAULT '',
        image_urls TEXT DEFAULT '[]',
        extra TEXT DEFAULT '{}',
        status TEXT DEFAULT 'queued',
        product_id TEXT DEFAULT '',
        error TEXT DEFAULT '',
        created_at TEXT,
        listed_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, level TEXT, message TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT)""")
    return con


def log(con, level, message):
    con.execute("INSERT INTO logs(ts,level,message) VALUES(?,?,?)",
                (now_iso(), level, message))
    con.commit()


def get_logs(con, limit=100):
    rows = con.execute(
        "SELECT ts,level,message FROM logs ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(con, key, value):
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                (key, str(value)))
    con.commit()


# ---------------------------------------------------------------- キュー操作

def row_to_item(row):
    d = dict(row)
    d["image_urls"] = json.loads(d.get("image_urls") or "[]")
    d["extra"] = json.loads(d.get("extra") or "{}")
    return d


def list_queue(con, status=None):
    if status:
        rows = con.execute(
            "SELECT * FROM queue WHERE status=? ORDER BY id", (status,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM queue ORDER BY id").fetchall()
    return [row_to_item(r) for r in rows]


def add_item(con, item):
    con.execute(
        """INSERT INTO queue(name,description,price,stock,category_id,
           condition,image_urls,extra,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (item["name"].strip(),
         item.get("description", ""),
         int(item["price"]),
         int(item.get("stock") or 1),
         str(item.get("category_id") or ""),
         item.get("condition") or "",
         json.dumps(item.get("image_urls") or [], ensure_ascii=False),
         json.dumps(item.get("extra") or {}, ensure_ascii=False),
         item.get("status") or "queued",
         now_iso()))
    con.commit()
    return con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def update_item(con, item_id, item):
    con.execute(
        """UPDATE queue SET name=?,description=?,price=?,stock=?,category_id=?,
           condition=?,image_urls=?,extra=?,status=?,error='' WHERE id=?""",
        (item["name"].strip(),
         item.get("description", ""),
         int(item["price"]),
         int(item.get("stock") or 1),
         str(item.get("category_id") or ""),
         item.get("condition") or "",
         json.dumps(item.get("image_urls") or [], ensure_ascii=False),
         json.dumps(item.get("extra") or {}, ensure_ascii=False),
         item.get("status") or "queued",
         item_id))
    con.commit()


def delete_item(con, item_id):
    con.execute("DELETE FROM queue WHERE id=?", (item_id,))
    con.commit()


def import_csv_text(con, text):
    """CSVテキストをキューに取り込む。image_urlsは | 区切り。戻り値: 追加件数。"""
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in ("name", "price") if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError("CSVに必須列がありません: " + ", ".join(missing) +
                         " (必要な列: " + ",".join(CSV_COLUMNS) + ")")
    count = 0
    for row in reader:
        if not (row.get("name") or "").strip():
            continue
        urls = [u.strip() for u in (row.get("image_urls") or "").split("|")
                if u.strip()]
        add_item(con, {
            "name": row["name"],
            "description": row.get("description", ""),
            "price": int(float(row["price"])),
            "stock": int(float(row.get("stock") or 1)),
            "category_id": row.get("category_id", ""),
            "condition": row.get("condition", ""),
            "image_urls": urls,
        })
        count += 1
    log(con, "info", "CSVから%d件をキューに登録しました" % count)
    return count


# ---------------------------------------------------------------- 出品実行

def run_once(con, limit=None, interval=None, cfg=None):
    """キュー(status=queued)の商品を古い順にlimit件出品する。

    戻り値: {"listed": n, "failed": n, "results": [...]}
    """
    if cfg is None:
        cfg = mercari_api.load_config()
    sched = cfg.get("schedule") or {}
    if limit is None:
        limit = int(sched.get("items_per_run") or 5)
    if interval is None:
        interval = float(sched.get("interval_seconds") or 5)

    items = list_queue(con, "queued")[:limit]
    results = {"listed": 0, "failed": 0, "results": []}
    if not items:
        log(con, "info", "出品対象がありません(キューが空です)")
        return results

    log(con, "info", "出品を開始します(%d件)" % len(items))
    for i, item in enumerate(items):
        try:
            product = mercari_api.create_product(item, cfg=cfg)
            pid = product.get("id") or ""
            con.execute(
                "UPDATE queue SET status='listed', product_id=?, error='',"
                " listed_at=? WHERE id=?",
                (pid, now_iso(), item["id"]))
            con.commit()
            results["listed"] += 1
            results["results"].append(
                {"id": item["id"], "name": item["name"], "ok": True,
                 "product_id": pid})
            log(con, "info", "出品成功: %s (product_id=%s)" % (item["name"], pid))
        except mercari_api.MercariAPIError as e:
            con.execute("UPDATE queue SET status='error', error=? WHERE id=?",
                        (str(e), item["id"]))
            con.commit()
            results["failed"] += 1
            results["results"].append(
                {"id": item["id"], "name": item["name"], "ok": False,
                 "error": str(e)})
            log(con, "error", "出品失敗: %s → %s" % (item["name"], e))
            if e.status == 401:
                log(con, "error", "認証エラーのため中断します")
                break
        if i < len(items) - 1 and interval > 0:
            time.sleep(interval)

    log(con, "info",
        "出品完了: 成功%d件 / 失敗%d件" % (results["listed"], results["failed"]))
    return results


# ---------------------------------------------------------------- CLI

def main(argv):
    con = connect()
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "import":
        if len(argv) < 3:
            print("使い方: python3 mercari_autolist.py import 商品リスト.csv")
            return 1
        with open(argv[2], encoding="utf-8-sig") as f:
            n = import_csv_text(con, f.read())
        print("%d件をキューに登録しました" % n)
    elif cmd == "list":
        for it in list_queue(con):
            print("[%s] #%d %s ¥%d %s" % (
                it["status"], it["id"], it["name"], it["price"],
                it["error"] or ""))
    elif cmd == "run":
        limit = int(argv[2]) if len(argv) > 2 else None
        res = run_once(con, limit=limit)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
