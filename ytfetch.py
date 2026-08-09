#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 取得・解析ユーティリティ(標準ライブラリのみ / APIキー不要)

取得元は3つ。
  1. RSS  https://www.youtube.com/feeds/videos.xml?channel_id=UC...
     → 直近15本の「正確な投稿日時」と再生数が取れる。一番信頼できる。
  2. チャンネルの /videos ページ
     → 直近30本。日時は「23 時間前」の相対表記だが、RSSより奥まで取れる。
  3. 検索結果ページ /results?search_query=...
     → 新ネタ・新規競合チャンネルの発見用。
"""

import gzip
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_last_request_at = [0.0]


class FetchError(Exception):
    pass


def http_get(url, interval=1.5, retries=2, timeout=25):
    """行儀よく間隔を空けて GET する。"""
    for attempt in range(retries + 1):
        wait = interval - (time.time() - _last_request_at[0])
        if wait > 0:
            time.sleep(wait)
        _last_request_at[0] = time.time()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip",
            "Cookie": "SOCS=CAI;",  # 同意バナー回避
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                raw = res.read()
                if res.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if attempt >= retries:
                raise FetchError("%s : %s" % (url, e))
            time.sleep(3 * (attempt + 1))
    raise FetchError(url)


# ---------------------------------------------------------------- 文字列解析

_VIEW_RE = re.compile(r"([\d,.]+)\s*(億|万|千)?\s*回視聴")


def parse_views(text):
    """'1.2万回視聴' → 12000 / '1,261回視聴' → 1261"""
    if not text:
        return None
    m = _VIEW_RE.search(text.replace("　", " "))
    if not m:
        m2 = re.search(r"([\d,]+)\s*views", text)
        return int(m2.group(1).replace(",", "")) if m2 else None
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit == "億":
        num *= 100000000
    elif unit == "万":
        num *= 10000
    elif unit == "千":
        num *= 1000
    return int(num)


def parse_count_ja(text):
    """'チャンネル登録者数 3.95万人' → 39500"""
    if not text:
        return None
    m = re.search(r"([\d,.]+)\s*(億|万|千)?\s*人", text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit == "億":
        num *= 100000000
    elif unit == "万":
        num *= 10000
    elif unit == "千":
        num *= 1000
    return int(num)


_REL_UNITS = [
    ("秒", 1 / 3600.0), ("分", 1 / 60.0), ("時間", 1.0),
    ("日", 24.0), ("週間", 24 * 7.0), ("か月", 24 * 30.4), ("ヶ月", 24 * 30.4),
    ("年", 24 * 365.0),
]


def parse_relative_time(text, now=None):
    """'23 時間前' → その時刻の datetime(UTC)。不明なら None。"""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    m = re.search(r"(\d+)\s*(秒|分|時間|日|週間|か月|ヶ月|年)前", text.replace("　", " "))
    if not m:
        return None
    n = int(m.group(1))
    for unit, hours in _REL_UNITS:
        if unit == m.group(2):
            return now - timedelta(hours=n * hours)
    return None


def parse_duration(text):
    """'11:15' → 675 秒"""
    if not text:
        return None
    parts = text.strip().split(":")
    if not all(p.isdigit() for p in parts) or len(parts) > 3:
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + int(p)
    return sec


def extract_initial_data(html):
    for pat in (r"var ytInitialData = (\{.*?\});</script>",
                r'window\["ytInitialData"\]\s*=\s*(\{.*?\});'):
        m = re.search(pat, html, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _walk(node, key, out):
    if isinstance(node, dict):
        if key in node:
            out.append(node[key])
        for v in node.values():
            _walk(v, key, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, key, out)
    return out


def _first_text(node):
    """{'simpleText':..} / {'runs':[..]} / {'content':..} をまとめて文字列化。"""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "simpleText" in node:
            return node["simpleText"]
        if "content" in node and isinstance(node["content"], str):
            return node["content"]
        if "runs" in node:
            return "".join(r.get("text", "") for r in node["runs"])
    return ""


# ---------------------------------------------------------------- チャンネル

def resolve_channel(handle_or_id, interval=1.5):
    """@handle か UC... から {channel_id, handle, title, subs} を得る。"""
    key = handle_or_id.strip()
    if key.startswith("UC") and len(key) == 24:
        url = "https://www.youtube.com/channel/%s" % key
    else:
        url = "https://www.youtube.com/%s" % (key if key.startswith("@") else "@" + key)
    html = http_get(url, interval=interval)
    cid = None
    m = re.search(r'"externalId":"(UC[\w-]+)"', html) or re.search(r'"channelId":"(UC[\w-]+)"', html)
    if m:
        cid = m.group(1)
    title = None
    mt = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if mt:
        title = mt.group(1)
    subs = None
    ms = re.search(r"チャンネル登録者数\s*([\d,.]+\s*[億万千]?)\s*人", html)
    if ms:
        subs = parse_count_ja(ms.group(1) + "人")
    handle = None
    mh = re.search(r'"canonicalBaseUrl":"/(@[^"/]+)"', html)
    if mh:
        handle = urllib.parse.unquote(mh.group(1))
    elif key.startswith("@"):
        handle = key
    if not cid:
        raise FetchError("channelId が取れませんでした: %s" % handle_or_id)
    return {"channel_id": cid, "handle": handle, "title": title, "subs": subs}


def fetch_channel_rss(channel_id, interval=1.5):
    """RSS から直近15本。published は正確な日時。"""
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=%s" % channel_id
    xml = http_get(url, interval=interval)
    out = []
    ch_title = None
    mct = re.search(r"<title>([^<]*)</title>", xml)
    if mct:
        ch_title = mct.group(1)
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry)
        title = re.search(r"<title>(.*?)</title>", entry, re.S)
        pub = re.search(r"<published>([^<]+)</published>", entry)
        views = re.search(r'<media:statistics views="(\d+)"', entry)
        if not vid:
            continue
        out.append({
            "video_id": vid.group(1),
            "channel_id": channel_id,
            "title": _unescape(title.group(1)) if title else "",
            "published_at": pub.group(1) if pub else None,
            "views": int(views.group(1)) if views else None,
            "duration_sec": None,
            "source": "rss",
        })
    return ch_title, out


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'"))


def fetch_channel_videos(channel_id, interval=1.5, tab="videos"):
    """チャンネルの /videos ページ(直近30本前後)。日時は相対表記からの推定。"""
    url = "https://www.youtube.com/channel/%s/%s" % (channel_id, tab)
    html = http_get(url, interval=interval)
    data = extract_initial_data(html)
    if not data:
        return []
    now = datetime.now(timezone.utc)
    out = []
    for lock in _walk(data, "lockupViewModel", []):
        blob = json.dumps(lock, ensure_ascii=False)
        mv = re.search(r"/vi/([\w-]{11})/", blob)
        if not mv:
            continue
        meta = lock.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = _first_text(meta.get("title"))
        rows = _walk(meta.get("metadata", {}), "metadataParts", [])
        views = published = None
        for row in rows:
            for part in row:
                txt = _first_text(part.get("text"))
                if "回視聴" in txt:
                    views = parse_views(txt)
                elif "前" in txt:
                    published = parse_relative_time(txt, now)
        dur = None
        for badge in _walk(lock.get("contentImage", {}), "thumbnailBadgeViewModel", []):
            d = parse_duration(badge.get("text", ""))
            if d:
                dur = d
        out.append({
            "video_id": mv.group(1),
            "channel_id": channel_id,
            "title": title,
            "published_at": published.isoformat() if published else None,
            "published_is_estimate": 1,
            "views": views,
            "duration_sec": dur,
            "source": "channel_page",
        })
    # 重複除去(同じ動画が複数箇所に出ることがある)
    seen, uniq = set(), []
    for v in out:
        if v["video_id"] in seen or not v["title"]:
            continue
        seen.add(v["video_id"])
        uniq.append(v)
    return uniq


# ---------------------------------------------------------------- 字幕(台本)

def _innertube_player(video_id, interval=1.5):
    """innertube の ANDROID クライアントで player 情報を取る。
    WEB クライアントと違い、字幕URLが POT トークンなしで生きている。"""
    body = json.dumps({
        "context": {"client": {
            "clientName": "ANDROID", "clientVersion": "20.10.38",
            "androidSdkVersion": 30, "hl": "ja",
            "userAgent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip",
        }},
        "videoId": video_id,
    }).encode()
    wait = interval - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.time()
    req = urllib.request.Request(
        "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
        data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode("utf-8", "replace"))


_TAG_RE = re.compile(r"<[^>]+>")


def fetch_transcript(video_id, interval=1.5):
    """字幕(あれば手動、なければ自動生成)を取り、
    {lang, kind, text, description, duration_sec} を返す。無ければ None。"""
    d = _innertube_player(video_id, interval=interval)
    detail = d.get("videoDetails", {})
    tracks = (d.get("captions", {})
               .get("playerCaptionsTracklistRenderer", {})
               .get("captionTracks", []))
    if not tracks:
        return None
    # 日本語の手動字幕 > 日本語の自動生成 > 先頭
    def rank(t):
        ja = t.get("languageCode", "").startswith("ja")
        manual = t.get("kind") != "asr"
        return (ja, manual)
    track = sorted(tracks, key=rank, reverse=True)[0]
    xml = http_get(track["baseUrl"], interval=interval)
    lines = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", xml, re.S):
        txt = _TAG_RE.sub("", p)
        txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                  .replace("&quot;", '"').replace("&#39;", "'").strip())
        if txt:
            lines.append(txt)
    if not lines:
        return None
    return {
        "lang": track.get("languageCode"),
        "kind": track.get("kind") or "manual",
        "text": "\n".join(lines),
        "description": detail.get("shortDescription", ""),
        "duration_sec": int(detail.get("lengthSeconds") or 0) or None,
    }


# ---------------------------------------------------------------- コメント

def _innertube_next(payload, interval=1.0):
    wait = interval - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.time()
    body = json.dumps({
        "context": {"client": {"clientName": "WEB",
                               "clientVersion": "2.20250801.01.00", "hl": "ja"}},
        **payload}).encode()
    req = urllib.request.Request(
        "https://www.youtube.com/youtubei/v1/next?prettyPrint=false",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Accept-Language": "ja-JP,ja;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return res.read().decode("utf-8", "replace")


def _extract_comment_payloads(raw):
    out = []
    def walk(o):
        if isinstance(o, dict):
            if "commentEntityPayload" in o:
                out.append(o["commentEntityPayload"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(raw))
    res = []
    for c in out:
        props = c.get("properties", {})
        text = (props.get("content", {}) or {}).get("content", "")
        if not text:
            continue
        likes = parse_count_ja((c.get("toolbar", {}) or {}).get("likeCountNotliked", "") + "人")
        res.append({
            "text": text,
            "author": (c.get("author", {}) or {}).get("displayName", ""),
            "is_creator": bool((c.get("author", {}) or {}).get("isCreator")),
            "likes": likes or 0,
            "replies": parse_count_ja(((c.get("toolbar", {}) or {}).get("replyCount") or "0") + "人") or 0,
            "published": props.get("publishedTime", ""),
        })
    return res


def fetch_comments(video_id, max_comments=60, interval=1.0):
    """コメントを新しい順ではなく「トップコメント」順で最大 max_comments 件。

    watch/next のどの continuation がコメント本体かは応答からは判別しにくいので、
    全トークンを試して一番多く返ってきたものを採用する。"""
    first = _innertube_next({"videoId": video_id}, interval=interval)
    tokens = list(dict.fromkeys(re.findall(
        r'"continuationCommand"\s*:\s*\{\s*"token"\s*:\s*"([^"]{20,})"', first)))
    best_raw, best = None, []
    for tok in tokens[:6]:
        try:
            raw = _innertube_next({"continuation": tok}, interval=interval)
        except Exception:  # noqa: BLE001
            continue
        got = _extract_comment_payloads(raw)
        if len(got) > len(best):
            best_raw, best = raw, got
        if len(best) >= 10:
            break
    comments = best
    # 続きを1〜2ページたどる
    raw = best_raw
    while raw and len(comments) < max_comments:
        nxt = re.findall(r'"continuationCommand"\s*:\s*\{\s*"token"\s*:\s*"([^"]{100,})"', raw)
        if not nxt:
            break
        try:
            raw = _innertube_next({"continuation": nxt[-1]}, interval=interval)
        except Exception:  # noqa: BLE001
            break
        more = _extract_comment_payloads(raw)
        if not more:
            break
        comments += more
    # 重複除去
    seen, uniq = set(), []
    for c in comments:
        key = (c["author"], c["text"][:60])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq[:max_comments]


# ---------------------------------------------------------------- 検索

# sp= の値。YouTube の検索フィルタをそのまま使う。
SEARCH_FILTERS = {
    "today": "EgQIAhAB",      # 今日 + 動画
    "week": "EgQIAxAB",       # 今週 + 動画
    "month": "EgQIBBAB",      # 今月 + 動画
    "year": "EgQIBRAB",       # 今年 + 動画
    "views": "CAMSAhAB",      # 再生回数順 + 動画
    "recent": "CAISAhAB",     # アップロード日順 + 動画
    "all": "EgIQAQ%3D%3D",    # 動画のみ
}


def _parse_video_renderer(vr, now, keyword):
    vid = vr.get("videoId")
    if not vid:
        return None
    owner = vr.get("ownerText") or vr.get("longBylineText") or {}
    cid = ctitle = None
    for run in owner.get("runs", []):
        ctitle = run.get("text")
        ep = run.get("navigationEndpoint", {}).get("browseEndpoint", {})
        cid = ep.get("browseId")
        break
    published = parse_relative_time(_first_text(vr.get("publishedTimeText")), now)
    return {
        "video_id": vid,
        "channel_id": cid,
        "channel_title": ctitle,
        "title": _first_text(vr.get("title")),
        "published_at": published.isoformat() if published else None,
        "published_is_estimate": 1,
        "views": parse_views(_first_text(vr.get("viewCountText"))),
        "duration_sec": parse_duration(_first_text(vr.get("lengthText"))),
        "source": "search:%s" % keyword,
    }


def _search_page(data):
    """検索応答1ページ分から (videoRenderer列, 次のcontinuationトークン) を取り出す。"""
    vids = _walk(data, "videoRenderer", [])
    # continuationCommand は複数返る。先頭が「続きを読む」用で、
    # 後ろに並ぶのはフィルタチップ用(毎ページ同じ)なので先頭だけ使う。
    token = None
    for cc in _walk(data, "continuationCommand", []):
        if cc.get("request") == "CONTINUATION_REQUEST_TYPE_SEARCH" and cc.get("token"):
            token = cc["token"]
            break
    return vids, token


def search_videos(keyword, period="month", interval=1.5, limit=20):
    """innertube の search API でキーワード検索。limit 件までページをたどる。"""
    sp = SEARCH_FILTERS.get(period, SEARCH_FILTERS["month"]).replace("%3D", "=")
    now = datetime.now(timezone.utc)
    out, seen = [], set()
    payload = {"query": keyword, "params": sp}
    # 1ページの実収穫は4〜20件とばらつくので、ページ数は多めに許可して件数で打ち切る
    max_pages = 22 if limit > 20 else 2
    for _ in range(max_pages):
        if len(out) >= limit:
            break
        wait = interval - (time.time() - _last_request_at[0])
        if wait > 0:
            time.sleep(wait)
        _last_request_at[0] = time.time()
        body = json.dumps({
            "context": {"client": {"clientName": "WEB",
                                   "clientVersion": "2.20250801.01.00", "hl": "ja"}},
            **payload}).encode()
        req = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA,
                     "Accept-Language": "ja-JP,ja;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                data = json.loads(res.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            if not out:
                raise FetchError("search %s : %s" % (keyword, e))
            break
        vids, token = _search_page(data)
        for vr in vids:
            v = _parse_video_renderer(vr, now, keyword)
            if v and v["video_id"] not in seen:
                seen.add(v["video_id"])
                out.append(v)
        if not token:
            break
        payload = {"continuation": token}
    return out[:limit]
