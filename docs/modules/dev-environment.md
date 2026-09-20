# 模块：开发环境与验证

> 状态：✅ 可用　｜　最近更新：2026-09-17

## 摘要

FpIM 的独立开发环境：**不碰正在运行的 `shouwenzeren_newdb` / 8001**，另建 `fpim_dev` 库与独立前后端实例。
本模块记录端口分配、启动命令、以及本机特有的坑（踩过，别再踩）。

## 动机

`findperson` 原环境（`shouwenzeren_newdb` + backend:8001 + agent-service:8100）是**正在跑的实例**。改造 IM 必然涉及建表（`im` schema）与数据写入，直接在原库上做会污染现有环境、且难以回退。

## 范围与非范围

- 范围内：独立数据库、独立后端端口、独立前端 mode、验证脚本、本机环境坑。
- 明确不做：**多实例/容器化部署编排**（后续独立议题）；**CI 配置**。

## 关键接口与运行时信息

### 端口分配

| 端口 | 用途 | 备注 |
|---|---|---|
| 5432 | PostgreSQL（Docker 容器 `swzr-pg`） | 容器 `pgvector/pgvector:pg17` |
| 8001 | **原有** backend | 不要动 |
| 8100 | **原有** agent-service | 只读只推理，FpIM 复用 |
| **8002** | **FpIM** backend | 指向 `fpim_dev` |
| **5175** | **FpIM** 前端（vite） | 原计划 5174，**被其他项目占用** |

### 数据库

| | |
|---|---|
| 库名 | `fpim_dev`（`swzr_admin` 所有） |
| 来源 | 从 `shouwenzeren_newdb` **1:1 复制**，含 208 人名片库 + 8487 条 RAG 向量块 + `issues`/`issue_events`/`mail_messages` 历史 |
| 扩展 | `pg_trgm` + `vector`（**无中文分词扩展**，见后续优化） |
| 连接串 | `postgresql://swzr_admin@localhost:5432/fpim_dev`（**口令不入库**，由 `PGPASSWORD` 提供，见 `findperson/backend/.env`） |

复制方式（容器内 `pg_dump | psql`，不落中间文件）：

```bash
docker exec swzr-pg sh -c \
  "pg_dump -U swzr_admin -d shouwenzeren_newdb --no-owner --no-acl | psql -U swzr_admin -d fpim_dev -q"
```

### 测试账号

| 账号 | 口令 | 说明 |
|---|---|---|
| `P0004` | 见 `backend/.env` 的 `SEED_PASSWORD` | 师沛琳，自测默认用 A |
| `P0005` / `P0006` / `P0007` | 同上 | 自测用 B / C / D |

> seed 账号口令统一，**不入库**：由 `.env` 的 `SEED_PASSWORD` 提供（`backend/tests/conftest.py` 与自测脚本都读这一项）。

### 项目位置（2026-09-17 起：代码是独立副本）

```
~/projects/mine/FpIM/              ← 项目根 = git 仓库根
├── README.md                      ← 项目入口
├── docs/                          ← 全部文档
│   ├── PROJECT.md                 ← 主文档（模块索引 / 变更日志）
│   ├── 01-产品需求文档-PRD.md / 02-技术方案文档.md / 03-前端设计文档.md
│   ├── 重构方案-IM化与问题闭环.md
│   ├── modules/                   ← 模块文档（本目录）
│   └── research/                  ← 前期调研与原始方案（归档）
├── prototype/                     ← 高保真原型 + 截图
├── findperson/                    ← 代码（从原 findperson 复制）
└── .workbuddy/memory/             ← 项目记忆

~/projects/mine/findperson/        ← 原项目：保持独立，已不再使用
```

**为什么是"复制"而不是"直接在原仓库开发"**：FpIM 是独立新项目，findperson 也是独立项目，两者不该合到一起。

**复制时排除了什么、为什么**：

| 排除项 | 体积 | 原因 |
|---|---|---|
| `backend/venv` | 95M | ⚠️ **venv 不可搬迁**——`bin/pip` 的 shebang 硬编码旧绝对路径，复制后在新项目里装包会**静默装回旧项目** |
| `agent-service/venv` | 243M | 同上；且 agent-service 复用原实例（:8100），副本不需要独立 venv |
| `.git` | 26M | 新项目要独立历史（复制时的 `.git` 是原仓库的，已弃用；现仓库由 `FpIM/` 根 `git init` 建立） |

