#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""健康コーチ — 体重・食事・血圧・睡眠を記録して、その日の指示を出すエンジン。

  python3 coach_server.py    → http://localhost:8771 (ダッシュボード)
  python3 coach.py today     → 今日の状況とアドバイスを端末に表示
  python3 coach.py weight 98.4
  python3 coach.py bp 145 92 --slot 朝

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
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "coach.db")
FOODS_PATH = os.path.join(BASE, "foods.json")

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

DEFAULT_PROFILE = {
    "height": 171.0,
    "start_weight": 100.0,
    "goal_weight": 70.0,
    "sex": "male",
    "age": 40,
    "activity": "low",
    "pace": "standard",
    "salt_target": 6.0,          # g/日。高血圧の減塩目標(JSH2019)
    "sleep_target": 450,         # 分。7時間30分
    "wake_target": "06:30",      # 起床時刻を固定するのが睡眠改善の土台
    "step_target": 8000,
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

    CREATE TABLE IF NOT EXISTS foods(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cat TEXT, name TEXT UNIQUE, unit TEXT,
        kcal REAL, p REAL, f REAL, c REAL, salt REAL,
        custom INTEGER DEFAULT 0, used INTEGER DEFAULT 0);
    """)
    con.commit()
    if con.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 0:
        load_builtin_foods(con)
    if con.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0:
        set_profile(con, DEFAULT_PROFILE)


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


def targets(prof, weight):
    """今の体重における1日の目標値をまとめて返す。"""
    h, age, sex = prof["height"], prof["age"], prof["sex"]
    b = bmr(weight, h, age, sex)
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

    # たんぱく質は「目標体重 × 1.5g」。減量中の筋肉の減りを抑えるため多めに取る
    protein = max(round(prof["goal_weight"] * 1.5), 90)
    fat = round(kcal * 0.25 / 9)                  # 脂質は総カロリーの25%
    carb = round((kcal - protein * 4 - fat * 9) / 4)
    return {
        "bmr": round(b),
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


def project(prof, weight):
    """目標体重に着く時期を、週ごとに代謝を再計算しながら見積もる。

    体重が落ちると基礎代謝も落ちて痩せる速度は鈍る。単純な割り算だと
    実態より早い予定が出てしまうので、1週ずつ回して積み上げる。
    """
    goal = prof["goal_weight"]
    w = weight
    curve = [{"week": 0, "weight": round(w, 1)}]
    weeks = 0
    while w > goal and weeks < 200:
        t = targets(prof, w)
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


def build_advice(con, prof, d, weight, t, intake, trend, bp7, sleep14, sas, day_row):
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

    # 7) 運動・活動量
    steps = (day_row["steps"] if day_row else None) or 0
    if steps and steps < prof["step_target"] * 0.6:
        msgs.append(_msg("info", "今日は %d歩(目標 %d歩)" % (steps, prof["step_target"]),
                         "早歩き30分は血圧を下げる効果がはっきりしている数少ない運動です。"
                         "一度にやらず10分×3回でも同じ効果が得られます。", "運動"))
    elif steps >= prof["step_target"]:
        msgs.append(_msg("good", "%d歩 — 目標達成" % steps,
                         "歩数は減量よりむしろ血圧と睡眠に効きます。", "運動"))

    # 8) 習慣チェックの未達
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
    t = targets(prof, weight)
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
        "projection": project(prof, weight),
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
        con.execute("SELECT * FROM days WHERE date=?", (data["date"],)).fetchone())
    return data


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
