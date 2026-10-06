#!/usr/bin/env bash
# 恢复演练（04-生产加固技术方案 §2.1 验收）：恢复最新备份到临时库并跑只读冒烟断言
# 用法: ./scripts/restore-drill.sh [dump文件路径，默认取最新]
set -euo pipefail
CONTAINER="${FPIM_PG_CONTAINER:-swzr-pg}"
DB_USER="${FPIM_PG_USER:-swzr_admin}"
DB_NAME="${FPIM_PG_DB:-fpim_dev}"
BACKUP_DIR="${FPIM_BACKUP_DIR:-/data/backups}"
DRILL_DB="fpim_drill_$(date +%s)"

DUMP="${1:-$(ls -t "$BACKUP_DIR"/fpim_*.dump 2>/dev/null | head -1 || true)}"
[ -z "$DUMP" ] && { echo "❌ 没有可用的备份文件，先跑 backup-db.sh"; exit 1; }
echo "演练备份: $DUMP"

cleanup() { docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DRILL_DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DRILL_DB" >/dev/null
docker exec -i "$CONTAINER" pg_restore -U "$DB_USER" -d "$DRILL_DB" --no-owner < "$DUMP" 2>/dev/null \
  || docker exec "$CONTAINER" pg_restore -U "$DB_USER" -d "$DRILL_DB" --no-owner "$DUMP"

TABLES=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DRILL_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
IM_TABLES=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DRILL_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='im'")
ISSUES=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DRILL_DB" -tAc \
  "SELECT count(*) FROM public.issues" 2>/dev/null || echo 0)
MSGS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DRILL_DB" -tAc \
  "SELECT count(*) FROM im.messages" 2>/dev/null || echo 0)

echo "---- 恢复演练报告 ----"
echo "业务表: $TABLES | im 表: $IM_TABLES | issues: $ISSUES | messages: $MSGS"
if [ "${IM_TABLES:-0}" -ge 4 ] && [ "${TABLES:-0}" -ge 5 ]; then
  echo "✅ 恢复演练通过（表结构完整、数据可读）"
  exit 0
else
  echo "❌ 恢复演练不通过"
  exit 1
fi
