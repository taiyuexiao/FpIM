"""推前端 dist 到 146:本地打包 -> SFTP 上传 -> 远端解包到 /opt/shouwenzeren/frontend。单连接。"""
import io
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _deploy146_lib import connect, run

DIST = Path(__file__).resolve().parents[2] / "dist"
REMOTE_DIR = "/opt/shouwenzeren/frontend"  # nginx root = $REMOTE_DIR/dist


def main():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(DIST, arcname="dist")
    payload = buf.getvalue()
    print(f"tarball {len(payload)//1024} KB")
    c = connect()
    try:
        sftp = c.open_sftp()
        sftp.putfo(io.BytesIO(payload), "/tmp/dist.tar.gz")
        sftp.close()
        code, out, err = run(c, f"cd {REMOTE_DIR} && mv dist dist.bak.$(date +%m%d%H%M) && "
                                f"tar -xzf /tmp/dist.tar.gz -C {REMOTE_DIR} && "
                                f"ls {REMOTE_DIR}/dist | head -5 && rm -f /tmp/dist.tar.gz")
        print(out, err, f"[exit={code}]")
    finally:
        c.close()


main()
