#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""健康コーチ — 体重・食事・血圧・睡眠を記録して、その日の指示を出すエンジン。

  python3 coach_server.py    → http://localhost:8771 (ダッシュボード)
  python3 coach.py today     → 今日の状況とアドバイスを端末に表示
  python3 coach.py weight 98.4
  python3 coach.py bp 145 92 --slot 朝
  python3 coach.py import                       # iCloud Drive/ダウンロードから自動で探す
  python3 coach.py import ~/Downloads/書き出したデータ.zip

外部ライブラリは使わない(標準ライブラリのみ)。データは coach.db (SQLite)。

【重要】このツールは医療機器でも診断ツールでもありません。数値はすべて一般的な
目安です。治療中の病気・服薬がある場合、または高い血圧が続く場合は必ず医師に
相談してください。判定ロジックの根拠は README.md にまとめてあります。
"""

import json
import math
import os
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "coach.db")
FOODS_PATH = os.path.join(BASE, "foods.json")
PROFILE_PATH = os.path.join(BASE, "profile.json")

# ── 定数 ───────────────────────────────────────────────────────────────────

KCAL_PER_KG_FAT = 7200.0        # 体脂肪1kgあたりの熱量(概算)

# 活動レベル → 身体活動レベル(PAL)
ACTIVITY = {
    "low":    (1.30, "座り仕事中心・ほとんど歩かない"),
    "mid":    (1.45, "立ち仕事や通勤の歩きがある・軽い運動"),
    "high":   (1.60, "よく動く仕事 / 週3〜5回の運動"),
}

# 減量ペース → 週あたりの体重減少率(現体重比)
PACE = {
    "slow":     (0.0050, "ゆっくり(週0.5%)"),
    "standard": (0.0075, "標準(週0.75%)"),
    "fast":     (0.0100, "速め(週1.0%)"),
}

# 摂取カロリーの絶対下限。これ以下は栄養が満たせず、筋肉と代謝が落ちる
KCAL_FLOOR = {"male": 1500, "female": 1200}

# 1日の赤字はTDEEの何割までにするか(急激な減量を防ぐ安全弁)
MAX_DEFICIT_RATIO = 0.25

# 既定値はあくまで初期表示用のプレースホルダ。実際の値は
#   ・同じフォルダの profile.json (gitignore済み。個人の値をここに置ける)
#   ・または画面の「設定」タブ(coach.db に入る。これもgitignore済み)
# のどちらかで上書きする。身体の数値をリポジトリに残さないための分け方。
DEFAULT_PROFILE = {
    "height": 170.0,
    "start_weight": 80.0,
    "goal_weight": 70.0,
    "sex": "male",
    "age": 40,
    "activity": "low",
    "pace": "standard",
    "salt_target": 6.0,          # g/日。高血圧の減塩目標(JSH2019)
    "sleep_target": 450,         # 分。7時間30分
    "wake_target": "06:30",      # 起床時刻を固定するのが睡眠改善の土台
    "step_target": 8000,
    "bmr_formula": "mifflin",    # mifflin / katch(除脂肪体重ベース。体組成を記録していれば選べる)
    "bone_ratio": 0.035,         # 推定骨量の体重比。筋肉量から除脂肪体重を出すときに使う
    "on_bp_medication": 0,       # 降圧薬を飲んでいるか
    "snoring": 0,                # いびきを指摘される
    "observed_apnea": 0,         # 睡眠中に呼吸が止まると言われた
    "neck_cm": 0.0,              # 首まわり(cm)。0なら未入力
    "profile_confirmed": 0,      # 設定画面で一度確認したか
}

MEAL_SLOTS = ["朝", "昼", "夕", "間食"]


# ── DB ────────────────────────────────────────────────────────────────────

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    init_db(con)
    return con


def init_db(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS profile(
        key TEXT PRIMARY KEY, value TEXT);

    -- 1日1行。体重・歩数・体調など
    CREATE TABLE IF NOT EXISTS days(
        date TEXT PRIMARY KEY,
        weight REAL, steps INTEGER, exercise_min INTEGER,
        condition INTEGER,            -- 体調 1(悪い)〜5(良い)
        body_fat REAL,                -- 体脂肪率 %
        muscle_kg REAL,               -- 筋肉量 kg(体組成計の表示値)
        note TEXT, updated_at TEXT);

    CREATE TABLE IF NOT EXISTS meals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, slot TEXT, name TEXT, qty REAL,
        kcal REAL, p REAL, f REAL, c REAL, salt REAL, created_at TEXT);
    CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(date);

    CREATE TABLE IF NOT EXISTS bp(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, slot TEXT,         -- 朝 / 晩
        systolic INTEGER, diastolic INTEGER, pulse INTEGER,
        created_at TEXT);
    CREATE INDEX IF NOT EXISTS idx_bp_date ON bp(date);

    CREATE TABLE IF NOT EXISTS sleep(
        date TEXT PRIMARY KEY,        -- 「その朝に起きた日」で記録する
        bedtime TEXT, waketime TEXT, minutes INTEGER,
        quality INTEGER,              -- 眠りの質 1〜5
        awakenings INTEGER,           -- 夜中に目が覚めた回数
        sleepiness INTEGER,           -- 日中の眠気 1〜5
        note TEXT, updated_at TEXT);

    -- 睡眠の習慣チェック(1日1行、done は JSON の配列)
    CREATE TABLE IF NOT EXISTS habits(
        date TEXT PRIMARY KEY, done TEXT, updated_at TEXT);

    CREATE TABLE IF NOT EXISTS workouts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, name TEXT, muscle TEXT,
        size TEXT,                    -- big(大筋群) / small(小筋群) / cardio
        sets INTEGER, reps INTEGER, weight REAL, minutes INTEGER,
        created_at TEXT);
    CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);

    CREATE TABLE IF NOT EXISTS foods(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cat TEXT, name TEXT UNIQUE, unit TEXT,
        kcal REAL, p REAL, f REAL, c REAL, salt REAL,
        custom INTEGER DEFAULT 0, used INTEGER DEFAULT 0);
    """)
    have = {r["name"] for r in con.execute("PRAGMA table_info(days)")}
    for col in ("body_fat REAL", "muscle_kg REAL"):
        if col.split()[0] not in have:
            con.execute("ALTER TABLE days ADD COLUMN " + col)
    con.commit()
    if con.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 0:
        load_builtin_foods(con)
    if con.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0:
        prof = dict(DEFAULT_PROFILE)
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, encoding="utf-8") as f:
                prof.update({k: v for k, v in json.load(f).items() if k in DEFAULT_PROFILE})
            prof["profile_confirmed"] = 1
        set_profile(con, prof)


def load_builtin_foods(con):
    with open(FOODS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    con.executemany(
        "INSERT OR IGNORE INTO foods(cat,name,unit,kcal,p,f,c,salt,custom)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        [(x["cat"], x["name"], x["unit"], x["kcal"], x["p"], x["f"], x["c"], x["salt"])
         for x in data["foods"]])
    con.commit()


def get_profile(con):
    prof = dict(DEFAULT_PROFILE)
    for row in con.execute("SELECT key, value FROM profile"):
        default = DEFAULT_PROFILE.get(row["key"])
        try:
            if isinstance(default, float):
                prof[row["key"]] = float(row["value"])
            elif isinstance(default, int):
                prof[row["key"]] = int(float(row["value"]))
            else:
                prof[row["key"]] = row["value"]
        except (TypeError, ValueError):
            prof[row["key"]] = row["value"]
    return prof


def set_profile(con, values):
    con.executemany("INSERT OR REPLACE INTO profile(key,value) VALUES(?,?)",
                    [(k, str(v)) for k, v in values.items()])
    con.commit()


# ── 計算 ───────────────────────────────────────────────────────────────────

def bmi(weight, height_cm):
    return weight / (height_cm / 100.0) ** 2


def bmi_label(v):
    """日本肥満学会の判定基準。"""
    if v < 18.5:
        return "低体重"
    if v < 25:
        return "普通体重"
    if v < 30:
        return "肥満(1度)"
    if v < 35:
        return "肥満(2度)"
    if v < 40:
        return "肥満(3度)"
    return "肥満(4度)"


def bmr(weight, height_cm, age, sex):
    """基礎代謝量(Mifflin-St Jeor式)。"""
    base = 10 * weight + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "male" else base - 161


def bmr_katch(lean_kg):
    """除脂肪体重から基礎代謝を出す(Katch-McArdle式)。

    体組成が分かっているときはこちらのほうが実測に近い。ただし家庭用の体組成計は
    体脂肪が多いほど筋肉量を多めに出す傾向があるので、鵜呑みにはしない。
    """
    return 370 + 21.6 * lean_kg


def body_comp(prof, weight, body_fat=None, muscle_kg=None):
    """体脂肪率または筋肉量から、除脂肪体重と体脂肪量を出す。

    体脂肪率が分かっていればそれが一番正確。筋肉量しか分からない場合は
    「体重 = 筋肉量 + 体脂肪量 + 骨量」とみなし、骨量を体重比で概算する。
    """
    if body_fat:
        fat_kg = weight * body_fat / 100.0
        lean = weight - fat_kg
    elif muscle_kg:
        lean = muscle_kg + weight * prof.get("bone_ratio", 0.035)
        fat_kg = weight - lean
    else:
        return None
    if lean <= 0 or fat_kg < 0:
        return None
    return {"lean": round(lean, 1), "fat_kg": round(fat_kg, 1),
            "body_fat": round(fat_kg / weight * 100, 1),
            "muscle_kg": round(muscle_kg, 1) if muscle_kg else None}


