# 首问责任平台 — 数据库部署说明

> 2026-08-12

---

## 一、部署步骤

```bash
# 1. 起 PostgreSQL
docker compose up -d

# 2. 建表（首次 baseline 为空操作，后续增量迁移）
#    密码由环境变量 DB_PASSWORD 提供（写在本目录 .env 中，不入库）
alembic upgrade head

# 3. 灌数据（pg_dump 导出，和开发库 100% 一致）
#    seed.sql 由 scripts/generate_seed.py 生成，仓库内只保留一份
cat ../scripts/seed.sql | docker exec -i swzr-pg \
  psql -U swzr_admin -d shouwenzeren
```

执行完三步后，可用 `p0001` ~ `p0300` 任意账号 + 统一初始密码登录（口令由环境变量 `SEED_PASSWORD` 配置，不入库）。

---

## 二、数据库规模

| 项目 | 内容 |
|------|------|
| 数据库 | PostgreSQL 17 + pgvector（容器 `swzr-pg`） |
| Schema | `public`（12 张业务表 + `alembic_version`）、`agent`（15 表）、`rag`（4 表） |

### 各表数据量

| Schema | 表 | 行数 | 说明 |
|--------|-----|------|------|
| public | `departments` | 30 | 4 级：1 → 4 → 10 → 15 |
| public | `users` | 300 | P0001～P0300 |
| public | `contents` | 607 | 604 已发布 + 3 草稿 |
| public | `peer_reviews` | ~200 | 他画像标签 |
| public | `manuals` | 4 | 操作手册 |
| agent | `concepts` | 25 | 技术领域概念 |
| agent | `raw_tags` | 657 | 原始标签 |
| agent | `person_tags` | 1,809 | 人员-标签关联 |
| agent | `tag_concept_map` | 575 | 标签-概念映射 |
| agent | `intent_rules` | 4 | 意图识别规则 |
| agent | `feedback_reason_options` | 6 | 反馈原因选项 |
| agent | `tag_policy` | 10 | 标签策略（按部门） |
| agent | 其余表 | 空 | 运行时写入 |
| rag | 全部表 | 空 | RAG 索引任务运行时写入 |

---

## 三、300 人数据来源：200 + 100

### 200 人：合成数据

- ID：`P0001` ~ `P0200`
- 背景为科技公司组织，字段完整（姓名、手机、部门、岗位、标签、自画像）
- 对应 593 篇模拟文章，作者均引用这批人

### 100 人：state.js 种子数据

- ID：`P0201` ~ `P0300`
- 来自前端 demo 的 `src/state.js`，导入时做了字段映射：ID 格式统一为 `Pxxxx`、部门字符串→外键、标签整合
- 背景为上海银行组织
- 其中 8 人有内容发布（共 12 篇）

### 内容分布

| 用户段 | 人数 | 有内容的作者 | 内容数 |
|--------|------|-------------|--------|
| P0001~P0200 | 200 | 200 | 595 |
| P0201~P0300 | 100 | 8 | 12 |
| **合计** | **300** | **208** | **607** |

---

## 四、Alembic

- `alembic.ini` — `sqlalchemy.url` 中的密码为 `${DB_PASSWORD}`，env.py 自动展开
- `alembic/env.py` — 三 schema 配置，`target_metadata = None`（表由 DDL 直接创建）
- `versions/64c9fe23ca1b_initial_baseline.py` — 空迁移，版本锚点

### 常用命令

```bash
alembic current                          # 查看当前版本
alembic history                          # 迁移历史
alembic revision --autogenerate -m "描述" # 创建新迁移（需先设 target_metadata）
alembic upgrade head                     # 升级到最新
alembic downgrade -1                     # 回滚一步
```

---

## 五、更新 seed.sql

当开发库数据有变更时，重新导出即可：

```bash
docker exec swzr-pg pg_dump -U swzr_admin -d shouwenzeren \
  --no-owner --no-privileges --clean --if-exists \
  > ../scripts/seed.sql
```

导出包含三 schema 全部 DDL + 数据（COPY 格式），`--clean --if-exists` 保证可重复执行。

---

## 六、关键设计决策

1. **三 schema 分层**：`public`（业务表）→ `agent`（Agent 引擎）→ `rag`（知识检索），各司其职
2. **ID 格式统一**：user `P0001~P0300`（P + 4 位），content `A00001~A00607`（A + 5 位）
3. **双源合并**：合成数据作为体力主体，state.js 提供真实银行场景语义
4. **pg_dump 精确复制**：`seed.sql` 由开发库直接导出，部署后逐行一致；修数据→重新导出→提交，单向同步
5. **Alembic 基线先行**：空 migration 做锚点，后续增量迁移从此开始
