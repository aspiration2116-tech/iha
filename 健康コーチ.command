#!/bin/zsh
# ダブルクリックで健康コーチを開く。
# サーバーが動いていなければ起動してから、ブラウザを開きます。
cd "$(dirname "$0")/coach"
PORT=8771

if ! command -v python3 >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。"
  echo "App Store の「Xcodeコマンドラインツール」か https://www.python.org/ からインストールしてください。"
  read "?Enterキーで閉じます..."
  exit 1
fi

# 起動済みかどうかを、応答があるかで判定する
if ! curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/api/data"; then
  echo "健康コーチを起動します..."
  nohup python3 coach_server.py > coach.log 2>&1 &
  for i in {1..40}; do
    curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$PORT/api/data" && break
    sleep 0.25
  done
fi

open "http://localhost:$PORT"