保留：全部源码、配置（含 `.env` / `.env.fpim`）、`node_modules`、数据库脚本、文档。复制后 13015 个文件与源完全一致。

### 依赖重建

```bash
cd /Users/shipeilin/projects/mine/FpIM/findperson/backend
uv venv --python 3.12.14 venv                 # 与原环境同版本，避免漂移
VIRTUAL_ENV=$PWD/venv uv pip install -r requirements.txt
cd .. && rm -rf node_modules/.vite            # 清掉含旧绝对路径的 vite 缓存
```

> `uv` 在 `~/.local/bin/uv`；原 venv 用的是 uv 装的 CPython **3.12.14**。

### 启动

```bash
# 1) 后端（独立实例）—— 口令不入库，从 backend/.env 取
cd /Users/shipeilin/projects/mine/FpIM/findperson/backend
DATABASE_URL="postgresql://swzr_admin@localhost:5432/fpim_dev" \
  PGPASSWORD="<数据库口令，见 backend/.env>" \
  FPIM_FILE_ROOT=/tmp/fpim-files \
  CORS_ORIGINS="http://localhost:5173,http://localhost:5174,http://localhost:5175" \
  venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# 2) 前端（--mode fpim 读 .env.fpim，把 API 指向 8002）
cd /Users/shipeilin/projects/mine/FpIM/findperson
node node_modules/vite/bin/vite.js --mode fpim --port 5175 --host 127.0.0.1 --strictPort
```

`.env.fpim` 只在 `--mode fpim` 时生效，`VITE_API_BASE_URL=http://127.0.0.1:8002/api/v1`。

### 验证

```bash
cd backend
venv/bin/python scripts/fpim_smoke_http.py --reset   # 37 项（含清库；§14~21 为立项闭环场景）
venv/bin/python scripts/fpim_smoke_ws.py             # 13 项
```

`--reset` 会清 `im.*` 并对 `issues` 的会话/留痕字段做复位——**只对开发库使用**。

### 关键文件

- `backend/scripts/fpim_smoke_http.py` / `fpim_smoke_ws.py` —— 自测脚本（HTTP `--reset` 可清库）
- `.env.fpim` —— 前端独立环境变量
- `agent-service/scripts/ddl/08_im.sql` —— IM 建表（由后端启动自检自动应用）

## 设计决策与假设

- **另建库而非直连原库**：改造要建 `im` schema 并写数据，原库是运行中实例，污染后无法干净回退。
- **前端用 vite mode 而非改 `.env`**：`--mode fpim` 隔离配置，默认启动方式的行为完全不变。
- **`FPIM_FILE_ROOT` 指到 `/tmp/fpim-files`**：开发期附件不入正式存储目录。
- **代码用"独立副本"而非在原仓库演进**（2026-09-17 决策变更，原 Q1=A 作废）：FpIM 与 findperson 是两个独立项目，合到一起不好。原仓库保持原样，副本独立起历史。
- **排除 `venv` 而不排除 `node_modules`**：`node_modules` 里的符号链接是相对的、可搬迁（只需清 `.vite` 缓存）；`venv` 则**会指向旧路径**，属于"看起来成功、实际装错地方"的静默错误，必须重建。

## Bug 与问题记录

### BUG-001 Docker 的 LinuxKit VM 死掉，导致"能连上 5432 但查询卡死"（2026-09-17，已解决）

- 错误行为：WHEN 访问 PG THEN TCP 能连上 5432，但查询无响应；后端登录接口 8 秒无返回。
- 期望行为：WHEN 同一请求 THEN 系统 SHALL 正常返回查询结果。
- 不可破坏的行为：WHEN 重启 Docker THEN 系统 SHALL CONTINUE TO 保留 `Docker.raw` 里的数据卷（不得丢数据）。
- 根因：`~/Library/Containers/com.docker.docker/Data/log/host/com.docker.backend.log` 报
  `still dialing 192.168.65.7:2376 ... no route to host`、`Cannot connect to the Docker daemon`——
  **VM 已死，但宿主机的 5432 转发代理进程还在**，于是表现为"连得上、查不动"。宿主网络正常。
