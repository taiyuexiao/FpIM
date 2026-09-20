"""同步 agent-service 代码到 146 + 服务器概念归并 SQL + 重启 swzr-agent。单连接。"""
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _deploy146_lib import connect, run

LOCAL = Path(__file__).resolve().parents[1]
REMOTE = "/opt/shouwenzeren/agent-service"

SQL = """
DO $$
DECLARE tgt text;
BEGIN
  SELECT concept_id INTO tgt FROM agent.concepts
   WHERE canonical_name='服务器与计算资源' AND status='active' LIMIT 1;
  IF tgt IS NULL THEN RAISE EXCEPTION 'target concept missing'; END IF;
  UPDATE agent.tag_concept_map SET concept_id=tgt
   WHERE concept_id IN (SELECT concept_id FROM agent.concepts
     WHERE canonical_name IN ('服务器/计算资源','服务器资源不足、主机未交付','项目部署-服务器资源','项目服务器'));
  UPDATE agent.concepts SET status='deprecated', valid_to=now()
   WHERE canonical_name IN ('服务器/计算资源','服务器资源不足、主机未交付','项目部署-服务器资源','项目服务器');
  DELETE FROM agent.tag_concept_map WHERE concept_id IN
    (SELECT concept_id FROM agent.concepts WHERE canonical_name='资源');
  UPDATE agent.concepts SET status='deprecated', valid_to=now() WHERE canonical_name='资源';
END $$;
SELECT count(DISTINCT person_id) FROM agent.person_concept_evidence
 WHERE concept_id='concept-server-resource' AND verification_status='active';
"""


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    c = connect()
    try:
        # 1. 远端哈希
        code, out, err = run(c, f"cd {REMOTE} && find app scripts -name '*.py' | xargs sha256sum")
        remote = {}
        for line in out.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                remote[parts[1].strip()] = parts[0]
        # 2. 本地哈希,找差异
        todo = []
        for sub in ("app", "scripts"):
            for p in (LOCAL / sub).rglob("*.py"):
                rel = p.relative_to(LOCAL).as_posix()
                if remote.get(rel) != sha(p.read_bytes()):
                    todo.append((p, rel))
        print(f"diff files: {len(todo)}")
        # 3. SFTP 上传
        sftp = c.open_sftp()
        for p, rel in todo:
            print("  put", rel)
            parts = rel.split("/")[:-1]
            d = REMOTE
            for part in parts:
                d += "/" + part
                try:
                    sftp.stat(d)
                except IOError:
                    sftp.mkdir(d)
            sftp.putfo(io.BytesIO(p.read_bytes()), f"{REMOTE}/{rel}")
        sftp.close()
        # 4. 概念归并 SQL(stdin 传入)
        stdin, stdout, stderr = c.exec_command("sudo -u postgres psql -d shouwenzeren_agent -v ON_ERROR_STOP=1", timeout=60)
        stdin.write(SQL)
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        print("SQL out:", out, err)
        # 5. 重启
        code, out, err = run(c, "systemctl restart swzr-agent && sleep 3 && systemctl is-active swzr-agent")
        print("restart:", out, err, code)
    finally:
        c.close()


main()
