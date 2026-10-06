# 模块：平台加固（既有 findperson 代码的缺陷修复）

> 状态：✅ 本轮修复完成（pytest 42/42 全通过）　｜　最近更新：2026-09-17

## 摘要

为跑通既有测试套件（`backend/tests/`，TST-01 单测 + TST-02 验收）而发现并修复的一批**平台既有缺陷**。
这些不是 FpIM 新功能的 bug，而是 findperson 仓库里"写了但没接线/已过时"的存量问题。
统一记在这里，是因为它们跨 auth/admin/审计多个域，不属于任何单一 FpIM 模块。

## 动机

FpIM 需要在可靠的地基上开发 IM 闭环。既有测试套件能跑起来，才能防止重构把老功能改坏。

## 关键运行时信息

### 双用户表（最重要的既有事实，不知道会踩坑）

| 表 | 角色 |
|---|---|
| `public.user2` | **当前用户主表**（backend ORM `User` 映射它；登录、注册都走它） |
| `public.users` | **老表**，仍被 `contents.owner_id` / `peer_reviews.reviewer_id` 等外键引用；种子用户两表都有（208 人），`/auth/register` 新建的只在 user2 |

- `audit_logs.user_id` 的外键已用 `09_fix_audit_fk.sql` 从 `users` 对齐到 `user2`。
- `contents.owner_id` / `peer_reviews.reviewer_id` 的外键**仍指向 `users`**——新建/临时用户不能当内容 owner 或评价人（测试里已按此规避）。要根治需做外键迁移 + 数据核对，**未做，见待办**。

### 改密链路（本轮从 stub 补成真实现）

- 后端 `POST /api/v1/auth/change-password`：校验旧密码 → 写新 hash。之前是 `return {"message": "ok"}` 的桩。
- 前端 `stores/auth.js.changePassword`：之前只改本地 mock；现在 server 模式下调真实接口。

### 审计链路

- `AuditMiddleware` 本轮才在 `main.py` 注册（写了没接线的存量缺陷）。
- **Starlette 中间件顺序**：后 `add_middleware` 的是外层。审计要读 Auth 注入的 `request.state.user_id`，必须先 add（执行靠内层）。

## Bug 与问题记录

### BUG-001 注册的新账号永远无法登录（已解决）

- 错误行为：WHEN 管理员用 `/auth/register` 建号 THEN 该账号登录返回 401。
- 期望行为：WHEN 注册成功 THEN 系统 SHALL 能用该账号密码登录。
- 不可破坏的行为：WHEN 用种子账号（PXXXX）登录 THEN 系统 SHALL CONTINUE TO 大小写不敏感。
- 根因：登录 `User.id == account.upper()` 单边大写；而 register 生成的 id 是**小写 hex**（`uuid4().hex[:12]`），upper 后对不上。
- 解决方式：两边都 upper（`func.upper(User.id) == account.upper()`）。
- 验证方式：`test_change_password_full_cycle`（注册→改密→新密码登录）通过。

### BUG-002 审计中间件写了但从未注册（已解决）

- 错误行为：WHEN 用户做任何写操作 THEN `audit_logs` 一条不落。
- 期望行为：WHEN 已登录用户做写操作 THEN 系统 SHALL 落一条审计记录。
- 不可破坏的行为：WHEN 未登录请求（登录/健康检查）THEN SHALL CONTINUE TO 不产生审计。
- 根因：`middleware/audit.py` 已实现，但 `main.py` 没 `add_middleware`。
- 解决方式：注册到 AuthMiddleware 内层；并把 `audit_logs.user_id` 外键从老表 `users` 对齐到 `user2`（否则 register 新建用户写审计时被 FK 拒，且中间件 `except: rollback` 静默吞掉——本轮加 BUG-004 记录提醒这类吞异常的写法）。
- 验证方式：`test_audit_logs_capture_write` 通过；手工 PUT /me/profile 后审计表有记录。

### BUG-003 测试套件大面积过时（已解决）

- 错误行为：WHEN 跑 `pytest tests/` THEN 13 failed + 18 error。
- 期望行为：测试 SHALL 反映当前产品行为。
- 不可破坏的行为：产品的既定设计（全局鉴权、注册是管理员动作、PATCH /people 仅管理员）SHALL CONTINUE TO 成立——**改测试对齐产品，不为过测而放松鉴权**。
- 根因：测试写于 integration 分支收紧鉴权之前（假设注册/列表公开），且有多处细节过时（`/me/password` 路径、临时用户按 account 登录、USER_ACCOUNT=p0002 其实是管理员）。
- 解决方式：注册带管理员 token；普通用户 fixture 改用 p0005；临时用户直接 `create_token` 签发；内容/评价测试用种子账号 + 显式清理（避开老表 FK）；`test_path_01` 改为打真实 agent-service（8100 不在则 skip）。
- 验证方式：42/42 通过。

## 已知限制与待办

- [ ] **`contents.owner_id` / `peer_reviews.reviewer_id` 外键仍指向老表 `users`**：注册用户不能当内容 owner。根治 = 迁移外键到 user2 + 核对存量数据，需专项。
- [ ] `config.py` 的 class-based Config 用了 pydantic v2 废弃写法（warning，不影响运行）。
- [ ] 改密后旧 token 仍有效（未做 token 失效）；企业内网可接受，后续可加版本号字段。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-17 | 装 pytest+httpx，跑通既有套件；修 register 登录不一致 / 审计中间件未注册 / 审计外键指向老表；改密从 stub 补全（后端+前端）；测试套件对齐现行鉴权 | BUG-001~003 |