- 解决方式：`docker desktop restart`（数据在 `Docker.raw`，不丢），等 VM 起来后 `swzr-pg` 自动恢复。
- 验证方式：重启后能查到 `people=208`、`issues=3`、`issue_events=13`、`mail_messages=43`；后端登录恢复。

### BUG-002 前端 5174 起不来，访问返回 404（2026-09-17，已解决）

- 错误行为：WHEN 访问 `http://127.0.0.1:5174/` THEN 返回 404，连 `/@vite/client` 都 404。
- 期望行为：WHEN 访问前端 THEN 系统 SHALL 返回应用页面。
- 不可破坏的行为：WHEN 启动 FpIM 前端 THEN 系统 SHALL CONTINUE TO 不干扰其他项目已占用的端口。
- 根因：5174 已被**另一个项目**的 vite 进程占用（`shbank/shouwenzeren/node_modules/.bin/vite`，cwd 指向回收站目录），我们的实例压根没绑上端口。
- 解决方式：改用 **5175**，并加 `--strictPort`（端口被占直接失败，而不是静默换端口）；同步把 5175 加进后端的 `CORS_ORIGINS`。
- 验证方式：`curl` `/` `/index.html` `/src/main.js` 均 200；无头浏览器截图能看到登录页。

### BUG-003 本地回环请求被沙箱代理拦成 502（2026-09-17，已解决）

- 错误行为：WHEN 用 urllib 请求 `http://127.0.0.1:8002` THEN 收到 502。
- 期望行为：WHEN 同一请求 THEN 系统 SHALL 直连回环地址。
- 不可破坏的行为：WHEN 请求公网 THEN 系统 SHALL CONTINUE TO 走环境既有代理配置。
- 根因：运行环境注入了 `HTTP_PROXY`，urllib 默认会把回环请求也交给代理。
- 解决方式：自测脚本里 `urllib.request.ProxyHandler({})` 显式绕过；`curl` 侧加 `--noproxy '*'`。
- 验证方式：脚本从 502 变为正常 200。

### BUG-004 `JWT_SECRET` 在 `.env.example` 里与真实密钥同值（2026-09-17，已解决）

- 错误行为：WHEN 任何人拿到本仓库 THEN 可用 `.env.example` 里的 `JWT_SECRET` 伪造任意用户的登录令牌。
- 期望行为：WHEN `.env.example` 存在于仓库 THEN 系统 SHALL 只含 `CHANGE_ME` 占位符，不含任何真实凭据。
- 不可破坏的行为：WHEN 环境变量缺失 THEN 系统 SHALL CONTINUE TO 明确报错提示（而不是静默用硬编码默认值连库/签发）。
- 根因：原项目把真实密钥同时写进了 `.env` 和 `.env.example`（复制配置时未脱敏）。
- 解决方式：① 轮换真实 `JWT_SECRET`（`openssl rand -hex 32`，副作用：旧登录态全部失效）② 重写 `.env.example` 为完整占位模板 ③ `config.py` 默认值改为无凭据占位。
- 验证方式：`git grep` 全历史无真实密钥；新 token 签发与校验正常（回归 32 项通过）。

### BUG-005 前端口令被 Vite 构建期内联进 JS bundle（2026-09-17，已解决）

- 错误行为：WHEN `VITE_DEMO_PASSWORD` 写在会被生产构建读取的 `.env` THEN `npm run build` 产物 `dist/assets/LoginView-*.js` 中可直接搜到口令明文。
- 期望行为：WHEN 生产构建 THEN 系统 SHALL 产物中不含任何口令。
- 不可破坏的行为：WHEN `--mode fpim` 开发模式 THEN 系统 SHALL CONTINUE TO 正常加载快捷登录口令（开发体验不变）。
- 根因：Vite 把 `import.meta.env.VITE_*` 在**构建期**静态替换为字面量——前端的任何"配置值"最终都会下发到浏览器，**前端口令本质上藏不住**。
- 解决方式：双层隔离——① 口令只放 `.env.fpim.local`（Vite `.local` 约定，仅 `--mode fpim` 加载，生产构建不读）② 代码用 `import.meta.env.DEV` 再兜一层。
- 验证方式：生产构建后 `dist/` 全文搜不到口令；`loadEnv('fpim')` 能取到、`loadEnv('production')` 取不到。

