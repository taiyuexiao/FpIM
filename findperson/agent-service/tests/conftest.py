"""pytest 全局夹具:测试环境隔离(在任何 app 导入前生效)。

1. DB 隔离:测试一律连 shouwenzeren_test(newdb 的全量一次性副本,可随时重建),
   禁止污染运行库 shouwenzeren_newdb(合成夹具残留即源于此)。
   重建(必须走文件,禁止管道——PowerShell 管道会用 GBK 转码毁坏中文):
     pg_dump -U postgres -f newdb_clone.sql shouwenzeren_newdb
     psql -U postgres -c "DROP DATABASE shouwenzeren_test; CREATE DATABASE shouwenzeren_test;"
     $env:PGCLIENTENCODING='UTF8'; psql -U postgres -d shouwenzeren_test -f newdb_clone.sql
2. 离线模型:fastembed 不联网校验(与 start_all.ps1 运行时一致),
   否则 RAG 相关用例会在 HuggingFace 连接上超时。
"""
import os

os.environ["PGDATABASE"] = "shouwenzeren_test"
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH",
    r"C:\python\pycharm\shouwenzeren\deploy_bundle\fastembed_cache",
)
