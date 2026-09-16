#!/bin/zsh
# 沖縄観光チャンネル用のリサーチ(プロファイル: okinawa)
#   ・ダッシュボードが立っていなければ起動して開く (http://localhost:8771)
#   ・そのあと収集を実行する(初回は競合チャンネルの解決に数分かかります)
# ライフハック雑学のほう(8770)とは設定もDBも別なので、同時に動かして大丈夫です。

cd "$(dirname "$0")"
PROFILE=okinawa
PORT=8771

mkdir -p "profiles/$PROFILE"

if ! curl -s -o /dev/null -m 2 "http://localhost:$PORT"; then
  echo "ダッシュボードを起動します..."
  nohup python3 server.py --profile "$PROFILE" \
    > "profiles/$PROFILE/server.log" 2> "profiles/$PROFILE/server.err.log" &
  sleep 2
fi

open "http://localhost:$PORT"

echo "=== 沖縄リサーチ 収集開始 ==="
python3 research.py --profile "$PROFILE"

echo ""
echo "完了しました。ダッシュボード: http://localhost:$PORT"
read "?Enterキーでこのウィンドウを閉じます..."
