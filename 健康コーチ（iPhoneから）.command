#!/bin/zsh
# iPhoneから同じWi-Fi経由で健康コーチを開きたいときはこちら。
# 起動後に表示される http://192.168.x.x:8771 をiPhoneのSafariで開き、
# 共有ボタン →「ホーム画面に追加」でアプリのように使えます。
# 認証は無いので、自宅のWi-Fi以外では通常の「健康コーチ.command」を使ってください。
cd "$(dirname "$0")/coach"
PORT=8771

if ! command -v python3 >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。"
  read "?Enterキーで閉じます..."
  exit 1
fi

if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/api/data"; then
  echo "すでに起動しています。iPhoneからも開くには一度終了してからこのファイルを実行してください。"
  echo "  終了: pkill -f coach_server.py"
  read "?Enterキーで閉じます..."
  exit 0
fi

echo "健康コーチを起動します（同じWi-FiのiPhoneからも開けます）..."
echo "このウィンドウを閉じるとサーバーも止まります。"
echo
COACH_HOST=0.0.0.0 python3 coach_server.py