def latest_comp(con, prof, weight):
    """直近で記録された体組成。体脂肪率を優先する。"""
    row = con.execute(
        "SELECT date, weight, body_fat, muscle_kg FROM days"
        " WHERE body_fat IS NOT NULL OR muscle_kg IS NOT NULL"
        " ORDER BY date DESC LIMIT 1").fetchone()
    if not row:
        return None
    c = body_comp(prof, row["weight"] or weight, row["body_fat"], row["muscle_kg"])
    if c:
        c["date"] = row["date"]
    return c


def targets(prof, weight, comp=None):
    """今の体重における1日の目標値をまとめて返す。"""
    h, age, sex = prof["height"], prof["age"], prof["sex"]
    b = bmr(weight, h, age, sex)
    if comp and prof.get("bmr_formula") == "katch":
        b = bmr_katch(comp["lean"])
    pal = ACTIVITY.get(prof["activity"], ACTIVITY["low"])[0]
    tdee = b * pal

    rate = PACE.get(prof["pace"], PACE["standard"])[0]
    # 希望ペースから必要な赤字を出し、安全弁で抑える
    want = weight * rate * KCAL_PER_KG_FAT / 7.0
    deficit = min(want, tdee * MAX_DEFICIT_RATIO)

    floor = max(b, KCAL_FLOOR.get(sex, 1500))
    kcal = tdee - deficit
    if kcal < floor:
        kcal = floor          # 基礎代謝を下回る食事はさせない
    if weight <= prof["goal_weight"]:
        kcal = tdee           # 目標到達後は維持カロリー
    kcal = round(kcal / 10) * 10
    actual_deficit = max(tdee - kcal, 0)

    # たんぱく質は減量中の筋肉の減りを抑えるために多めに取る。除脂肪体重が
    # 分かっていれば「除脂肪体重 × 1.6g」、分からなければ「目標体重 × 1.5g」。
    if comp:
        protein = max(round(comp["lean"] * 1.6), 90)
    else:
        protein = max(round(prof["goal_weight"] * 1.5), 90)
    fat = round(kcal * 0.25 / 9)                  # 脂質は総カロリーの25%
    carb = round((kcal - protein * 4 - fat * 9) / 4)
    return {
        "bmr": round(b),
        "bmr_formula": "katch" if (comp and prof.get("bmr_formula") == "katch") else "mifflin",
        "bmr_mifflin": round(bmr(weight, h, age, sex)),
        "bmr_katch": round(bmr_katch(comp["lean"])) if comp else None,
        "pal": pal,
        "tdee": round(tdee),
        "kcal": int(kcal),
        "deficit": round(actual_deficit),
        "protein": int(protein),
        "fat": int(fat),
        "carb": int(max(carb, 0)),
        "salt": prof["salt_target"],
        "fiber": 20,
        "weekly_loss": round(actual_deficit * 7 / KCAL_PER_KG_FAT, 2),
    }


def project(prof, weight, comp=None):
    """目標体重に着く時期を、週ごとに代謝を再計算しながら見積もる。

    体重が落ちると基礎代謝も落ちて痩せる速度は鈍る。単純な割り算だと
    実態より早い予定が出てしまうので、1週ずつ回して積み上げる。
    """
    goal = prof["goal_weight"]
    w = weight
    curve = [{"week": 0, "weight": round(w, 1)}]
    weeks = 0
    while w > goal and weeks < 200:
        c = dict(comp) if comp else None
        if c:
            # 理想は除脂肪体重を保ったまま脂肪だけ減ること。その前提で代謝を出す
            c = {"lean": comp["lean"], "fat_kg": max(w - comp["lean"], 0),
                 "body_fat": max(w - comp["lean"], 0) / w * 100, "muscle_kg": c.get("muscle_kg")}
        t = targets(prof, w, c)
        loss = t["deficit"] * 7 / KCAL_PER_KG_FAT
        if loss <= 0.02:
            break
        w = max(goal, w - loss)
        weeks += 1
        if weeks % 4 == 0 or w <= goal:
            curve.append({"week": weeks, "weight": round(w, 1)})
    reached = w <= goal + 0.05
    return {
        "weeks": weeks if reached else None,
        "months": round(weeks / 4.345, 1) if reached else None,
        "goal_date": (date.today() + timedelta(weeks=weeks)).isoformat() if reached else None,
        "curve": curve,
        "note": "毎日きっちり守れた場合の理想値。実際はこの1.2〜1.5倍かかるのが普通。",
    }


# ── 集計 ───────────────────────────────────────────────────────────────────

def day_intake(con, d):
    row = con.execute(
        "SELECT COALESCE(SUM(kcal),0) k, COALESCE(SUM(p),0) p, COALESCE(SUM(f),0) f,"
        " COALESCE(SUM(c),0) c, COALESCE(SUM(salt),0) s, COUNT(*) n"
        " FROM meals WHERE date=?", (d,)).fetchone()
    return {"kcal": round(row["k"]), "protein": round(row["p"], 1), "fat": round(row["f"], 1),
            "carb": round(row["c"], 1), "salt": round(row["s"], 1), "items": row["n"]}


def recent_weights(con, days=90):
    since = (date.today() - timedelta(days=days)).isoformat()
    return [(r["date"], r["weight"]) for r in con.execute(
        "SELECT date, weight FROM days WHERE weight IS NOT NULL AND date>=?"
        " ORDER BY date", (since,))]


def current_weight(con, prof):
    row = con.execute("SELECT weight FROM days WHERE weight IS NOT NULL"
                      " ORDER BY date DESC LIMIT 1").fetchone()
    return row["weight"] if row else prof["start_weight"]


def moving_average(series, window=7):
    """(日付, 値) の列に移動平均を付ける。体重は日々1〜2kg揺れるので生値では判断しない。"""
    out = []
    for i, (d, v) in enumerate(series):
        chunk = [x[1] for x in series[max(0, i - window + 1): i + 1]]
        out.append({"date": d, "value": v, "avg": round(sum(chunk) / len(chunk), 2)})
    return out


def weight_trend(con):
    """直近の体重変化を、移動平均と回帰直線の両方で見る。"""
    series = recent_weights(con, 120)
    if len(series) < 2:
        return {"points": moving_average(series), "days": len(series),
                "rate_week": None, "stalled": False}
    pts = moving_average(series)

    # 直近14日を日付の通し番号に対して直線あてはめ → 1日あたりの傾き
    base = date.fromisoformat(series[0][0])
    recent = [(d, v) for d, v in series
              if (date.today() - date.fromisoformat(d)).days <= 14]
    rate_week = None
    if len(recent) >= 4:
        xs = [(date.fromisoformat(d) - base).days for d, _ in recent]
        ys = [v for _, v in recent]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            rate_week = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den * 7, 2)

    span = (date.fromisoformat(series[-1][0]) - date.fromisoformat(series[0][0])).days
    stalled = (rate_week is not None and rate_week > -0.1 and span >= 21 and len(recent) >= 7)
    return {
        "points": pts, "days": len(series), "span_days": span,
        "rate_week": rate_week, "stalled": stalled,
        "total_change": round(series[-1][1] - series[0][1], 1),
    }


def bp_category(sys_v, dia_v):
    """家庭血圧の分類(高血圧治療ガイドライン2019 の家庭血圧基準)。"""
    if sys_v >= 160 or dia_v >= 100:
        return ("III度高血圧", "alert")
    if sys_v >= 145 or dia_v >= 90:
        return ("II度高血圧", "alert")
    if sys_v >= 135 or dia_v >= 85:
        return ("I度高血圧", "warn")
    if sys_v >= 125 or dia_v >= 75:
        return ("高値血圧", "warn")
    if sys_v >= 115:
        return ("正常高値血圧", "info")
    return ("正常血圧", "good")


def bp_summary(con, days=7):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = con.execute("SELECT * FROM bp WHERE date>=? ORDER BY date, slot", (since,)).fetchall()
    if not rows:
        return {"count": 0, "days": days}
    sys_v = [r["systolic"] for r in rows]
    dia_v = [r["diastolic"] for r in rows]
    avg_s, avg_d = round(statistics.mean(sys_v)), round(statistics.mean(dia_v))
    cat, level = bp_category(avg_s, avg_d)
    return {
        "count": len(rows), "days": days,
        "avg_systolic": avg_s, "avg_diastolic": avg_d,
        "max_systolic": max(sys_v), "max_diastolic": max(dia_v),
        "category": cat, "level": level,
        "measured_days": len({r["date"] for r in rows}),
    }


def bp_series(con, days=90):
    """1日1点(その日の平均)にまとめたグラフ用の列。"""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute(
        "SELECT date, ROUND(AVG(systolic)) s, ROUND(AVG(diastolic)) d FROM bp"
        " WHERE date>=? GROUP BY date ORDER BY date", (since,)).fetchall()
    return [{"date": r["date"], "systolic": int(r["s"]), "diastolic": int(r["d"])} for r in rows]


def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def sleep_minutes(bedtime, waketime):
    """就寝〜起床の分数。日付をまたぐ前提で計算する。"""
    if not bedtime or not waketime:
        return None
    b, w = _to_minutes(bedtime), _to_minutes(waketime)
    return (w - b) % (24 * 60)


