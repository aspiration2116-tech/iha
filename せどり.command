#!/bin/zsh
# せどり仕入れツールをこのMacで配信して、同じWi-Fiのスマホから使えるようにする。
# ダブルクリックで起動。ウィンドウを閉じる(Ctrl+C)と止まる。
cd "$(dirname "$0")/sedori" || exit 1
open "http://localhost:8771" 2>/dev/null &
exec python3 keepa_proxy.py
