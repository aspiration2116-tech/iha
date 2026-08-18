#!/bin/zsh
cd "$(dirname "$0")"
(python3 mercari_server.py > mercari_server.log 2>&1 &)
sleep 1
open http://localhost:8771
