#!/usr/bin/env bash
# FpIM 开发环境一键拉起（后端 8002 + 前端 5175）
# 用法：./start-dev.sh        拉起（已起则跳过）
#       ./start-dev.sh stop   全部停掉
#
# 凭据从 findperson/backend/.env 读（.env 不入库），本脚本不含明文。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACK="$ROOT/findperson/backend"
FRONT="$ROOT/findperson"
LOG_DIR="$ROOT/.workbuddy/logs"
mkdir -p "$LOG_DIR"

# 从 backend/.env 提取变量（只取需要的两个）
env_get() { grep -E "^$1=" "$BACK/.env" | head -1 | cut -d= -f2-; }
DATABASE_URL="$(env_get DATABASE_URL)"
PGPASSWORD="$(env_get PGPASSWORD)"
[ -z "$DATABASE_URL" ] && { echo "❌ backend/.env 里缺 DATABASE_URL"; exit 1; }
[ -z "$PGPASSWORD" ] && { echo "❌ backend/.env 里缺 PGPASSWORD"; exit 1; }

stop_all() {
  for port in 8002 5175; do
    pid=$(lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null || true)
    [ -n "$pid" ] && kill "$pid" && echo "已停 :$port (pid $pid)" || true
  done
  return 0
}

if [ "${1:-}" = "stop" ]; then stop_all; exit 0; fi

# 数据库：5432 不在就先拉起 Docker Desktop（容器 swzr-pg 会随 Docker 自启）
if ! nc -z 127.0.0.1 5432 2>/dev/null; then
  echo "数据库 5432 不在，拉起 Docker Desktop…"
  open -a Docker 2>/dev/null || { echo "❌ 无法启动 Docker Desktop，请手动打开"; exit 1; }
  for i in $(seq 1 18); do
    nc -z 127.0.0.1 5432 2>/dev/null && break
    [ "$i" = 18 ] && { echo "❌ 等 3 分钟数据库还没就绪，请检查 Docker Desktop"; exit 1; }
    sleep 10
  done
  echo "数据库已就绪"
fi

# 后端
if nc -z 127.0.0.1 8002 2>/dev/null; then
  echo "后端 8002 已在跑，跳过"
else
  cd "$BACK"
  env DATABASE_URL="$DATABASE_URL" PGPASSWORD="$PGPASSWORD" \
    FPIM_FILE_ROOT=/tmp/fpim-files \
    CORS_ORIGINS="http://localhost:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5175" \
    nohup venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo "后端启动中（pid $!，日志 .workbuddy/logs/backend.log）"
fi

# 前端
if nc -z 127.0.0.1 5175 2>/dev/null; then
  echo "前端 5175 已在跑，跳过"
else
  cd "$FRONT"
  nohup node node_modules/vite/bin/vite.js --mode fpim --port 5175 --host 127.0.0.1 --strictPort \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo "前端启动中（pid $!，日志 .workbuddy/logs/frontend.log）"
fi

sleep 4
echo "---- 探活 ----"
curl -s -m 3 --noproxy '*' http://127.0.0.1:8002/health && echo "  ← 后端 OK" || echo "后端未就绪，看 .workbuddy/logs/backend.log"
curl -s -o /dev/null -w "前端 HTTP %{http_code}\n" -m 3 --noproxy '*' http://127.0.0.1:5175/ || echo "前端未就绪，看 .workbuddy/logs/frontend.log"
echo "打开 http://127.0.0.1:5175 （账号 P0004，密码见 findperson/backend/.env 的 SEED_PASSWORD）"