### BUG-006 用 ripgrep 做全仓凭据扫描，漏掉 `.workbuddy/`（2026-09-17，已解决）

- 错误行为：WHEN 用 ripgrep（Grep 工具默认参数）扫全仓口令 THEN 报告"无匹配"，但 `.workbuddy/memory/` 里的入库文件中实际存在明文口令。
- 期望行为：WHEN 做敏感信息扫描 THEN 扫描 SHALL 覆盖包括隐藏目录在内的全部文件。
- 不可破坏的行为：WHEN 日常代码检索 THEN 系统 SHALL CONTINUE TO 默认跳过隐藏目录（这是合理默认，只有敏感扫描是例外）。
- 根因：ripgrep 默认忽略隐藏文件/目录（`.gitignore` 语义的扩展），而 `.workbuddy/` 恰好是隐藏目录且已被 git 跟踪。
- 解决方式：敏感扫描一律用 `grep -rnE`（不跳隐藏）或显式指定隐藏路径；本轮已把记忆文件中的口令改为指针（"见 backend/.env"）。
- 验证方式：`grep -rnE` 全仓扫描仅剩 `.env` 系列命中（均不入库）。

### BUG-007 `findperson/.gitignore` 混合编码导致 14 行规则静默失效（2026-09-17，已解决）

- 错误行为：WHEN 该文件第 9~22 行（`venv/`、`.pytest_cache/`、`*.log` 等 14 条规则）以 UTF-16 字节存储 THEN git 按字节匹配，**这些规则全部不生效**，对应文件会被误提交。
- 期望行为：WHEN `.gitignore` 声明规则 THEN 规则 SHALL 实际生效。
- 不可破坏的行为：WHEN 重写该文件 THEN SHALL CONTINUE TO 保留原有全部忽略语义（含 `/方案/` 等中文路径规则）。
- 根因：历史上某次编辑把部分行存成了 UTF-16（文件整体呈"UTF-8 + UTF-16 混合"，被 `file` 判为 binary/data）。
- 解决方式：重写为纯 UTF-8 + LF，并补 `*.local` / `.env.*.local` 约定；同时修掉 `agent-service/.gitignore` 的一行 GBK 注释、`backend/README.md` 的 UTF-16（正文乱码不可还原，已加说明头）。
- 验证方式：`git check-ignore` 逐一验证 `node_modules`/`venv`/`.env`/`*.local` 全部生效；全仓无非 UTF-8 文本文件。

## 已知限制与待办

