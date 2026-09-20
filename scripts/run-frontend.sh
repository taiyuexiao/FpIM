#!/usr/bin/env bash
# FpIM 前端守护入口（launchd 用；也可手动跑）
set -e
cd "$(dirname "$0")/../findperson"
exec /opt/homebrew/bin/node node_modules/vite/bin/vite.js --mode fpim --port 5175 --host 127.0.0.1 --strictPort
