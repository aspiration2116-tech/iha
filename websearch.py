#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube以外のWebソースを横断検索する(標準ライブラリのみ / APIキー不要)。

ソース:
  x         Yahoo!リアルタイム検索 (X/Twitterの投稿)
  ynews     Yahoo!ニュース検索
  gnews     Google News RSS (ネット記事全般)
  hatena    はてなブックマーク検索 (話題のブログ・記事)
  blog      DuckDuckGo (ブログ・ネット記事)
  tiktok    DuckDuckGo site:tiktok.com
  instagram DuckDuckGo site:instagram.com
  threads   DuckDuckGo site:threads.com
"""

import concurrent.futures
import html as html_mod
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", "replace")


def _clean(text):
    return html_mod.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


# ---------------------------------------------------------------- 各ソース

def fetch_x(query, limit=30):
    """Yahoo!リアルタイム検索: Xの投稿が取れる。"""
    url = "https://search.yahoo.co.jp/realtime/search?" + urllib.parse.urlencode({"p": query})
    html = _get(url)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        entries = data["props"]["pageProps"]["pageData"]["timeline"]["entry"]
    except (KeyError, json.JSONDecodeError):
        return []
    out = []
    for e in entries[:limit]:
        if not e.get("id"):
            continue
        text = re.sub(r"\s*\t?(START|END)\t?\s*", "", e.get("displayText", ""))
        ts = int(e.get("createdAt", 0) or 0)
        out.append({
            "title": text[:300],
            "url": (e.get("url") or "").split("?")[0],
            "author": "%s (@%s)" % (e.get("name", ""), e.get("screenName", "")),
            "date": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
        })
    return out


def fetch_yahoo_news(query, limit=25):
    """Yahoo!ニュース検索: 記事リンクをHTMLから直接拾う。"""
    url = "https://news.yahoo.co.jp/search?" + urllib.parse.urlencode(
        {"p": query, "ei": "utf-8"})
    html = _get(url)
    out, seen = [], set()
    for m in re.finditer(
            r'<a[^>]+href="(https://news\.yahoo\.co\.jp/articles/[^"]+)"[^>]*>(.*?)</a>',
            html, re.S):
        u = m.group(1).split("?")[0]
        title = _clean(m.group(2))
        if u in seen or len(title) < 8:
            continue
        seen.add(u)
        # 「タイトル…本文抜粋」の形で来るので分割
        title = title.split("…")[0][:120]
        out.append({"title": title, "url": u, "author": "Yahoo!ニュース", "date": None})
        if len(out) >= limit:
            break
    return out


def fetch_google_news(query, limit=25):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"})
    xml_data = _get(url)
    out = []
    try:
        root = ET.fromstring(xml_data.encode())
    except ET.ParseError:
        return []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        out.append({"title": title, "url": link, "author": src or "Google News",
                    "date": pub})
        if len(out) >= limit:
            break
    return out


def fetch_hatena(query, limit=25):
    """はてなブックマーク検索RSS: ブクマ数つきで話題の記事が取れる。"""
    url = "https://b.hatena.ne.jp/search/text?" + urllib.parse.urlencode(
        {"q": query, "mode": "rss", "sort": "recent"})
    xml_data = _get(url)
    out = []
    # RSS1.0。名前空間が面倒なので正規表現で
    for m in re.finditer(r"<item[^>]*>(.*?)</item>", xml_data, re.S):
        item = m.group(1)
        title = _clean((re.search(r"<title>(.*?)</title>", item, re.S) or [None, ""])[1])
        link = _clean((re.search(r"<link>(.*?)</link>", item, re.S) or [None, ""])[1])
        count = (re.search(r"<hatena:bookmarkcount>(\d+)</hatena:bookmarkcount>", item)
                 or [None, ""])[1]
        date = _clean((re.search(r"<dc:date>(.*?)</dc:date>", item, re.S) or [None, ""])[1])
        if not title or not link:
            continue
        out.append({"title": title, "url": link,
                    "author": "はてブ %susers" % (count or "?"), "date": date or None})
        if len(out) >= limit:
            break
    return out


# DuckDuckGo は同時アクセスに厳しいので、直列化して間隔を空ける
_ddg_lock = threading.Lock()
_ddg_last = [0.0]


def _ddg_get(url):
    with _ddg_lock:
        wait = 2.5 - (time.time() - _ddg_last[0])
        if wait > 0:
            time.sleep(wait)
        html = _get(url)
        _ddg_last[0] = time.time()
        if "result__a" not in html:  # レート制限ページの可能性 → 1回だけ待って再試行
            time.sleep(4)
            html = _get(url)
            _ddg_last[0] = time.time()
        return html


def _ddg(query, limit=20, domain_filter=None):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
        {"q": query, "kl": "jp-jp"})
    html = _ddg_get(url)
    titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    out = []
    for i, (href, inner) in enumerate(titles):
        if href.startswith("//duckduckgo.com/l/") or "/l/?" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(
                "https:" + href if href.startswith("//") else href).query)
            href = qs.get("uddg", [href])[0]
        netloc = urllib.parse.urlparse(href).netloc
        if "duckduckgo.com" in netloc:  # 広告・内部リンク
            continue
        if domain_filter and not any(d in netloc for d in domain_filter):
            continue
        title = _clean(inner)
        if not title:
            continue
        snip = _clean(snippets[i]) if i < len(snippets) else ""
        out.append({"title": title, "url": href, "author": netloc,
                    "date": None, "snippet": snip[:160]})
        if len(out) >= limit:
            break
    return out


# Yahoo!検索も直列化(同時アクセスを避ける)
_yj_lock = threading.Lock()
_yj_last = [0.0]


def _yahoo_web(query, limit=20, domain_filter=None):
    """Yahoo!検索のオーガニック結果(sw-Card Algo ブロック)を解析する。"""
    with _yj_lock:
        wait = 1.5 - (time.time() - _yj_last[0])
        if wait > 0:
            time.sleep(wait)
        url = "https://search.yahoo.co.jp/search?" + urllib.parse.urlencode({"p": query})
        html = _get(url)
        _yj_last[0] = time.time()
    out, seen = [], set()
    for block in re.findall(r'<div class="sw-Card Algo.*?</section>', html, re.S):
        mu = re.search(r'<a href="(https?://[^"]+)"', block)
        mt = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        if not mu:
            continue
        u = mu.group(1).split("?")[0] if "youtube.com" not in mu.group(1) else mu.group(1)
        netloc = urllib.parse.urlparse(u).netloc
        if domain_filter and not any(d in netloc for d in domain_filter):
            continue
        if u in seen:
            continue
        seen.add(u)
        title = _clean(mt.group(1)) if mt else u
        ms = re.search(r'<p class="sw-Card__summary[^"]*"[^>]*>(.*?)</p>', block, re.S)
        out.append({"title": title[:150], "url": u, "author": netloc,
                    "date": None, "snippet": _clean(ms.group(1))[:160] if ms else ""})
        if len(out) >= limit:
            break
    return out


def _web_search(query, limit, domain_filter=None):
    """Yahoo!検索を優先し、ダメなら DuckDuckGo にフォールバック。"""
    try:
        out = _yahoo_web(query, limit, domain_filter)
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return _ddg(query, limit, domain_filter)


def fetch_blog(query, limit=20):
    return _web_search("%s ブログ" % query, limit)


def fetch_note(query, limit=15):
    """note.com の公開検索API。"""
    url = "https://note.com/api/v3/searches?" + urllib.parse.urlencode(
        {"context": "note", "q": query, "size": limit})
    d = json.loads(_get(url))
    items = (d.get("data", {}).get("notes", {}) or {}).get("contents") or []
    out = []
    for n in items[:limit]:
        key = n.get("key")
        user = (n.get("user") or {}).get("urlname", "")
        if not key:
            continue
        out.append({
            "title": n.get("name", ""),
            "url": "https://note.com/%s/n/%s" % (user, key),
            "author": "note / " + ((n.get("user") or {}).get("nickname") or user),
            "date": n.get("publishAt") or n.get("publish_at"),
        })
    return out


def _yahoo_video(query, limit=20, domain_filter=None):
    """Yahoo!動画検索: TikTok/Instagramリール/YouTube等の動画がサムネ付きで取れる。"""
    with _yj_lock:
        wait = 1.5 - (time.time() - _yj_last[0])
        if wait > 0:
            time.sleep(wait)
        url = "https://search.yahoo.co.jp/video/search?" + urllib.parse.urlencode({"p": query})
        html = _get(url)
        _yj_last[0] = time.time()
    out, seen = [], set()
    for chunk in html.split('<div class="sw-Card sw-ThumbnailListItem">')[1:]:
        mu = re.search(r'<a href="(https?://[^"]+)" class="sw-Card__titleInner"', chunk)
        mt = re.search(r'<h3 class="sw-Card__titleMain[^>]*>(.*?)</h3>', chunk, re.S)
        if not mu or not mt:
            continue
        u = mu.group(1)
        netloc = urllib.parse.urlparse(u).netloc
        if domain_filter and not any(d in netloc for d in domain_filter):
            continue
        if u in seen:
            continue
        seen.add(u)
        mi = re.search(r'<img[^>]+src="(https?://[^"]+)"', chunk)
        md = re.search(r">(\d+:\d{2})<", chunk)
        out.append({
            "title": _clean(mt.group(1))[:150],
            "url": u,
            "author": netloc + (" 動画 %s" % md.group(1) if md else ""),
            "date": None,
            "thumb": mi.group(1) if mi else None,
        })
        if len(out) >= limit:
            break
    return out


def fetch_tiktok(query, limit=20):
    """TikTokの動画。Yahoo!動画検索→ダメならWeb検索。"""
    try:
        out = _yahoo_video("%s site:tiktok.com" % query, limit,
                           domain_filter=["tiktok.com"])
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return _web_search("%s site:tiktok.com" % query, limit, domain_filter=["tiktok.com"])


def fetch_instagram(query, limit=20):
    """Instagramのリール・動画。Yahoo!動画検索→ダメならWeb検索。"""
    try:
        out = _yahoo_video("%s site:instagram.com" % query, limit,
                           domain_filter=["instagram.com"])
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return _web_search("%s site:instagram.com" % query, limit,
                       domain_filter=["instagram.com"])


def fetch_threads(query, limit=15):
    return _web_search("%s site:threads.com OR site:threads.net" % query, limit,
                       domain_filter=["threads.com", "threads.net"])


SOURCES = {
    "x":         ("X(Twitter)",    fetch_x),
    "ynews":     ("Yahoo!ニュース", fetch_yahoo_news),
    "gnews":     ("ニュース記事",   fetch_google_news),
    "hatena":    ("はてブ",        fetch_hatena),
    "note":      ("note",         fetch_note),
    "blog":      ("ブログ・記事",   fetch_blog),
    "tiktok":    ("TikTok動画",       fetch_tiktok),
    "instagram": ("Instagramリール",  fetch_instagram),
    "threads":   ("Threads",      fetch_threads),
}


def search_all(query, source_keys=None):
    """選択ソースを並列で検索して {key: {label, items|error}} を返す。"""
    keys = [k for k in (source_keys or SOURCES.keys()) if k in SOURCES]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(SOURCES[k][1], query): k for k in keys}
        for fut in concurrent.futures.as_completed(futs):
            k = futs[fut]
            label = SOURCES[k][0]
            try:
                results[k] = {"label": label, "items": fut.result()}
            except Exception as e:  # noqa: BLE001
                results[k] = {"label": label, "items": [], "error": str(e)}
    return {k: results[k] for k in keys if k in results}
