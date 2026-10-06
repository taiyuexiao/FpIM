#!/usr/bin/env bash
# FpIM 后端守护入口（launchd 用；也可手动跑）
# 配置全部来自 findperson/backend/.env（pydantic-settings 直读），这里只负责：等数据库 + 起进程
set -e
cd "$(dirname "$0")/../findperson/backend"

# 等 PG：先探活，不通则拉起 Docker Desktop 再等（最多 ~4 分钟）
for i in $(seq 1 48); do
  nc -z 127.0.0.1 5432 2>/dev/null && break
  [ "$i" = 1 ] && open -a Docker 2>/dev/null || true
  [ "$i" = 48 ] && { echo "数据库 4 分钟未就绪，退出（launchd 会自动重试）"; exit 1; }
  sleep 5
done

export FPIM_FILE_ROOT="${FPIM_FILE_ROOT:-/tmp/fpim-files}"
exec venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
