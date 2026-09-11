#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ヘルスケアアプリ・活動量計の書き出しファイルを取り込む。

  python3 coach.py import ~/Downloads/書き出したデータ.zip     # iPhone ヘルスケア
  python3 coach.py import ~/Downloads/fitbit.csv               # 汎用CSV

iPhoneの「ヘルスケア」はAPIを外部に公開していないため、常時同期はできない。
かわりにアプリの書き出し機能が全データをXMLで出せるので、そこから読む。
歩数・体重・体脂肪率・血圧・睡眠・ワークアウトを拾う。

書き出し手順(iPhone):
  ヘルスケア → 右上のアイコン → 「すべての健康データを書き出す」
  → 共有シートから「ファイルに保存」 → 出来た書き出したデータ.zip を指定する
"""

import csv
import os
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

# HealthKitの型 → このツールでの扱い
STEP = "HKQuantityTypeIdentifierStepCount"
WEIGHT = "HKQuantityTypeIdentifierBodyMass"
FAT = "HKQuantityTypeIdentifierBodyFatPercentage"
LEAN = "HKQuantityTypeIdentifierLeanBodyMass"
SYS = "HKQuantityTypeIdentifierBloodPressureSystolic"
DIA = "HKQuantityTypeIdentifierBloodPressureDiastolic"
PULSE = "HKQuantityTypeIdentifierHeartRate"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"

WANTED = {STEP, WEIGHT, FAT, LEAN, SYS, DIA, PULSE, SLEEP}

# ワークアウトの種類 → (表示名, 分類)
WORKOUT_KIND = {
    "Walking": ("ウォーキング", "cardio"),
    "Running": ("ランニング", "cardio"),
    "Cycling": ("バイク", "cardio"),
    "Elliptical": ("クロストレーナー", "cardio"),
    "Rowing": ("ローイング", "cardio"),
    "Swimming": ("水泳", "cardio"),
    "StairClimbing": ("階段", "cardio"),
    "HighIntensityIntervalTraining": ("HIIT", "cardio"),
    "TraditionalStrengthTraining": ("筋トレ(アプリ記録)", "other"),
    "FunctionalStrengthTraining": ("筋トレ(アプリ記録)", "other"),
    "CoreTraining": ("体幹トレ(アプリ記録)", "other"),
    "Yoga": ("ヨガ", "other"),
    "Hiking": ("ハイキング", "cardio"),
}


def _dt(v):
    """「2026-09-11 08:00:00 +0900」形式を読む。"""
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None


def _open_xml(path):
    """zipならその中のXMLを、xmlならそのまま開く。"""
    if path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist()
                 if n.lower().endswith(".xml") and "export_cda" not in n.lower()]
        if not names:
            raise ValueError("zipの中にXMLが見つかりません")
        # 「書き出したデータ.xml」/「export.xml」を優先し、なければ一番大きいもの
        names.sort(key=lambda n: (not re.search(r"(export|書き出したデータ)\.xml$", n),
                                  -z.getinfo(n).file_size))
        return z.open(names[0])
    return open(path, "rb")


def parse_apple_health(path):
    """書き出しXMLを1件ずつ読んで、日付ごとにまとめる。

    ファイルが数百MBになることがあるので、全体を読み込まず iterparse で流す。
    """
    steps = defaultdict(lambda: defaultdict(float))   # 日付 → 提供元 → 歩数
    weight, fat, lean = {}, {}, {}
    bp_raw = defaultdict(dict)                        # 測定時刻 → {sys,dia,pulse}
    sleep_seg = defaultdict(list)                     # 起きた日 → 区間
    workouts = []

    with _open_xml(path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            tag = el.tag
            if tag == "Record":
                t = el.get("type")
                if t in WANTED:
                    _record(el, t, steps, weight, fat, lean, bp_raw, sleep_seg)
            elif tag == "Workout":
                _workout(el, workouts)
            if tag in ("Record", "Workout"):
                el.clear()

    return {
        "steps": _dedupe_steps(steps),
        "weight": weight, "fat": fat, "lean": lean,
        "bp": _pair_bp(bp_raw),
        "sleep": _fold_sleep(sleep_seg),
        "workouts": workouts,
    }


def _record(el, t, steps, weight, fat, lean, bp_raw, sleep_seg):
    start, end = _dt(el.get("startDate")), _dt(el.get("endDate"))
    if not start:
        return
    day = start.date().isoformat()
    raw = el.get("value")

    if t == SLEEP:
        if end:
            sleep_seg[_night_of(end)].append((start, end, raw or ""))
        return

    try:
        val = float(raw)
    except (TypeError, ValueError):
        return

    if t == STEP:
        steps[day][el.get("sourceName") or "?"] += val
    elif t == WEIGHT:
        weight[day] = val                      # その日の最後の測定が残る
    elif t == FAT:
        # 書き出しによって 0.365 と 36.5 の両方がありうる
        fat[day] = round(val * 100, 1) if val <= 1 else round(val, 1)
    elif t == LEAN:
        lean[day] = val
    elif t in (SYS, DIA, PULSE):
        key = start.isoformat()
        bp_raw[key]["sys" if t == SYS else "dia" if t == DIA else "pulse"] = val
        bp_raw[key]["date"] = day
        bp_raw[key]["hour"] = start.hour


def _workout(el, out):
    kind = (el.get("workoutActivityType") or "").replace("HKWorkoutActivityType", "")
    name, size = WORKOUT_KIND.get(kind, (kind or "ワークアウト", "other"))
    start = _dt(el.get("startDate"))
    if not start:
        return
    try:
        minutes = round(float(el.get("duration") or 0))
    except ValueError:
        minutes = 0
    if (el.get("durationUnit") or "min") != "min":
        minutes = round(minutes / 60) if el.get("durationUnit") == "sec" else minutes
    out.append({"date": start.date().isoformat(), "name": name,
                "size": size, "minutes": minutes})


def _dedupe_steps(steps):
    """iPhoneとApple Watchの両方に同じ歩数が入るので、提供元ごとの合計の最大を採る。

    区間の重なりを厳密に解くのが本来だが、日単位で見るぶんにはこれで足りる。
    """
    return {day: round(max(by_src.values())) for day, by_src in steps.items() if by_src}


def _pair_bp(bp_raw):
    """上と下は別レコードで出てくるので、同じ測定時刻どうしを組にする。"""
    out = []
    for key, v in sorted(bp_raw.items()):
        if "sys" in v and "dia" in v:
            out.append({"date": v["date"], "slot": "朝" if v["hour"] < 15 else "晩",
                        "systolic": round(v["sys"]), "diastolic": round(v["dia"]),
                        "pulse": round(v["pulse"]) if "pulse" in v else None})
    return out


def _night_of(end):
    """睡眠は「起きた日」に付ける。夕方以降に終わる区間は昼寝とみなして翌日には送らない。"""
    return end.date().isoformat()


def _fold_sleep(sleep_seg):
    """1晩ぶんの区間をまとめ、就寝・起床・実睡眠時間を出す。"""
    out = {}
    for day, segs in sleep_seg.items():
        asleep = [(s, e) for s, e, v in segs if "Asleep" in v]
        # 古いiOSは Asleep の区別がなく InBed しか無いことがある
        use = asleep or [(s, e) for s, e, v in segs if "InBed" in v]
        if not use:
            continue
        minutes = round(sum((e - s).total_seconds() for s, e in use) / 60)
        if minutes < 60:            # 昼寝は無視する
            continue
        bed, wake = min(s for s, _ in use), max(e for _, e in use)
        awake = sum(1 for s, e, v in segs if "Awake" in v)
        out[day] = {"bedtime": bed.strftime("%H:%M"), "waketime": wake.strftime("%H:%M"),
                    "minutes": minutes, "awakenings": awake or None}
    return out


# ── 汎用CSV(Fitbit / Garmin / Google Takeout / 体組成計アプリなど) ──────────

COLUMN_MAP = {
    "date": ["date", "日付", "測定日", "日時", "time", "timestamp"],
    "weight": ["weight", "体重", "weight(kg)", "体重(kg)", "体重kg"],
    "body_fat": ["fat", "body fat", "体脂肪", "体脂肪率", "bodyfat", "体脂肪率(%)"],
    "muscle_kg": ["muscle", "筋肉量", "muscle mass", "筋肉量(kg)"],
    "steps": ["steps", "歩数", "step count", "総歩数"],
    "systolic": ["systolic", "最高血圧", "収縮期", "上", "sys"],
    "diastolic": ["diastolic", "最低血圧", "拡張期", "下", "dia"],
    "pulse": ["pulse", "脈拍", "心拍数", "heart rate"],
    "minutes": ["sleep", "睡眠", "睡眠時間", "minutes asleep", "sleep minutes"],
}


def _match_columns(header):
    found = {}
    for i, col in enumerate(header):
        c = (col or "").strip().lower()
        for key, names in COLUMN_MAP.items():
            if key in found:
                continue
            if any(c == n or c.startswith(n) for n in names):
                found[key] = i
                break
    return found


def parse_csv(path):
    """列名から中身を推測して読む。日付の列は必須。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {"rows": [], "columns": {}}
    cols = _match_columns(rows[0])
    if "date" not in cols:
        raise ValueError("日付の列が見つかりません（date / 日付 / 測定日 など）")

    out = []
    for r in rows[1:]:
        if len(r) <= cols["date"]:
            continue
        d = _norm_date(r[cols["date"]])
        if not d:
            continue
        rec = {"date": d}
        for key, i in cols.items():
            if key == "date" or i >= len(r):
                continue
            v = (r[i] or "").strip().replace(",", "")
            if not v:
                continue
            try:
                rec[key] = float(v)
            except ValueError:
                pass
        if len(rec) > 1:
            out.append(rec)
    return {"rows": out, "columns": sorted(cols)}


def _norm_date(v):
    v = (v or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M",
                "%Y年%m月%d日", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(v[:len(datetime.now().strftime(fmt)) + 4]
                                     if " " in fmt else v[:10], fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", v)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    return None
