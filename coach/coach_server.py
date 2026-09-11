#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""健康コーチのローカルダッシュボード。

  python3 coach_server.py   → http://localhost:8771

127.0.0.1 だけで待ち受けるので、記録が外に出ることはない。
"""

import io
import csv
import json
import os
import traceback
import urllib.parse
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import coach

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("COACH_PORT", "8771"))


def _num(v, cast=float, default=None):
    if v is None or v == "":
        return default
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def _today():
    return date.today().isoformat()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html", "/coach.html"):
                with open(os.path.join(BASE, "coach.html"), encoding="utf-8") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")

            con = coach.connect()
            try:
                if path == "/api/data":
                    d = (qs.get("date") or [_today()])[0]
                    return self._json(coach.build(con, d))

                if path == "/api/foods":
                    q = (qs.get("q") or [""])[0].strip()
                    if q:
                        rows = con.execute(
                            "SELECT * FROM foods WHERE name LIKE ? OR cat LIKE ?"
                            " ORDER BY used DESC, custom DESC, id LIMIT 40",
                            ("%" + q + "%", "%" + q + "%")).fetchall()
                    else:
                        # 検索していないときは、よく使うものを先に見せる
                        rows = con.execute(
                            "SELECT * FROM foods ORDER BY used DESC, id LIMIT 40").fetchall()
                    return self._json([dict(r) for r in rows])

                if path == "/api/history":
                    return self._json(self._history(con, int((qs.get("days") or [90])[0])))

                if path == "/api/export":
                    return self._export(con, (qs.get("kind") or ["bp"])[0])
            finally:
                con.close()
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def _history(self, con, days):
        since = (date.today() - timedelta(days=days)).isoformat()
        meals = con.execute(
            "SELECT date, ROUND(SUM(kcal)) kcal, ROUND(SUM(p),1) p, ROUND(SUM(salt),1) salt"
            " FROM meals WHERE date>=? GROUP BY date ORDER BY date", (since,)).fetchall()
        sleeps = con.execute(
            "SELECT date, minutes, quality FROM sleep WHERE date>=? ORDER BY date",
            (since,)).fetchall()
        days_rows = con.execute(
            "SELECT date, weight, body_fat, muscle_kg, steps, condition FROM days"
            " WHERE date>=? ORDER BY date",
            (since,)).fetchall()
        return {
            "weights": coach.weight_trend(con)["points"],
            "meals": [dict(r) for r in meals],
            "bp": coach.bp_series(con, days),
            "sleep": [dict(r) for r in sleeps],
            "days": [dict(r) for r in days_rows],
            "workouts": [dict(r) for r in con.execute(
                "SELECT date, name, muscle, size, sets, reps, weight, minutes FROM workouts"
                " WHERE date>=? ORDER BY date DESC, id DESC", (since,))],
        }

    def _export(self, con, kind):
        """医師に見せる用の書き出し。家庭血圧の記録は受診時にそのまま使える。"""
        buf = io.StringIO()
        w = csv.writer(buf)
        if kind == "bp":
            w.writerow(["日付", "時間帯", "収縮期(上)", "拡張期(下)", "脈拍"])
            for r in con.execute("SELECT * FROM bp ORDER BY date, id"):
                w.writerow([r["date"], r["slot"], r["systolic"], r["diastolic"], r["pulse"]])
            fname = "katei-ketsuatsu.csv"
        elif kind == "sleep":
            w.writerow(["日付", "就寝", "起床", "睡眠(分)", "質", "中途覚醒", "日中の眠気"])
            for r in con.execute("SELECT * FROM sleep ORDER BY date"):
                w.writerow([r["date"], r["bedtime"], r["waketime"], r["minutes"],
                            r["quality"], r["awakenings"], r["sleepiness"]])
            fname = "sleep.csv"
        else:
            w.writerow(["日付", "体重", "体脂肪率", "筋肉量", "摂取kcal",
                        "たんぱく質g", "食塩g", "歩数"])
            rows = con.execute(
                "SELECT d.date, d.weight, d.body_fat, d.muscle_kg, d.steps,"
                " (SELECT ROUND(SUM(kcal)) FROM meals m WHERE m.date=d.date) kcal,"
                " (SELECT ROUND(SUM(p),1) FROM meals m WHERE m.date=d.date) p,"
                " (SELECT ROUND(SUM(salt),1) FROM meals m WHERE m.date=d.date) salt"
                " FROM days d ORDER BY d.date")
            for r in rows:
                w.writerow([r["date"], r["weight"], r["body_fat"], r["muscle_kg"],
                            r["kcal"], r["p"], r["salt"], r["steps"]])
            fname = "kiroku.csv"
        body = "﻿" + buf.getvalue()          # Excelで開いても文字化けしないBOM付き
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)

        path = urllib.parse.urlparse(self.path).path
        con = coach.connect()
        try:
            handler = {
                "/api/log": self._post_log,
                "/api/import": self._post_import,
                "/api/day": self._post_day,
                "/api/meal": self._post_meal,
                "/api/meal/delete": self._post_meal_delete,
                "/api/workout": self._post_workout,
                "/api/workout/delete": self._post_workout_delete,
                "/api/bp": self._post_bp,
                "/api/bp/delete": self._post_bp_delete,
                "/api/sleep": self._post_sleep,
                "/api/habits": self._post_habits,
                "/api/profile": self._post_profile,
                "/api/food": self._post_food,
            }.get(path)
            if not handler:
                return self._json({"error": "not found"}, 404)
            self._last_log = self._last_import = None
            handler(con, body)
            data = coach.build(con, body.get("date") or _today())
            if self._last_log:
                data["log_result"] = self._last_log
            if self._last_import:
                data["import_result"] = self._last_import
            return self._json(data)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)
        finally:
            con.close()

    def _post_log(self, con, b):
        """1行のテキストをそのまま記録する。結果は次の画面更新で返す。"""
        self._last_log = coach.parse_log(con, b.get("text") or "", b.get("date") or _today())

    def _post_import(self, con, b):
        """ヘルスケアの書き出しファイルを取り込む。パスは同じMac上のもの。"""
        path = os.path.expanduser((b.get("path") or "").strip())
        if not path:
            raise ValueError("ファイルのパスを入れてください")
        if not os.path.exists(path):
            raise ValueError("見つかりません: %s" % path)
        self._last_import = coach.import_health(con, path, b.get("since") or None)

    def _post_day(self, con, b):
        d = b.get("date") or _today()
        con.execute("INSERT OR IGNORE INTO days(date) VALUES(?)", (d,))
        for col in ("weight", "steps", "exercise_min", "condition",
                    "body_fat", "muscle_kg", "note"):
            if col not in b:
                continue
            val = b[col]
            if col in ("weight", "body_fat", "muscle_kg"):
                val = _num(val)
            elif col != "note":
                val = _num(val, int)
            con.execute("UPDATE days SET %s=?, updated_at=? WHERE date=?" % col,
                        (val, datetime.now().isoformat(timespec="seconds"), d))
        con.commit()

    def _post_meal(self, con, b):
        d = b.get("date") or _today()
        qty = _num(b.get("qty"), float, 1.0) or 1.0
        if b.get("food_id"):
            f = con.execute("SELECT * FROM foods WHERE id=?", (b["food_id"],)).fetchone()
            if not f:
                raise ValueError("食品が見つかりません")
            vals = (f["name"], f["kcal"] * qty, f["p"] * qty, f["f"] * qty,
                    f["c"] * qty, f["salt"] * qty)
            con.execute("UPDATE foods SET used=used+1 WHERE id=?", (f["id"],))
        else:
            # 手入力。カロリーだけ分かっているケースも受け付ける
            vals = (b.get("name") or "手入力", _num(b.get("kcal"), float, 0) or 0,
                    _num(b.get("p"), float, 0) or 0, _num(b.get("f"), float, 0) or 0,
                    _num(b.get("c"), float, 0) or 0, _num(b.get("salt"), float, 0) or 0)
            qty = 1.0
        con.execute(
            "INSERT INTO meals(date,slot,name,qty,kcal,p,f,c,salt,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (d, b.get("slot") or "朝", vals[0], qty, round(vals[1], 1), round(vals[2], 1),
             round(vals[3], 1), round(vals[4], 1), round(vals[5], 2),
             datetime.now().isoformat(timespec="seconds")))
        con.commit()

    def _post_meal_delete(self, con, b):
        con.execute("DELETE FROM meals WHERE id=?", (b.get("id"),))
        con.commit()

    def _post_workout(self, con, b):
        name = (b.get("name") or "").strip()
        if not name:
            raise ValueError("種目を選んでください")
        e = coach.EX_BY_NAME.get(name, {"muscle": b.get("muscle") or "その他",
                                        "size": b.get("size") or "small"})
        con.execute(
            "INSERT INTO workouts(date,name,muscle,size,sets,reps,weight,minutes,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (b.get("date") or _today(), name, e["muscle"], e["size"],
             _num(b.get("sets"), int), _num(b.get("reps"), int),
             _num(b.get("weight"), float), _num(b.get("minutes"), int),
             datetime.now().isoformat(timespec="seconds")))
        con.commit()

    def _post_workout_delete(self, con, b):
        con.execute("DELETE FROM workouts WHERE id=?", (b.get("id"),))
        con.commit()

    def _post_bp(self, con, b):
        s, dia = _num(b.get("systolic"), int), _num(b.get("diastolic"), int)
        if not s or not dia:
            raise ValueError("血圧の値を入れてください")
        con.execute("INSERT INTO bp(date,slot,systolic,diastolic,pulse,created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (b.get("date") or _today(), b.get("slot") or "朝", s, dia,
                     _num(b.get("pulse"), int), datetime.now().isoformat(timespec="seconds")))
        con.commit()

    def _post_bp_delete(self, con, b):
        con.execute("DELETE FROM bp WHERE id=?", (b.get("id"),))
        con.commit()

    def _post_sleep(self, con, b):
        d = b.get("date") or _today()
        bed, wake = b.get("bedtime") or "", b.get("waketime") or ""
        mins = coach.sleep_minutes(bed, wake) if bed and wake else None
        con.execute(
            "INSERT OR REPLACE INTO sleep(date,bedtime,waketime,minutes,quality,"
            "awakenings,sleepiness,note,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (d, bed, wake, mins, _num(b.get("quality"), int), _num(b.get("awakenings"), int),
             _num(b.get("sleepiness"), int), b.get("note") or "",
             datetime.now().isoformat(timespec="seconds")))
        con.commit()

    def _post_habits(self, con, b):
        d = b.get("date") or _today()
        done = [k for k in (b.get("done") or []) if any(h["key"] == k for h in coach.HABITS)]
        con.execute("INSERT OR REPLACE INTO habits(date,done,updated_at) VALUES(?,?,?)",
                    (d, json.dumps(done), datetime.now().isoformat(timespec="seconds")))
        con.commit()

    def _post_profile(self, con, b):
        allowed = set(coach.DEFAULT_PROFILE)
        vals = {k: v for k, v in b.items() if k in allowed}
        if "sex" in vals and vals["sex"] not in ("male", "female"):
            vals.pop("sex")
        if "activity" in vals and vals["activity"] not in coach.ACTIVITY:
            vals.pop("activity")
        if "pace" in vals and vals["pace"] not in coach.PACE:
            vals.pop("pace")
        if "bmr_formula" in vals and vals["bmr_formula"] not in ("mifflin", "katch"):
            vals.pop("bmr_formula")
        vals["profile_confirmed"] = 1
        coach.set_profile(con, vals)

    def _post_food(self, con, b):
        con.execute(
            "INSERT OR REPLACE INTO foods(cat,name,unit,kcal,p,f,c,salt,custom,used)"
            " VALUES('マイ食品',?,?,?,?,?,?,?,1,1)",
            (b.get("name") or "名前なし", b.get("unit") or "1食",
             _num(b.get("kcal"), float, 0) or 0, _num(b.get("p"), float, 0) or 0,
             _num(b.get("f"), float, 0) or 0, _num(b.get("c"), float, 0) or 0,
             _num(b.get("salt"), float, 0) or 0))
        con.commit()


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("健康コーチ: http://localhost:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