- [x] ~~`backend/venv`（重建后）里也没有 `pytest`~~ → 已用 uv 装 `pytest` + `httpx`，既有套件 `backend/tests/` 已跑通（42/42）。跑法：`DATABASE_URL=...fpim_dev PGPASSWORD=... venv/bin/python -m pytest tests/ -q`（**必须指向 fpim_dev，别碰原库**）。套件修复过程见 [platform-hardening.md](platform-hardening.md)。
- [x] ~~两个 16M 的 `seed.sql` 完全重复~~ → **已删除副本** `findperson/database/scripts/seed.sql`，只保留 `findperson/scripts/seed.sql`（`generate_seed.py` 的产物）。同时修正了 `fix_content_seed.py`（原本会同时写两个路径）与 `database/README.md` 的引用。**注意：原先判断"无代码引用"是错的**——只搜了拼接好的字符串，漏了路径拼接写法。
- [ ] **开发服务不保证长期存活**：后台方式启动后，若中间跑了重活（大文件 git 操作、批量复制等）进程可能被回收，表现为端口空出、请求 `000`/连接被拒。**开工前先探活**。
- [ ] 原 `~/projects/mine/findperson` 的 1713 项未提交改动**保持原样未动**；若日后清理，须先确认副本已提交。
- [ ] 本机**没有 `psql` 客户端**，`docker` CLI 有 API 版本不兼容报错（500）→ 统一走 `docker exec swzr-pg psql` 或 Python 驱动。
- [ ] 中文字段检索依赖 `pg_trgm`，无分词扩展（不阻塞，见 `docs/PROJECT.md` 后续优化）。
- [ ] 无自动化"一键起全栈"脚本，目前靠手工两条命令。
- [ ] 副本目录名仍是 `findperson`（沿用原名，便于辨认来源）；若想让新项目名字更独立，`mv` 即可，不影响任何配置。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-17 | 建 `fpim_dev` 并从原库 1:1 复制；确定 8002 / 5175 端口分配；新增 `.env.fpim` | FpIM：环境隔离 |
| 2026-09-17 | 自测脚本固化进 `backend/scripts/`（含 `--reset` 清库） | FpIM：可重复验证 |
| 2026-09-17 | 修 BUG-001（Docker VM 死掉）、BUG-002（端口占用）、BUG-003（代理拦截） | BUG-001~003 |
| 2026-09-17 | **代码独立化**：复制为 `findperson/`（排除 venv/.git），uv 重建 venv（3.12.14）；开发服务切到副本，回归 32 项全通过 | FpIM：项目独立 |
| 2026-09-17 | **仓库提到项目根**：移除 `findperson/.git`，在 `FpIM/` 根 `git init` + 首次提交（e505fd8，1218 文件 / 45M 工作区） | FpIM：统一版本化 |
| 2026-09-17 | **凭据脱敏**：口令/密钥全部改为环境变量注入；轮换 `JWT_SECRET`；`.env.example` 重写为占位模板；生产构建不再含前端口令。回归 32 项全通过 | FpIM：安全治理 |
| 2026-09-17 | **统一文本编码**：`findperson/.gitignore` 原为混合编码（14 行 UTF-16 规则失效）+ 全仓唯一 CRLF，已重写；`backend/README.md` 由 UTF-16 转 UTF-8 并脱敏；`agent-service/.gitignore` 混编码行修正 | FpIM：规范化 |
| 2026-09-17 | **删除重复 seed**：`database/scripts/seed.sql`（16M） | FpIM：瘦身 |

### BUG-008 .env 的 DATABASE_URL 指向原库导致测试数据写穿（2026-09-18，已解决）

- 错误行为：WHEN 某次后端启动从 `.env` 读配置（而非显式传 `DATABASE_URL=...fpim_dev`）THEN 后端连上了**原项目的 `shouwenzeren_newdb`**，冒烟测试的 IM 数据（会话/消息/chat 问题/沉淀候选）全部写进原库。
- 期望行为：WHEN 用任何入口启动后端 THEN 系统 SHALL 连 `fpim_dev`。
- 不可破坏的行为：WHEN 以后改 `.env` THEN 系统 SHALL CONTINUE TO 在 DSN 缺口令时由 `PGPASSWORD` 注入（`core/database.py` 的 `_with_password`）。
- 根因：`backend/.env` 是从原项目 1:1 复制的，`DATABASE_URL` 仍指向 `shouwenzeren_newdb` **且 DSN 内联了口令**（违反我们自己的"DSN 不带口令"约定）；此前每次启动都显式 export 覆盖，唯独一次从 .env 读就踩中。另外 `config.py` 的默认值也是 `shouwenzeren_newdb`，双保险都错。
- 解决方式：① `.env` 的 DSN 改为 fpim_dev 且去掉内联口令；② `config.py` 默认值改 fpim_dev + 新增 `PGPASSWORD` 字段；③ `database.py` 装配时把 `PGPASSWORD` 注入无口令 DSN；④ 清掉写进 newdb 的测试数据（im 四表 TRUNCATE + source='chat' 的 issues/events/candidates 删除）。
- 验证方式：回归 57+13+42 全过；newdb 的 im.conversations=0、chat 问题=0 且回归后仍为 0。
- **教训**：同一项目两份库（原库/开发库）时，"默认配置指向哪个库"是最高危的配置项，必须让**所有入口的默认值都指向开发库**。
