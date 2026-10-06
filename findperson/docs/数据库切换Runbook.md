# 数据库切换 Runbook（feature/real-data 分支）

## 双轨现状

| 库 | 内容 | 状态 |
|---|---|---|
| `shouwenzeren_agent` | 合成数据（251账号/23部门/628合成文章/测试会话） | 备份态，随时可回切 |
| `shouwenzeren_newdb` | **真实数据**（208人/32部门/186责任/310文章，2026-08-20 数据库团队 dump + schema 迁移 + 全量索引 v1） | **当前在线** |

现役合成库完整备份：`_newdb/backup/shouwenzeren_agent_synthetic_20260823.dump`（pg_dump 自定义格式）。

## 切换（改配置秒级）

```powershell
powershell -File scripts\switch_db.ps1 -Target newdb   # 切到真实库
powershell -File scripts\switch_db.ps1 -Target old     # 回滚到合成库
```

脚本做的事：改 `agent-service/.env`（PGDATABASE）+ `_repo_push/backend/.env`（DATABASE_URL）→ 重启三服务。

## 新库首次启用完整流程（已执行一遍，供重演参考）

1. **恢复 dump**：`createdb shouwenzeren_newdb` → `psql -f _newdb/seed.sql`（dump 在 GitHub database 分支 `scripts/seed.sql`）
2. **schema 迁移**：`_newdb/migrate_newdb.py`（幂等）
   - 数据库团队版 agent/rag 表挪为 `public.v2bak_*` 保留
   - 重建 agent/rag schema，跑我方 DDL 01-06
   - 补后加列：`agent.person_tags.approval`、`public.peer_reviews.status`
   - v2 数据翻译进我方表（31 raw_tags / 31 concepts / 31 mappings / 363 person_tags）
   - `public.people` 视图 → 我方表设计（users 触发器同步），208 人回填
3. **切 .env**（见切换脚本）
4. **OKF 发布 + 全量索引**：
   ```powershell
   $env:FASTEMBED_CACHE_PATH='C:\python\pycharm\shouwenzeren\deploy_bundle\fastembed_cache'
   .\venv\Scripts\python.exe <repo>\agent-service\scripts\publish_okf.py   # 736 份
   .\venv\Scripts\python.exe <repo>\agent-service\scripts\build_rag_index.py  # 1660 文档/8471 块
   ```
5. **验证**：工号登录（P0001/小写 p0002 均可，口令见 `.env` 的 `SEED_PASSWORD`）→ 问答抽查 → `run_agent_tests.py`（新库 25 轮）

## 新库账号

- 登录：**工号**（P0001~P0208，大小写不敏感），不再支持手机号
- 密码：统一初始口令，由 `.env` 的 `SEED_PASSWORD` 提供（不入库）
- 管理员：P0001 刘成彦 / P0002 冉紫萱 / P0003 聂嘉琛 / P0004（共 4 名）

## 注意事项

- 自测用例已按真实数据重写（`agent_test_cases.py`），合成库用例见 git 历史
- 概念体系为新库 31 个种子概念起步，随真实标签使用重新生长
- `v2bak_*` 表是数据库团队版结构的存档，确认稳定后可删
- fastembed 缓存必须走稳定目录（start_all.ps1 已内置 `FASTEMBED_CACHE_PATH`），Temp 目录缓存被系统清理过两次

## 回滚

1. `switch_db.ps1 -Target old`（秒级回到合成库）
2. 若新库需重建：`DROP DATABASE shouwenzeren_newdb` → 重走"首次启用流程"
