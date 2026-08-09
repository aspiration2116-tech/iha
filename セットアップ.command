#!/bin/zsh
# 別のMacに移した後、これをダブルクリックすると
#   ・python3の有無を確認
#   ・このフォルダの現在地に合わせてplist(自動起動設定)を作り直す
#   ・ログイン時自動起動 + 6時間ごとの自動収集を登録する
#   ・ダッシュボードを開く
# を全部やります。何度実行しても安全です(登録し直すだけ)。

set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
LABEL_SERVER="com.user.youtube-research-server"
LABEL_CRON="com.user.youtube-research"
AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "=== YouTubeリサーチツール セットアップ ==="
echo "設置場所: $HERE"

if ! command -v python3 >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。"
  echo "App Store の「Xcodeコマンドラインツール」か https://www.python.org/ からインストールしてください。"
  read "?Enterキーで閉じます..."
  exit 1
fi
echo "python3: $(python3 --version)"

mkdir -p "$AGENTS_DIR"

# 既存の登録があれば一旦止める(初回は失敗して当然なのでエラーは無視)
launchctl bootout "gui/$(id -u)/$LABEL_SERVER" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/$LABEL_CRON" 2>/dev/null || true

cat > "$AGENTS_DIR/$LABEL_SERVER.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL_SERVER</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$HERE/server.py</string></array>
    <key>WorkingDirectory</key><string>$HERE</string>
    <key>KeepAlive</key><true/>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$HERE/server.log</string>
    <key>StandardErrorPath</key><string>$HERE/server.err.log</string>
</dict>
</plist>
PLIST

cat > "$AGENTS_DIR/$LABEL_CRON.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL_CRON</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$HERE/research.py</string></array>
    <key>WorkingDirectory</key><string>$HERE</string>
    <key>StartInterval</key><integer>21600</integer>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>$HERE/research.log</string>
    <key>StandardErrorPath</key><string>$HERE/research.err.log</string>
</dict>
</plist>
PLIST

# 元のplistファイル(旧Mac用のパスが書かれた版)は使わないので消しておく
rm -f "$HERE/com.user.youtube-research-server.plist" "$HERE/com.user.youtube-research.plist"

launchctl bootstrap "gui/$(id -u)" "$AGENTS_DIR/$LABEL_SERVER.plist"
launchctl bootstrap "gui/$(id -u)" "$AGENTS_DIR/$LABEL_CRON.plist"

echo "登録しました。ダッシュボードを開きます..."
sleep 2
open http://localhost:8770

echo ""
echo "完了です。次回からはこのMacにログインするだけでサーバーが自動起動します。"
echo "6時間ごとに自動でリサーチを収集します(手動更新は不要)。"
read "?Enterキーでこのウィンドウを閉じます..."
