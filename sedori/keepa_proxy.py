#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""せどり仕入れツールの配信 + Keepa API 中継サーバー。

  python3 keepa_proxy.py            → http://<このMacのIP>:8771 をスマホで開く

やること
  - このフォルダ(index.html など)を配信する
  - /keepa/<endpoint>?... を https://api.keepa.com/<endpoint>?... にそのまま転送し、
    CORSヘッダーを付けて返す(ブラウザから直接Keepaを呼べない環境向け)

APIキーはスマホ側(アプリの設定)に保存され、クエリに乗って届いたものをそのまま転送するだけ。
このサーバーは自宅のWi-Fi内だけで使う前提(認証なし)。外に公開しないこと。
"""

import os
import socket
import sys
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SEDORI_PORT", "8771"))
KEEPA = "https://api.keepa.com/"
ALLOWED = {"product", "search", "token", "graphimage", "bestsellers", "category", "seller", "query"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def log_message(self, fmt, *args):  # 静かに
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/keepa/"):
            return self._proxy(parsed)
        return super().do_GET()

    def _proxy(self, parsed):
        endpoint = parsed.path[len("/keepa/"):].strip("/")
        if endpoint not in ALLOWED:
            return self._send(400, b'{"error":{"type":"endpoint not allowed"}}', "application/json")
        url = KEEPA + endpoint + ("?" + parsed.query if parsed.query else "")
        req = urllib.request.Request(url, headers={"User-Agent": "sedori-tool/1.0", "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=40) as res:
                body = res.read()
                ctype = res.headers.get("Content-Type", "application/json")
                return self._send(res.status, body, ctype)
        except urllib.error.HTTPError as e:  # Keepaのエラー本文(429など)をそのまま返す
            body = e.read()
            return self._send(e.code, body, e.headers.get("Content-Type", "application/json"))
        except Exception as e:  # noqa: BLE001
            msg = '{"error":{"type":"proxy","message":%s}}' % _js(str(e))
            return self._send(502, msg.encode("utf-8"), "application/json")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _js(s):
    import json
    return json.dumps(s, ensure_ascii=False)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    print("=" * 56, flush=True)
    print("せどり仕入れツール を配信中", flush=True)
    print("  このMac:     http://localhost:%d" % PORT, flush=True)
    print("  スマホから:  http://%s:%d   (同じWi-Fiに接続)" % (ip, PORT), flush=True)
    print("  アプリの設定 → 接続方法「中継サーバー経由」→ URL に上のアドレスを入力", flush=True)
    print("  止めるときは Ctrl+C", flush=True)
    print("=" * 56, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if sys.version_info < (3, 7):
        sys.exit("Python 3.7 以上が必要です")
    main()