def sleep_summary(con, days=14):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = con.execute("SELECT * FROM sleep WHERE date>=? ORDER BY date", (since,)).fetchall()
    if not rows:
        return {"count": 0, "days": days}
    mins = [r["minutes"] for r in rows if r["minutes"]]
    wakes = [_to_minutes(r["waketime"]) for r in rows if r["waketime"]]
    quality = [r["quality"] for r in rows if r["quality"]]
    sleepy = [r["sleepiness"] for r in rows if r["sleepiness"]]
    awk = [r["awakenings"] for r in rows if r["awakenings"] is not None]
    return {
        "count": len(rows), "days": days,
        "avg_minutes": round(statistics.mean(mins)) if mins else None,
        "min_minutes": min(mins) if mins else None,
        # 起床時刻のばらつき。大きいほど体内時計が毎日ずれている
        "wake_sd_min": round(statistics.pstdev(wakes)) if len(wakes) >= 3 else None,
        "avg_quality": round(statistics.mean(quality), 1) if quality else None,
        "avg_sleepiness": round(statistics.mean(sleepy), 1) if sleepy else None,
        "avg_awakenings": round(statistics.mean(awk), 1) if awk else None,
        "series": [{"date": r["date"], "minutes": r["minutes"], "quality": r["quality"],
                    "bedtime": r["bedtime"], "waketime": r["waketime"]} for r in rows],
    }


def avg_intake(con, days=7):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = con.execute(
        "SELECT date, SUM(kcal) k, SUM(p) p, SUM(salt) s FROM meals"
        " WHERE date>=? GROUP BY date", (since,)).fetchall()
    if not rows:
        return {"logged_days": 0}
    return {
        "logged_days": len(rows),
        "kcal": round(statistics.mean([r["k"] for r in rows])),
        "protein": round(statistics.mean([r["p"] for r in rows])),
        "salt": round(statistics.mean([r["s"] for r in rows]), 1),
    }


# ── 睡眠時無呼吸(SAS)のスクリーニング ────────────────────────────────────
#
# BMI30以上 + 高血圧 の組み合わせは睡眠時無呼吸の頻度が高い。SASがあると
# 夜間に何度も低酸素と覚醒が起きるため「寝ても疲れが取れない」だけでなく、
# 血圧が薬でも下がりにくくなる。逆に治療すると睡眠と血圧が同時に改善する
# ことがあるので、このツールで最優先に拾うべき項目として別立てにしている。
# 判定は STOP-BANG 質問票に準じた簡易版(あくまで受診の目安で、診断ではない)。

def sas_risk(con, prof, weight, bp7, sleep14):
    hits, items = [], []

    def add(ok, label):
        items.append({"label": label, "hit": bool(ok)})
        if ok:
            hits.append(label)

    add(prof.get("snoring"), "大きないびきを指摘される")
    tired = (sleep14.get("avg_sleepiness") or 0) >= 4
    add(tired, "日中の強い眠気・だるさ")
    add(prof.get("observed_apnea"), "睡眠中に呼吸が止まると言われた")
    high_bp = bool(prof.get("on_bp_medication")) or \
        (bp7.get("avg_systolic") or 0) >= 135 or (bp7.get("avg_diastolic") or 0) >= 85
    add(high_bp, "血圧が高い / 降圧薬を服用中")
    add(bmi(weight, prof["height"]) > 35, "BMI 35超")
    add(prof["age"] > 50, "50歳超")
    add((prof.get("neck_cm") or 0) > 40, "首まわり40cm超")
    add(prof["sex"] == "male", "男性")

    score = len(hits)
    if score >= 5:
        level, text = "alert", "高リスク"
    elif score >= 3:
        level, text = "warn", "中リスク"
    else:
        level, text = "info", "低リスク"
    return {"score": score, "max": len(items), "level": level, "text": text,
            "hits": hits, "items": items}


# ── 筋トレの種目 ───────────────────────────────────────────────────────────
#
# size は動かす筋肉の大きさ。減量中に筋肉を守るなら、消費カロリーもホルモン応答も
# 大きい big(脚・背中・胸)を先にやるのが効率がいい。腕や腹だけをいくらやっても、
# その部位の脂肪が落ちるわけではない(部分やせは起きない)ので補助の位置づけ。

EXERCISES = [
    {"name": "レッグプレス",           "muscle": "脚",   "size": "big"},
    {"name": "スクワット(スミス)",      "muscle": "脚",   "size": "big"},
    {"name": "レッグカール",           "muscle": "もも裏", "size": "big"},
    {"name": "レッグエクステンション",   "muscle": "もも前", "size": "big"},
    {"name": "ラットプルダウン",        "muscle": "背中",  "size": "big"},
    {"name": "シーテッドロー",          "muscle": "背中",  "size": "big"},
    {"name": "デッドリフト",           "muscle": "背中・脚", "size": "big"},
    {"name": "チェストプレス",          "muscle": "胸",   "size": "big"},
    {"name": "腕立て伏せ",             "muscle": "胸",   "size": "big"},
    {"name": "懸垂",                  "muscle": "背中",  "size": "big"},
    {"name": "ベンチプレス",           "muscle": "胸",   "size": "big"},
    {"name": "ショルダープレス",        "muscle": "肩",   "size": "big"},
    {"name": "サイドレイズ",           "muscle": "肩",   "size": "small"},
    {"name": "トライセプスプレスダウン", "muscle": "三頭筋", "size": "small"},
    {"name": "アームカール",           "muscle": "二頭筋", "size": "small"},
    {"name": "アブドミナルクランチ",     "muscle": "腹",   "size": "small"},
    {"name": "腹筋(自重)",            "muscle": "腹",   "size": "small"},
    {"name": "プランク",              "muscle": "体幹",  "size": "small"},
    {"name": "カーフレイズ",           "muscle": "ふくらはぎ", "size": "small"},
    {"name": "トレッドミル(早歩き)",    "muscle": "有酸素", "size": "cardio"},
    {"name": "バイク",                "muscle": "有酸素", "size": "cardio"},
    {"name": "クロストレーナー",        "muscle": "有酸素", "size": "cardio"},
]

EX_BY_NAME = {e["name"]: e for e in EXERCISES}


def workout_summary(con, days=7):
    """直近の筋トレ内容。大筋群をやれているかを見る。"""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = con.execute("SELECT * FROM workouts WHERE date>=? ORDER BY date", (since,)).fetchall()
    reps = [r["reps"] for r in rows if r["size"] != "cardio" and r["reps"]]
    big = {r["name"] for r in rows if r["size"] == "big"}
    small = {r["name"] for r in rows if r["size"] == "small"}
    cardio = [r for r in rows if r["size"] == "cardio"]
    return {
        "count": len(rows), "days": days,
        "session_days": len({r["date"] for r in rows}),
        "big": sorted(big), "small": sorted(small),
        "cardio_min": sum(r["minutes"] or 0 for r in cardio),
        "muscles": sorted({r["muscle"] for r in rows if r["size"] != "cardio"}),
        "high_rep": bool(reps) and sum(1 for r in reps if r >= 25) > len(reps) / 2,
        "avg_reps": round(sum(reps) / len(reps)) if reps else None,
    }


# ── 睡眠の習慣チェックリスト ───────────────────────────────────────────────
# 不眠症の認知行動療法(CBT-I)と睡眠衛生指導でよく使われる項目を、
# その日やったかどうかで答えられる形にしたもの。

HABITS = [
    {"key": "wake_fixed",  "label": "起床時刻を目標どおりにした(±30分)",
     "why": "体内時計は起床時刻で決まる。就寝時刻より先にこちらを固定する"},
    {"key": "morning_light", "label": "起きて1時間以内に日光を15分以上浴びた",
     "why": "朝の光を浴びた約14〜16時間後に眠気が来る。夜の入眠が前倒しになる"},
    {"key": "no_caffeine_pm", "label": "カフェインは14時まで",
     "why": "カフェインは半分抜けるのに5〜6時間かかる。夕方の1杯が深い睡眠を削る"},
    {"key": "no_alcohol", "label": "寝る前の飲酒をしなかった",
     "why": "寝つきは良くなるが後半の睡眠が浅くなり、夜中に目が覚める。血圧も上げる"},
    {"key": "dinner_early", "label": "夕食を就寝3時間前までに終えた",
     "why": "消化中は深部体温が下がりにくく、眠りが浅くなる"},
    {"key": "no_screen", "label": "就寝1時間前はスマホ・PCを見なかった",
     "why": "光と情報刺激で覚醒度が上がる。寝室にスマホを持ち込まないのが一番早い"},
    {"key": "bath", "label": "就寝90分前に入浴した",
     "why": "一度上げた深部体温が下がるタイミングで眠気が来る"},
    {"key": "walk", "label": "日中に20分以上歩いた",
     "why": "日中の活動量は深い睡眠の量を増やす。減量にも血圧にも効く"},
    {"key": "no_bed_awake", "label": "眠れないとき15分以上ふとんで粘らなかった",
     "why": "「ふとん＝眠れない場所」という学習を防ぐ。眠くなるまで別室で過ごす"},
]


def get_habits(con, d):
    row = con.execute("SELECT done FROM habits WHERE date=?", (d,)).fetchone()
    done = set(json.loads(row["done"])) if row else set()
    return [{**h, "done": h["key"] in done} for h in HABITS]


# ── コーチング ─────────────────────────────────────────────────────────────

def _msg(level, title, body, tag=""):
    return {"level": level, "title": title, "body": body, "tag": tag}


