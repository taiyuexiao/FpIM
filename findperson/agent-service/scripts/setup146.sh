#!/bin/bash
# shouwenzeren 部署脚本(14.103.102.146,Ubuntu 24.04)
# 隔离原则:独立目录 /opt/shouwenzeren、独立端口 8001/8100/8081、独立 DB shouwenzeren_agent、
#           独立 systemd 单元 swzr-backend/swzr-agent、独立 nginx site;不动现有 hr 项目。
set -euo pipefail

APP=/opt/shouwenzeren
PKG=/root/deploy146.tar.gz

echo "== [1/8] 解包到 $APP =="
mkdir -p "$APP"
tar -xzf "$PKG" -C "$APP"
ls "$APP"

echo "== [2/8] 安装 PostgreSQL 18 + pgvector + venv + git =="
if ! command -v psql >/dev/null 2>&1; then
  echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
  curl -fsSL -o /etc/apt/trusted.gpg.d/postgresql.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
  apt-get update -qq
fi
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-18 postgresql-18-pgvector python3-venv python3-pip git

echo "== [3/8] 建角色/库/扩展(幂等) =="
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='swzr'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE swzr LOGIN PASSWORD 'SwzrDeploy2026'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='shouwenzeren_agent'" | grep -q 1 \
  || sudo -u postgres createdb -O swzr shouwenzeren_agent
sudo -u postgres psql -d shouwenzeren_agent -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo "== [4/8] 恢复数据(仅空库时) =="
TBLCOUNT=$(sudo -u postgres psql -d shouwenzeren_agent -tc "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('public','agent','rag')" | tr -d ' ')
if [ "$TBLCOUNT" -lt 5 ]; then
  sudo -u postgres pg_restore -d shouwenzeren_agent --no-owner --no-privileges "$APP/shouwenzeren_agent.dump" || true
  sudo -u postgres psql -d shouwenzeren_agent <<'SQL'
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('public','agent','rag')
  LOOP EXECUTE format('ALTER TABLE %I.%I OWNER TO swzr', r.schemaname, r.tablename); END LOOP;
  FOR r IN SELECT sequence_schema, sequence_name FROM information_schema.sequences WHERE sequence_schema IN ('public','agent','rag')
  LOOP EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO swzr', r.sequence_schema, r.sequence_name); END LOOP;
END$$;
ALTER SCHEMA agent OWNER TO swzr;
ALTER SCHEMA rag OWNER TO swzr;
GRANT USAGE ON SCHEMA public, agent, rag TO swzr;
SQL
  echo "dump restored"
else
  echo "database not empty, skip restore"
fi

echo "== [5/8] Python venv + 依赖 =="
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/backend/requirements.txt" -r "$APP/agent-service/requirements.txt" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple || \
"$APP/venv/bin/pip" install -q -r "$APP/backend/requirements.txt" -r "$APP/agent-service/requirements.txt"

echo "== [6/8] fastembed 缓存软链(双保险) =="
mkdir -p /root/.cache
ln -sfn "$APP/fastembed_cache" /root/.cache/fastembed

echo "== [7/8] systemd 单元 =="
cat > /etc/systemd/system/swzr-backend.service <<'UNIT'
[Unit]
Description=Shouwenzeren Backend (FastAPI 8001)
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/shouwenzeren/backend
ExecStart=/opt/shouwenzeren/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/swzr-agent.service <<'UNIT'
[Unit]
Description=Shouwenzeren Agent Service (FastAPI 8100)
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/shouwenzeren/agent-service
Environment=FASTEMBED_CACHE_PATH=/opt/shouwenzeren/fastembed_cache
ExecStart=/opt/shouwenzeren/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now swzr-backend swzr-agent

echo "== [8/8] nginx site(8081,独立于现有 hr 站点) =="
cat > /etc/nginx/sites-available/shouwenzeren <<'NGX'
server {
    listen 8081;
    server_name _;

    root /opt/shouwenzeren/frontend/dist;
    index index.html;

    location /api/v1/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/agui/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGX
ln -sfn /etc/nginx/sites-available/shouwenzeren /etc/nginx/sites-enabled/shouwenzeren
nginx -t
systemctl reload nginx

echo "== 完成 =="
systemctl is-active swzr-backend swzr-agent
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8100/health
