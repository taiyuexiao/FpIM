#!/usr/bin/env bash
# 数据库每日逻辑备份（04-生产加固技术方案 §2.1）
# crontab: 0 2 * * * /path/to/FpIM/scripts/backup-db.sh >> /var/log/fpim-backup.log 2>&1
set -euo pipefail
CONTAINER="${FPIM_PG_CONTAINER:-swzr-pg}"
DB_USER="${FPIM_PG_USER:-swzr_admin}"
DB_NAME="${FPIM_PG_DB:-fpim_dev}"
BACKUP_DIR="${FPIM_BACKUP_DIR:-/data/backups}"
KEEP_DAYS="${FPIM_BACKUP_KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/fpim_$(date +%F_%H%M).dump"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT"

# 异机拷贝（若配置了挂载点）
if [ -n "${FPIM_BACKUP_MIRROR:-}" ] && [ -d "$FPIM_BACKUP_MIRROR" ]; then
  cp "$OUT" "$FPIM_BACKUP_MIRROR/"
fi

find "$BACKUP_DIR" -name 'fpim_*.dump' -mtime +"$KEEP_DAYS" -delete
echo "[$(date '+%F %T')] 备份完成: $OUT ($(du -h "$OUT" | cut -f1))"