def build_advice(con, prof, d, weight, t, intake, trend, bp7, sleep14, sas, day_row,
                 comp=None, wk=None):
    """その日の状況から、出すべき指示を組み立てる。上から重要な順。"""
    msgs = []
    log_days = trend["days"]

    # 1) 受診すべき血圧かどうか。他のどのアドバイスより先に出す
    today_bp = con.execute(
        "SELECT MAX(systolic) s, MAX(diastolic) dd FROM bp WHERE date=?", (d,)).fetchone()
    ts, td = today_bp["s"], today_bp["dd"]
    if ts and (ts >= 180 or td >= 110):
        msgs.append(_msg("alert", "すぐに医療機関へ",
                         "今日の血圧が %d/%d でした。数分安静にしてから測り直しても同じくらい高い場合、"
                         "自己判断で様子を見ずに受診してください。頭痛・吐き気・胸の痛み・"
                         "ろれつが回らないなどがあれば救急を検討してください。" % (ts, td), "血圧"))
    elif ts and (ts >= 160 or td >= 100):
        msgs.append(_msg("alert", "早めに受診の予約を",
                         "今日の血圧が %d/%d です。この水準が続くなら数日以内に医療機関へ。"
                         "受診時はこのアプリの記録(朝晩の値)を見せると話が早いです。" % (ts, td), "血圧"))

    if bp7.get("count"):
        cat, level = bp7["category"], bp7["level"]
        line = "直近7日の平均は %d/%d(%s)。" % (bp7["avg_systolic"], bp7["avg_diastolic"], cat)
        if level in ("alert", "warn"):
            body = line + "家庭血圧は135/85未満が目標です。いま効く手は3つ——" \
                "①減塩(1日6g未満。今日は%.1fg)②減量(体重1kg減で上の血圧が約1mmHg下がる目安)" \
                "③夜の酒を減らす。" % intake["salt"]
            if not prof.get("on_bp_medication"):
                body += "2週間続けても平均が135/85を超えるなら受診してください。"
            msgs.append(_msg("warn" if level == "warn" else "alert", "血圧: " + cat, body, "血圧"))
        else:
            msgs.append(_msg("good", "血圧: " + cat, line + "この調子で記録を続けましょう。", "血圧"))
    elif log_days >= 1:
        msgs.append(_msg("info", "血圧を測りましょう",
                         "朝(起床後1時間以内・排尿後・朝食と薬の前)と晩(就寝前)に、"
                         "座って1〜2分休んでから測ります。1回の値ではなく平均で判断するので、"
                         "まず1週間ためるのが目標です。", "血圧"))

    # 2) 睡眠時無呼吸。見つかれば睡眠と血圧の両方が一気に動く可能性がある
    if sas["score"] >= 3:
        msgs.append(_msg("alert" if sas["score"] >= 5 else "warn",
                         "睡眠時無呼吸の可能性(%s・%d/%d項目)" % (sas["text"], sas["score"], sas["max"]),
                         "当てはまる項目: " + "、".join(sas["hits"]) +
                         "。睡眠時無呼吸があると、どれだけ寝ても疲れが取れず、血圧も下がりにくく"
                         "なります。逆に治療すると睡眠も血圧も一気に改善することがあります。"
                         "呼吸器内科・睡眠外来・耳鼻咽喉科で簡易検査(自宅で一晩)ができます。"
                         "ダイエットより先に、ここを一度調べる価値があります。", "睡眠"))

    # 3) 最初の2週間は数字を追うより、記録を続けること自体が目標
    if log_days < 14:
        msgs.append(_msg("info", "まずは2週間、記録を続ける(%d/14日)" % log_days,
                         "この時期にカロリーを厳しくしすぎると続きません。やることは3つだけ——"
                         "①毎朝おなじ条件で体重を測る(起床後トイレのあと、下着)"
                         "②食べたものを全部入れる(正確さより漏れのなさ)"
                         "③起床時刻を%sに固定する。数字の判断は2週間分たまってからです。"
                         % prof["wake_target"], "全体"))

    # 4) 今日の食事
    rest = t["kcal"] - intake["kcal"]
    if intake["items"] == 0:
        msgs.append(_msg("info", "今日の食事がまだ未記録",
                         "目標は %d kcal / たんぱく質 %dg / 食塩 %.1fg未満。"
                         "食べる前ではなく食べた直後に入れるのがコツです。"
                         % (t["kcal"], t["protein"], t["salt"]), "食事"))
    else:
        if rest >= 200:
            msgs.append(_msg("good", "残り %d kcal" % rest,
                             "たんぱく質はあと%dg。肉・魚・卵・豆腐・ヨーグルトで埋めると"
                             "腹持ちが良く、筋肉の減りも抑えられます。"
                             % max(t["protein"] - intake["protein"], 0), "食事"))
        elif rest >= -100:
            msgs.append(_msg("good", "今日はほぼ目標どおり(%+d kcal)" % -rest,
                             "この幅で収まっていれば十分です。1日の多少のブレは問題になりません。", "食事"))
        else:
            msgs.append(_msg("warn", "目標を %d kcal 超えました" % -rest,
                             "取り返そうとして翌日を極端に減らすと、反動でまた増えます。"
                             "明日はいつもどおりに戻すだけでOK。代わりに今日は20分多く歩きましょう。", "食事"))

        # カロリーの「量」ではなく「中身」を見る。たんぱく質の密度が低いと、
        # 総カロリーが目標内でも筋肉が落ちる食べ方になっている
        if intake["kcal"] >= 500:
            density = intake["protein"] / intake["kcal"] * 100      # 100kcalあたりg
            want = t["protein"] / t["kcal"] * 100
            if density < want * 0.6:
                msgs.append(_msg("warn", "中身が炭水化物に寄っています",
                                 "ここまで %dkcal 食べてたんぱく質は %.0fg。"
                                 "100kcalあたり %.1fg で、必要な密度(%.1fg)の半分以下です。"
                                 "カロリーは残っていても、この食べ方を続けると"
                                 "減る体重の中身が筋肉に寄ります。残りの食事は"
                                 "「主食を足す」より「肉・魚・卵・豆腐・ヨーグルトを足す」"
                                 "を優先してください。"
                                 % (intake["kcal"], intake["protein"], density, want), "食事"))

        if intake["protein"] < t["protein"] * 0.7 and intake["kcal"] > t["kcal"] * 0.6:
            msgs.append(_msg("warn", "たんぱく質が足りていません(%.0f/%dg)"
                             % (intake["protein"], t["protein"]),
                             "減量中にたんぱく質が少ないと、減る体重の中身が脂肪でなく筋肉に"
                             "寄ります。ゆで卵1個で6g、納豆1パックで7g、サラダチキンで24g、"
                             "ギリシャヨーグルトで10g。", "食事"))

        if intake["salt"] > t["salt"]:
            msgs.append(_msg("warn", "食塩が %.1fg(目標 %.1fg未満)" % (intake["salt"], t["salt"]),
                             "効く順に——①麺類の汁を残す(これだけで2〜3g減る)"
                             "②醤油・ソースは「かける」でなく小皿で「つける」"
                             "③味噌汁は1日1杯まで。酢・レモン・こしょう・だし・薬味で"
                             "味を補うと薄味でも物足りなさが出にくいです。", "血圧"))
        elif intake["items"] >= 3 and intake["salt"] <= t["salt"]:
            msgs.append(_msg("good", "食塩 %.1fg — 目標内です" % intake["salt"],
                             "減塩は血圧に直接効きます(1日1g減らすと上の血圧が約1mmHg下がる目安)。", "血圧"))

    # 5) 体重の動き
    if trend["rate_week"] is not None:
        r = trend["rate_week"]
        target_rate = -t["weekly_loss"]
        if trend["stalled"]:
            msgs.append(_msg("warn", "体重が2〜3週間止まっています",
                             "停滞のときに見る順番は決まっています——"
                             "①記録漏れ(油・ドレッシング・飲み物・つまみ食いは入っていますか)"
                             "②体重が落ちた分、目標カロリーも下がっているか(設定を今の体重で更新)"
                             "③塩分と便通による水分の増減(生理・筋トレ後は数日で戻ります)"
                             "④活動量。まずは①を3日ぶん見直すのが一番当たります。", "体重"))
        elif r > 0.2:
            msgs.append(_msg("warn", "直近2週間で週 %+.2fkg" % r,
                             "増えています。食事記録の漏れがないか、塩分が多くて水分を"
                             "溜めていないかを確認しましょう。1〜2日の上下は無視して構いません。", "体重"))
        elif r < target_rate * 1.8 and r < -0.9:
            msgs.append(_msg("warn", "減り方が速すぎます(週 %+.2fkg)" % r,
                             "週1%を超えるペースは筋肉が落ちやすく、リバウンドしやすくなります。"
                             "食事を100〜200kcal増やすか、ペース設定を「ゆっくり」に変えましょう。", "体重"))
        else:
            msgs.append(_msg("good", "直近2週間で週 %+.2fkg" % r,
                             "目標ペース(週 %.2fkg減)に対して良い線です。開始からの合計は %+.1fkg。"
                             % (t["weekly_loss"], trend["total_change"]), "体重"))

    # 6) 睡眠
    if sleep14.get("count"):
        avg = sleep14.get("avg_minutes")
        if avg and avg < prof["sleep_target"] - 45:
            msgs.append(_msg("warn", "睡眠が平均 %d時間%d分 — 足りていません" % (avg // 60, avg % 60),
                             "睡眠不足は食欲ホルモン(グレリン↑・レプチン↓)を動かして翌日の"
                             "食欲を増やします。減量の足を直接引っ張るので、食事より先に"
                             "ここを直す価値があります。就寝を早めるより、まず起床時刻の固定から。", "睡眠"))
        sd = sleep14.get("wake_sd_min")
        if sd is not None and sd > 60:
            msgs.append(_msg("warn", "起床時刻のばらつきが±%d分" % sd,
                             "毎日の起床時刻が1時間以上ずれていると、体内時計が時差ボケの状態に"
                             "なります。休日も平日との差を1時間以内に。眠いときは"
                             "「寝坊」ではなく「15時までに20分の昼寝」で返すのが正解です。", "睡眠"))
        elif sd is not None and sd <= 30:
            msgs.append(_msg("good", "起床時刻が安定しています(±%d分)" % sd,
                             "睡眠改善でいちばん効く土台ができています。", "睡眠"))
        if (sleep14.get("avg_awakenings") or 0) >= 2:
            msgs.append(_msg("info", "夜中に平均 %.1f回 目が覚めています" % sleep14["avg_awakenings"],
                             "寝る前の飲酒と、就寝2時間前以降の水分・カフェインをまず止めてみて"
                             "ください。いびきを指摘されているなら睡眠時無呼吸の検査も。", "睡眠"))
    else:
        msgs.append(_msg("info", "睡眠の記録をつけましょう",
                         "就寝・起床時刻と、朝の目覚めの感じ(1〜5)だけで十分です。"
                         "何が効いたのかは記録がないと分かりません。", "睡眠"))

    # 7) 筋トレ。減量中は「落とす体重の中身」を決めるのがここ
    wk = wk or {"count": 0}
    if wk.get("count"):
        if not wk["big"] and wk["small"]:
            msgs.append(_msg("warn", "大きい筋肉を先にやりましょう",
                             "直近7日でやったのは %s だけです。腕や腹は小さい筋肉なので、"
                             "いくらやってもその部位の脂肪は落ちません(部分やせは起きない)。"
                             "脚・背中・胸の3つは、使う筋肉の量が桁違いで、消費カロリーも"
                             "筋肉を守る効果も大きい。レッグプレス・ラットプルダウン・"
                             "チェストプレスの3種目を先に入れて、腕と腹はそのあと余力でやる、"
                             "の順番にしてください。" % "、".join(wk["small"]), "運動"))
        elif wk["big"]:
            msgs.append(_msg("good", "筋トレ %d日 / 大きい筋肉 %d種目"
                             % (wk["session_days"], len(wk["big"])),
                             "この順番で合っています。減量中の筋トレは「筋肉を増やす」ためでは"
                             "なく「落ちる体重の中身を脂肪に寄せる」ためのものなので、"
                             "重量が伸びなくても続ける価値があります。", "運動"))
        if wk.get("high_rep"):
            msgs.append(_msg("info", "回数が多め（平均 %d回）" % wk["avg_reps"],
                             "軽い重さで回数を稼ぐのは持久力寄りのやり方です。減量中に"
                             "筋肉を守るのが目的なら、10〜15回で「あと2回が限界」くらいの"
                             "重さのほうが時間あたりの効率は上。ただし血圧が高いうちは、"
                             "今の高回数・中重量のほうが安全なやり方でもあります。"
                             "血圧が135/85を切って落ち着いてきたら重さを上げていきましょう。", "運動"))

        if wk["cardio_min"] < 150 and (bp7.get("level") in ("warn", "alert")):
            msgs.append(_msg("info", "有酸素が週 %d分(目安150分)" % wk["cardio_min"],
                             "血圧に効くのは筋トレより有酸素です。筋トレのあとに"
                             "トレッドミルで早歩き20〜30分を足すのが、いま一番効率がいい形。", "運動"))
        if bp7.get("level") in ("warn", "alert") or prof.get("on_bp_medication"):
            msgs.append(_msg("warn", "血圧が高いときの筋トレの注意",
                             "重いものを持つとき息を止めて力むと(いきむと)、その瞬間に血圧が"
                             "大きく跳ね上がります。①息を止めない(力を入れるときに吐く)"
                             "②1セット10回以上できる重さにする(限界まで追い込まない)"
                             "③セット間は十分に休む。これを守れば筋トレは続けて問題ありません。", "運動"))

    # 8) 体組成
    if comp:
        msgs.append(_msg("good", "筋肉量 %skg / 体脂肪率 %.1f%%"
                         % (comp.get("muscle_kg") or "—", comp["body_fat"]),
                         "除脂肪体重が %.1fkg あります。これは大きな武器で、"
                         "基礎代謝が高く保たれているぶん脂肪を落としやすい状態です。"
                         "この先の目標は「%.1fkgの体脂肪を落として、除脂肪体重は守る」こと。"
                         "体重だけでなく体脂肪率も月1回は測ってください。"
                         % (comp["lean"], comp["fat_kg"]), "体重"))

    # 9) 歩数
    steps = (day_row["steps"] if day_row else None) or 0
    if steps and steps < prof["step_target"] * 0.6:
        msgs.append(_msg("info", "今日は %d歩(目標 %d歩)" % (steps, prof["step_target"]),
                         "早歩き30分は血圧を下げる効果がはっきりしている数少ない運動です。"
                         "一度にやらず10分×3回でも同じ効果が得られます。", "運動"))
    elif steps >= prof["step_target"]:
        msgs.append(_msg("good", "%d歩 — 目標達成" % steps,
                         "歩数は減量よりむしろ血圧と睡眠に効きます。", "運動"))

    # 10) 習慣チェックの未達
    habits = get_habits(con, d)
    undone = [h for h in habits if not h["done"]]
    if len(undone) >= 5 and log_days >= 3:
        pick = undone[0]
        msgs.append(_msg("info", "今夜の1つだけ: " + pick["label"], pick["why"], "睡眠"))

    order = {"alert": 0, "warn": 1, "good": 2, "info": 3}
    msgs.sort(key=lambda m: order.get(m["level"], 9))
    return msgs


def meal_plan(t):
    """目標カロリーを1日の中でどう割るかの目安。"""
    split = [("朝", 0.25), ("昼", 0.35), ("夕", 0.30), ("間食", 0.10)]
    return [{"slot": s, "kcal": round(t["kcal"] * r / 10) * 10,
             "protein": round(t["protein"] * r),
             "salt": round(t["salt"] * r, 1)} for s, r in split]


def dashboard(con, d=None):
    """画面とCLIの両方が使う、その日ぶんのデータ一式。"""
    d = d or date.today().isoformat()
    prof = get_profile(con)
    weight = current_weight(con, prof)
    comp = latest_comp(con, prof, weight)
    t = targets(prof, weight, comp)
    intake = day_intake(con, d)
    trend = weight_trend(con)
    bp7 = bp_summary(con, 7)
    sleep14 = sleep_summary(con, 14)
    sas = sas_risk(con, prof, weight, bp7, sleep14)
    day_row = con.execute("SELECT * FROM days WHERE date=?", (d,)).fetchone()

    b = bmi(weight, prof["height"])
    return {
        "date": d,
        "profile": prof,
        "activity_label": ACTIVITY.get(prof["activity"], ACTIVITY["low"])[1],
        "pace_label": PACE.get(prof["pace"], PACE["standard"])[1],
        "weight": weight,
        "bmi": round(b, 1),
        "bmi_label": bmi_label(b),
        "goal_bmi": round(bmi(prof["goal_weight"], prof["height"]), 1),
        "to_goal": round(weight - prof["goal_weight"], 1),
        "lost": round(prof["start_weight"] - weight, 1),
        "targets": t,
        "comp": comp,
        "projection": project(prof, weight, comp),
        "exercises": EXERCISES,
        "workouts": [dict(r) for r in con.execute(
            "SELECT * FROM workouts WHERE date=? ORDER BY id", (d,))],
        "workout7": workout_summary(con, 7),
        "intake": intake,
        "remaining": {"kcal": t["kcal"] - intake["kcal"],
                      "protein": round(t["protein"] - intake["protein"], 1),
                      "salt": round(t["salt"] - intake["salt"], 1)},
        "meal_plan": meal_plan(t),
        "trend": trend,
        "bp7": bp7,
        "bp_series": bp_series(con),
        "sleep": sleep14,
        "sas": sas,
        "habits": get_habits(con, d),
        "day": dict(day_row) if day_row else {},
        "meals": [dict(r) for r in con.execute(
            "SELECT * FROM meals WHERE date=? ORDER BY id", (d,))],
        "bp_today": [dict(r) for r in con.execute(
            "SELECT * FROM bp WHERE date=? ORDER BY id", (d,))],
        "sleep_today": dict(con.execute(
            "SELECT * FROM sleep WHERE date=?", (d,)).fetchone() or {}),
        "week": avg_intake(con, 7),
        "advice": [],
    }


def build(con, d=None):
    data = dashboard(con, d)
    data["advice"] = build_advice(
        con, data["profile"], data["date"], data["weight"], data["targets"],
        data["intake"], data["trend"], data["bp7"], data["sleep"], data["sas"],
        con.execute("SELECT * FROM days WHERE date=?", (data["date"],)).fetchone(),
        data["comp"], data["workout7"])
    return data


# ── テキストを1行投げて記録する ───────────────────────────────────────────
#
# 「朝 ご飯 納豆 味噌汁」「昼 ラーメン」「三頭筋 3x50 腹筋 2x50」「体重 98.4」
# のように書いた1行を解釈して、該当するテーブルに入れる。UIを開かずに
# その場で記録できるほうが続くので、入力の敷居をできるだけ下げる。

import re

SLOT_WORDS = {
    "朝": "朝", "朝食": "朝", "あさ": "朝", "morning": "朝",
    "昼": "昼", "昼食": "昼", "ひる": "昼", "ランチ": "昼", "lunch": "昼",
    "夕": "夕", "夕食": "夕", "夜": "夕", "晩": "夕", "夜食": "夕", "夕飯": "夕", "晩ご飯": "夕",
    "間食": "間食", "おやつ": "間食", "軽食": "間食",
}

# 略称・言い換え → 種目名
EX_ALIAS = {
    "三頭筋": "トライセプスプレスダウン", "三頭": "トライセプスプレスダウン",
    "トライセプス": "トライセプスプレスダウン", "プレスダウン": "トライセプスプレスダウン",
    "二頭筋": "アームカール", "二頭": "アームカール", "カール": "アームカール",
    "ダンベルカール": "アームカール", "バーベルカール": "アームカール",
    "ハンマーカール": "アームカール", "インクラインカール": "アームカール",
    "上腕二頭筋": "アームカール",
    "キックバック": "トライセプスプレスダウン", "フレンチプレス": "トライセプスプレスダウン",
    "上腕三頭筋": "トライセプスプレスダウン",
    "ダンベルプレス": "チェストプレス", "ダンベルフライ": "チェストプレス",
    "腕立て": "腕立て伏せ", "プッシュアップ": "腕立て伏せ",
    "チンニング": "懸垂", "ダンベルロー": "シーテッドロー",
    "シットアップ": "腹筋(自重)", "レッグレイズ": "腹筋(自重)", "アブローラー": "腹筋(自重)",
    "ダンベルショルダープレス": "ショルダープレス",
    "サイドレイズ": "サイドレイズ", "ランジ": "レッグプレス", "レッグランジ": "レッグプレス",
    "腹筋": "腹筋(自重)", "腹": "腹筋(自重)",
    "クランチ": "アブドミナルクランチ", "アブドミナル": "アブドミナルクランチ",
    "脚": "レッグプレス", "足": "レッグプレス", "レッグプレス": "レッグプレス",
    "スクワット": "スクワット(スミス)",
    "背中": "ラットプルダウン", "ラットプル": "ラットプルダウン",
    "ロー": "シーテッドロー", "ローイング": "シーテッドロー",
    "胸": "チェストプレス", "ベンチ": "ベンチプレス",
    "肩": "ショルダープレス", "レイズ": "サイドレイズ",
    "デッド": "デッドリフト",
    "エクステンション": "レッグエクステンション", "カーフ": "カーフレイズ",
    "有酸素": "トレッドミル(早歩き)", "ウォーキング": "トレッドミル(早歩き)",
    "歩き": "トレッドミル(早歩き)", "早歩き": "トレッドミル(早歩き)",
    "トレッドミル": "トレッドミル(早歩き)", "ランニング": "トレッドミル(早歩き)",
    "エアロバイク": "バイク", "チャリ": "バイク",
}


# 食品のよくある略称・言い換え
FOOD_ALIAS = {
    "ポテチ": "ポテトチップス 1袋", "ポテトチップス": "ポテトチップス 1袋",
    "たまご": "卵 1個", "玉子": "卵 1個", "タマゴ": "卵 1個",
    "とうふ": "木綿豆腐 半丁", "豆腐": "木綿豆腐 半丁",
    "コーヒー": "ブラックコーヒー", "珈琲": "ブラックコーヒー",
    "水": "お茶・水", "お茶": "お茶・水", "麦茶": "お茶・水", "緑茶": "お茶・水",
    "ヨーグルト": "ヨーグルト 無糖", "チーズ": "プロセスチーズ 1個",
    "ビール": "ビール 350ml", "ハイボール": "ハイボール 1杯",
    "焼酎": "焼酎 水割り1杯", "日本酒": "日本酒 1合", "ワイン": "ワイン グラス1杯",
    "鶏むね": "鶏むね肉 皮なし", "むね肉": "鶏むね肉 皮なし", "ささみ": "ささみ",
    "牛乳": "牛乳", "豆乳": "無調整豆乳", "納豆": "納豆 1パック(タレ込み)",
    "トマジュ": "トマトジュース 有塩",
    "プロテイン": "ホエイプロテイン 1杯", "ゴールドスタンダード": "ゴールドスタンダード 1杯",
    "ゴルスタ": "ゴールドスタンダード 1杯", "GS": "ゴールドスタンダード 1杯",
    "ホエイ": "ホエイプロテイン 1杯",
}


def _norm(t):
    return t.replace("　", " ").replace("×", "x").replace("X", "x").strip()


def find_food(con, token, allow_approx=True):
    """食品名のゆるい一致。完全一致 > 前方一致 > 部分一致 の順で、よく使う順に選ぶ。

    見つからないときは語尾を削りながら探す(「にんじんのおかず」→「にんじん」)。
    その場合は approx=1 を立てて、推定で拾ったことが分かるようにする。
    """
    token = (token or "").strip()
    if not token:
        return None
    token = FOOD_ALIAS.get(token, token)

    def look(sql, arg):
        return con.execute("SELECT * FROM foods WHERE " + sql + " ORDER BY used DESC, id",
                           (arg,)).fetchone()

    for sql, arg in (("name = ?", token),
                     ("name LIKE ?", token + "%"),
                     ("name LIKE ?", "%" + token + "%")):
        row = look(sql, arg)
        if row:
            return dict(row, approx=0)

    if allow_approx:
        for n in range(len(token) - 1, 1, -1):
            head = token[:n]
            row = look("name LIKE ?", head + "%") or (
                look("name LIKE ?", "%" + head + "%") if n >= 3 else None)
            if row:
                return dict(row, approx=1)
    return None


def parse_log(con, text, d=None):
    """1行のテキストを解釈して記録する。何をしたかのリストを返す。

    区切り文字に頼らず、体重・血圧・睡眠・歩数のような形の決まったものを先に
    抜き取ってから、残りを区分・種目・食品として読む。1行にいくつ混ざっていても
    拾えるようにするため。
    """
    d = d or date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    text = _norm(text)

    text, done = _extract_metrics(con, text, d, now)

    unknown = []
    slot = None
    for seg in re.split(r"[、,／/\n]+", text):
        # 「朝 … 昼 …」のように1行に区分が複数あっても切り替わるようにする
        groups, cur = [], []
        for t in seg.split():
            if t in SLOT_WORDS:
                if cur:
                    groups.append((slot, cur))
                    cur = []
                slot = SLOT_WORDS[t]
            else:
                cur.append(t)
        if cur:
            groups.append((slot, cur))

        for g_slot, toks in groups:
            hints = {t for t in toks if t in FOOD_HINTS}
            toks = [t for t in toks if t not in FOOD_HINTS]
            entries, rest = _scan_exercises(con, toks, d, now)
            done += entries
            done, unknown = _consume_foods(con, rest, g_slot or _slot_by_clock(), d, now,
                                           done, unknown, hints)

    con.commit()
    return {"done": done, "unknown": unknown, "date": d}


# 同じ料理でも食べ方で塩分が大きく変わるものは、書き添えられていれば拾う
FOOD_HINTS = {"汁残し": "汁を残す", "汁を残す": "汁を残す", "スープ残し": "汁を残す",
              "汁なし": "汁を残す"}


def _consume_foods(con, toks, slot, d, now, done, unknown, hints=None):
    """食品名は「鶏むね肉 皮なし」のように空白を含むので、長い並びから順に試す。"""
    i = 0
    last = None          # 直前に記録した食事のid。「2杯」のような後置の数量に使う
    while i < len(toks):
        m = re.match(r"^([0-9.]+)\s*(?:杯|個|枚|本|人前|袋|パック|切れ|串|皿)$", toks[i])
        if m and last:
            _scale_meal(con, last, float(m.group(1)))
            done[-1] = _meal_label(con, last, done[-1])
            i += 1
            continue
        hit = False
        for n in (3, 2, 1):
            if i + n > len(toks):
                continue
            chunk = list(toks[i:i + n])
            qty = 1.0
            m = re.match(r"^(.*?)x([0-9.]+)$", chunk[-1])
            if m and m.group(1):
                chunk[-1], qty = m.group(1), float(m.group(2))
            phrase = " ".join(chunk)
            if n > 1 and not find_food(con, phrase, allow_approx=False):
                continue
            ok, msg = _parse_food(con, phrase, slot, d, now, qty, hints,
                                  allow_approx=(n == 1))
            if ok or n == 1:
                (done if ok else unknown).append(msg)
                last = con.execute("SELECT MAX(id) m FROM meals").fetchone()["m"] if ok else None
                i += n
                hit = True
                break
        if not hit:
            i += 1
    return done, unknown


def _scale_meal(con, meal_id, qty):
    """すでに入れた食事の量を倍にする(「お茶漬け 2杯」の2杯ぶん)。"""
    r = con.execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone()
    if not r or not r["qty"]:
        return
    k = qty / r["qty"]
    con.execute("UPDATE meals SET qty=?, kcal=?, p=?, f=?, c=?, salt=? WHERE id=?",
                (qty, round(r["kcal"] * k, 1), round(r["p"] * k, 1), round(r["f"] * k, 1),
                 round(r["c"] * k, 1), round(r["salt"] * k, 2), meal_id))


def _meal_label(con, meal_id, fallback):
    r = con.execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone()
    if not r:
        return fallback
    mark = "≈ " if fallback.startswith("≈ ") else ""
    return "%s%s %s%s (%dkcal 塩%.1fg)" % (
        mark, r["slot"], r["name"], "" if r["qty"] == 1 else " x%g" % r["qty"],
        r["kcal"], r["salt"])


def _extract_metrics(con, text, d, now):
    """体重・体組成・血圧・睡眠・歩数を、書かれている位置に関係なく抜き取る。"""
    done = []

    def day_set(col, val, label):
        con.execute("INSERT OR IGNORE INTO days(date) VALUES(?)", (d,))
        con.execute("UPDATE days SET %s=?, updated_at=? WHERE date=?" % col, (val, now, d))
        done.append(label)

    def sub(pattern, fn):
        nonlocal text
        text = re.sub(pattern, fn, text)

    sub(r"体重\s*([0-9.]+)\s*(?:kg|キロ)?",
        lambda m: day_set("weight", float(m.group(1)), "体重 %.1fkg" % float(m.group(1))) or "")
    sub(r"体脂肪(?:率)?\s*([0-9.]+)\s*%?",
        lambda m: day_set("body_fat", float(m.group(1)), "体脂肪率 %.1f%%" % float(m.group(1))) or "")
    sub(r"筋肉(?:量)?\s*([0-9.]+)\s*(?:kg|キロ)?",
        lambda m: day_set("muscle_kg", float(m.group(1)), "筋肉量 %.1fkg" % float(m.group(1))) or "")

    def bp(m):
        sys_v, dia_v = int(m.group(1)), int(m.group(2))
        if not (60 <= sys_v <= 260 and 30 <= dia_v <= 160):
            return m.group(0)
        pulse = int(m.group(3)) if m.group(3) else None
        sl = "晩" if datetime.now().hour >= 15 else "朝"
        con.execute("INSERT INTO bp(date,slot,systolic,diastolic,pulse,created_at)"
                    " VALUES(?,?,?,?,?,?)", (d, sl, sys_v, dia_v, pulse, now))
        cat, _ = bp_category(sys_v, dia_v)
        done.append("血圧 %s %d/%d%s (%s)"
                    % (sl, sys_v, dia_v, " 脈%d" % pulse if pulse else "", cat))
        return ""

    # 「血圧 145 92」「血圧145/92 脈78」「145/92」のどれでも
    sub(r"血圧\s*(\d{2,3})\s*[/ ]\s*(\d{2,3})(?:\s*(?:脈拍?)?\s*(\d{2,3}))?", bp)
    sub(r"(?<![0-9x])(\d{2,3})\s*/\s*(\d{2,3})(?![0-9])(?:\s*(?:脈拍?)\s*(\d{2,3}))?", bp)

    def bp_half(m):
        v = int(m.group(1))
        if not (60 <= v <= 260):
            return m.group(0)
        done.append("⚠ 血圧 %d は上の値だけです。記録していません — "
                    "「血圧 %d 92」のように下の値も入れてください" % (v, v))
        return ""

    sub(r"血圧\s*(\d{2,3})(?![0-9/])", bp_half)

    def sleep(m):
        bed, wake = m.group(1), m.group(2)
        mins = sleep_minutes(bed, wake)
        con.execute(
            "INSERT INTO sleep(date,bedtime,waketime,minutes,updated_at) VALUES(?,?,?,?,?)"
            " ON CONFLICT(date) DO UPDATE SET bedtime=excluded.bedtime,"
            " waketime=excluded.waketime, minutes=excluded.minutes,"
            " updated_at=excluded.updated_at",
            (d, bed, wake, mins, now))
        done.append("睡眠 %s→%s (%d時間%02d分)" % (bed, wake, mins // 60, mins % 60))
        return ""

    sub(r"(?:睡眠\s*)?(\d{1,2}:\d{2})\s*[-〜~ー–]\s*(\d{1,2}:\d{2})", sleep)
    sub(r"(?:歩数\s*)?([0-9][0-9,]*)\s*歩",
        lambda m: day_set("steps", int(m.group(1).replace(",", "")),
                          "%s歩" % m.group(1)) or "")
    return text, done


# 数字だけの修飾語(3x50 / 50回 / 20分 / 40kg)。直前の種目にぶら下げる
_MOD = re.compile(r"^[0-9.]+(?:x[0-9.]+)?(?:回|分|kg|キロ|セット|km)?$")


def _scan_exercises(con, toks, d, now):
    """トークンの並びから種目を切り出す。1行に何種目あっても分けて記録する。"""
    entries, rest, cur = [], [], None

    def flush():
        nonlocal cur
        if cur:
            entries.append(_save_workout(con, cur["name"], cur["mods"], d, now))
            cur = None

    for t in toks:
        # 「ダンベルカール50回8キロ」のように数字がくっついていても、
        # 最初の数字の手前までを種目名とみなす
        m = re.match(r"^([^0-9]+?)[0-9].*$", t)
        key = m.group(1) if m else t
        key = re.sub(r"[x×\s]+$", "", key)
        name = key if key in EX_BY_NAME else EX_ALIAS.get(key)
        if name:
            flush()
            cur = {"name": name, "mods": [t]}
        elif cur and _MOD.match(t):
            cur["mods"].append(t)
        else:
            flush()
            rest.append(t)
    flush()
    return entries, rest


def _save_workout(con, name, mods, d, now):
    e = EX_BY_NAME[name]
    body = " ".join(mods)
    sets = reps = weight = minutes = None
    m = re.search(r"(\d+)\s*x\s*(\d+)", body)
    if m:
        sets, reps = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(\d+)\s*セット", body)
        if m:
            sets = int(m.group(1))
        m = re.search(r"(\d+)\s*回", body)
        if m:
            reps = int(m.group(1))
    m = re.search(r"(\d+)\s*分", body)
    if m:
        minutes = int(m.group(1))
    m = re.search(r"([0-9.]+)\s*(?:kg|キロ|キログラム)", body)
    if m:
        weight = float(m.group(1))
    con.execute("INSERT INTO workouts(date,name,muscle,size,sets,reps,weight,minutes,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (d, name, e["muscle"], e["size"], sets, reps, weight, minutes, now))
    detail = " ".join(x for x in [
        "%dx%d" % (sets, reps) if sets and reps else ("%d回" % reps if reps else ""),
        "%gkg" % weight if weight else "", "%d分" % minutes if minutes else ""] if x)
    tag = {"big": "大筋群", "small": "小筋群", "cardio": "有酸素"}[e["size"]]
    return "運動 %s %s[%s]" % (name, detail + " " if detail else "", tag)


def _slot_by_clock():
    h = datetime.now().hour
    return "朝" if h < 10 else "昼" if h < 15 else "夕" if h < 22 else "間食"


def _parse_food(con, tok, slot, d, now, qty=1.0, hints=None, allow_approx=True):
    """食品名(空白を含むこともある)を記録する。『700kcal』のような直接指定も受ける。"""
    m = re.match(r"^(.*?)([0-9]+)kcal$", tok)
    if m:
        con.execute("INSERT INTO meals(date,slot,name,qty,kcal,p,f,c,salt,created_at)"
                    " VALUES(?,?,?,1,?,0,0,0,0,?)",
                    (d, slot, m.group(1) or "手入力", float(m.group(2)), now))
        return (True, "%s %s %skcal" % (slot, m.group(1) or "手入力", m.group(2)))

    f = find_food(con, tok, allow_approx)
    if not f:
        return (False, tok)
    for h in (hints or ()):
        want = FOOD_HINTS[h]
        alt = con.execute(
            "SELECT * FROM foods WHERE name LIKE ? AND name LIKE ? ORDER BY id LIMIT 1",
            (tok + "%", "%" + want + "%")).fetchone()
        if alt:
            f = dict(alt, approx=0)
            break
    con.execute("INSERT INTO meals(date,slot,name,qty,kcal,p,f,c,salt,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (d, slot, f["name"], qty, round(f["kcal"] * qty, 1), round(f["p"] * qty, 1),
                 round(f["f"] * qty, 1), round(f["c"] * qty, 1), round(f["salt"] * qty, 2), now))
    con.execute("UPDATE foods SET used=used+1 WHERE id=?", (f["id"],))
    label = f["name"] + ("" if qty == 1 else " x%g" % qty)
    mark = "≈ " if f.get("approx") else ""
    return (True, "%s%s %s (%dkcal 塩%.1fg)"
            % (mark, slot, label, f["kcal"] * qty, f["salt"] * qty))


# ── ヘルスケアアプリ・活動量計からの取り込み ─────────────────────────────

# iPhoneから「ファイルに保存」したときに落ちる先。iCloud Driveに保存すると
# Macではこのパスに現れるので、毎回パスを打たなくて済むようにここを探す。
EXPORT_DIRS = [
    "~/Library/Mobile Documents/com~apple~CloudDocs",        # iCloud Drive
    "~/Library/Mobile Documents/com~apple~CloudDocs/Downloads",
    "~/Downloads", "~/Desktop", "~/Documents", ".",
]
EXPORT_NAMES = ("書き出したデータ.zip", "export.zip", "書き出したデータ.xml", "export.xml")


def find_export():
    """書き出しファイルを探して、いちばん新しいものを返す。"""
    found = []
    for d in EXPORT_DIRS:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        for n in EXPORT_NAMES:
            p = os.path.join(d, n)
            if os.path.exists(p):
                found.append((os.path.getmtime(p), p))
        # 「書き出したデータ 2.zip」のような連番も拾う
        try:
            for n in os.listdir(d):
                if re.match(r"^(書き出したデータ|export)( \d+)?\.(zip|xml)$", n):
                    p = os.path.join(d, n)
                    found.append((os.path.getmtime(p), p))
        except OSError:
            pass
    return max(found)[1] if found else None


def import_health(con, path, since=None, days_back=180):
    """書き出しファイルを読んでDBに入れる。同じものを二度入れないようにする。"""
    import healthimport

    since = since or (date.today() - timedelta(days=days_back)).isoformat()
    prof = get_profile(con)
    now = datetime.now().isoformat(timespec="seconds")
    n = defaultdict(int)

    def day_set(d, col, val):
        if d < since or val is None:
            return
        con.execute("INSERT OR IGNORE INTO days(date) VALUES(?)", (d,))
        cur = con.execute("SELECT %s v FROM days WHERE date=?" % col, (d,)).fetchone()["v"]
        if cur is not None and abs(float(cur) - float(val)) < 0.05:
            return                      # すでに同じ値なら触らない
        con.execute("UPDATE days SET %s=?, updated_at=? WHERE date=?" % col, (val, now, d))
        n[col] += 1

    if path.lower().endswith((".xml", ".zip")):
        data = healthimport.parse_apple_health(path)
        src = "iPhone ヘルスケア"

        for d, v in data["steps"].items():
            day_set(d, "steps", v)
        for d, v in data["weight"].items():
            day_set(d, "weight", round(v, 1))
        for d, v in data["fat"].items():
            day_set(d, "body_fat", v)
        # 筋肉量そのものは書き出しに無いので、除脂肪体重から骨量ぶんを引いて近似する
        for d, v in data["lean"].items():
            if d in data["weight"]:
                day_set(d, "muscle_kg", round(v - data["weight"][d] * prof.get("bone_ratio", 0.035), 1))

        for b in data["bp"]:
            if b["date"] < since:
                continue
            dup = con.execute(
                "SELECT 1 FROM bp WHERE date=? AND systolic=? AND diastolic=?",
                (b["date"], b["systolic"], b["diastolic"])).fetchone()
            if dup:
                continue
            con.execute("INSERT INTO bp(date,slot,systolic,diastolic,pulse,created_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (b["date"], b["slot"], b["systolic"], b["diastolic"], b["pulse"], now))
            n["血圧"] += 1

        for d, sl in data["sleep"].items():
            if d < since:
                continue
            cur = con.execute("SELECT bedtime, waketime, minutes FROM sleep WHERE date=?",
                              (d,)).fetchone()
            if cur and (cur["bedtime"], cur["waketime"], cur["minutes"]) == \
                    (sl["bedtime"], sl["waketime"], sl["minutes"]):
                continue                # すでに同じ内容なら数えない
            con.execute(
                "INSERT INTO sleep(date,bedtime,waketime,minutes,awakenings,updated_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET"
                " bedtime=excluded.bedtime, waketime=excluded.waketime,"
                " minutes=excluded.minutes,"
                " awakenings=COALESCE(sleep.awakenings, excluded.awakenings),"
                " updated_at=excluded.updated_at",
                (d, sl["bedtime"], sl["waketime"], sl["minutes"], sl["awakenings"], now))
            n["睡眠"] += 1

        for w in data["workouts"]:
            if w["date"] < since:
                continue
            dup = con.execute(
                "SELECT 1 FROM workouts WHERE date=? AND name=? AND minutes=?",
                (w["date"], w["name"], w["minutes"])).fetchone()
            if dup:
                continue
            con.execute("INSERT INTO workouts(date,name,muscle,size,minutes,created_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (w["date"], w["name"], "アプリ記録", w["size"], w["minutes"], now))
            n["運動"] += 1
    else:
        res = healthimport.parse_csv(path)
        src = "CSV (%s)" % "、".join(res["columns"])
        for r in res["rows"]:
            d = r["date"]
            if d < since:
                continue
            for col in ("weight", "body_fat", "muscle_kg", "steps"):
                if col in r:
                    day_set(d, col, round(r[col], 1) if col != "steps" else round(r[col]))
            if "systolic" in r and "diastolic" in r:
                dup = con.execute("SELECT 1 FROM bp WHERE date=? AND systolic=? AND diastolic=?",
                                  (d, round(r["systolic"]), round(r["diastolic"]))).fetchone()
                if not dup:
                    con.execute("INSERT INTO bp(date,slot,systolic,diastolic,pulse,created_at)"
                                " VALUES(?,?,?,?,?,?)",
                                (d, "朝", round(r["systolic"]), round(r["diastolic"]),
                                 round(r["pulse"]) if "pulse" in r else None, now))
                    n["血圧"] += 1
            if "minutes" in r and r["minutes"] >= 60:
                cur = con.execute("SELECT minutes FROM sleep WHERE date=?", (d,)).fetchone()
                if cur and cur["minutes"] == round(r["minutes"]):
                    continue
                con.execute("INSERT INTO sleep(date,minutes,updated_at) VALUES(?,?,?)"
                            " ON CONFLICT(date) DO UPDATE SET minutes=excluded.minutes,"
                            " updated_at=excluded.updated_at",
                            (d, round(r["minutes"]), now))
                n["睡眠"] += 1

    con.commit()
    label = {"steps": "歩数", "weight": "体重", "body_fat": "体脂肪率", "muscle_kg": "筋肉量"}
    return {"source": src, "since": since,
            "counts": {label.get(k, k): v for k, v in n.items() if v}}


# ── コマンドライン ─────────────────────────────────────────────────────────

def _print_today(con, d=None):
    data = build(con, d)
    t, i, r = data["targets"], data["intake"], data["remaining"]
    print("── %s ──" % data["date"])
    print("体重 %.1fkg  BMI %.1f (%s)  目標まで %.1fkg"
          % (data["weight"], data["bmi"], data["bmi_label"], data["to_goal"]))
    print("食事 %d / %d kcal   たんぱく質 %.0f / %dg   食塩 %.1f / %.1fg"
          % (i["kcal"], t["kcal"], i["protein"], t["protein"], i["salt"], t["salt"]))
    if data["bp7"].get("count"):
        b = data["bp7"]
        print("血圧 7日平均 %d/%d (%s)" % (b["avg_systolic"], b["avg_diastolic"], b["category"]))
    if data["sleep"].get("avg_minutes"):
        m = data["sleep"]["avg_minutes"]
        print("睡眠 14日平均 %d時間%02d分" % (m // 60, m % 60))
    print()
    mark = {"alert": "!!", "warn": "! ", "good": "o ", "info": "- "}
    for m in data["advice"]:
        print("%s %s" % (mark.get(m["level"], "  "), m["title"]))
        for line in _wrap(m["body"], 66):
            print("     " + line)
    print()
    print("残り %d kcal。詳しくは http://localhost:8771" % r["kcal"])


def _wrap(text, width):
    """日本語は空白で切れないので、文字数で折り返す。"""
    return [text[i:i + width] for i in range(0, len(text), width)] or [""]


def _print_plan(con):
    prof = get_profile(con)
    w = current_weight(con, prof)
    t, p = targets(prof, w), project(prof, w)
    print("体重 %.1fkg → 目標 %.1fkg (BMI %.1f → %.1f)"
          % (w, prof["goal_weight"], bmi(w, prof["height"]),
             bmi(prof["goal_weight"], prof["height"])))
    print("基礎代謝 %d kcal / 消費 %d kcal (×%.2f)" % (t["bmr"], t["tdee"], t["pal"]))
    print("目標摂取 %d kcal  P%dg F%dg C%dg  食塩 %.1fg未満"
          % (t["kcal"], t["protein"], t["fat"], t["carb"], t["salt"]))
    print("赤字 %d kcal/日 → 週 -%.2fkg" % (t["deficit"], t["weekly_loss"]))
    if p["weeks"]:
        print("到達見込み %s (%s ヶ月)  ※%s" % (p["goal_date"], p["months"], p["note"]))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "today"
    con = connect()
    try:
        if cmd == "today":
            _print_today(con, argv[2] if len(argv) > 2 else None)
        elif cmd == "plan":
            _print_plan(con)
        elif cmd == "weight" and len(argv) > 2:
            d = date.today().isoformat()
            con.execute("INSERT OR IGNORE INTO days(date) VALUES(?)", (d,))
            con.execute("UPDATE days SET weight=?, updated_at=? WHERE date=?",
                        (float(argv[2]), datetime.now().isoformat(timespec="seconds"), d))
            con.commit()
            _print_today(con)
        elif cmd == "log" and len(argv) > 2:
            r = parse_log(con, " ".join(argv[2:]))
            for x in r["done"]:
                print("  ✓ " + x)
            if r["unknown"]:
                print("  ? 分からなかった: " + "、".join(r["unknown"]))
                print("    → 『社食 700kcal』のようにカロリーを直接書くか、")
                print("      画面の「手入力／マイ食品に登録」から登録してください")
            print()
            _print_today(con)
        elif cmd == "import":
            since = argv[argv.index("--since") + 1] if "--since" in argv else None
            args = [a for a in argv[2:] if not a.startswith("--") and a != since]
            path = os.path.expanduser(args[0]) if args else find_export()
            if not path:
                print("書き出しファイルが見つかりません。iCloud Drive か ダウンロード に"
                      "「書き出したデータ.zip」を置くか、パスを指定してください:")
                print("  python3 coach.py import ~/Downloads/書き出したデータ.zip")
                return
            print("ファイル: %s (%.0f MB)" % (path, os.path.getsize(path) / 1e6))
            r = import_health(con, path, since)
            print("取り込み元: %s" % r["source"])
            print("対象期間: %s 以降" % r["since"])
            if r["counts"]:
                for k, v in r["counts"].items():
                    print("  ✓ %s %d件" % (k, v))
            else:
                print("  新しく取り込むものはありませんでした")
            print()
            _print_today(con)
        elif cmd == "bp" and len(argv) > 3:
            slot = argv[argv.index("--slot") + 1] if "--slot" in argv else "朝"
            con.execute("INSERT INTO bp(date,slot,systolic,diastolic,created_at)"
                        " VALUES(?,?,?,?,?)",
                        (date.today().isoformat(), slot, int(argv[2]), int(argv[3]),
                         datetime.now().isoformat(timespec="seconds")))
            con.commit()
            cat, _ = bp_category(int(argv[2]), int(argv[3]))
            print("記録しました: %s %s/%s (%s)" % (slot, argv[2], argv[3], cat))
        else:
            print(__doc__)
    finally:
        con.close()


if __name__ == "__main__":
    import sys
    try:
        main(sys.argv)
    except BrokenPipeError:
        # `coach.py today | head` のように途中で読み取りを止められた場合
        os._exit(0)
    except KeyboardInterrupt:
        os._exit(130)
