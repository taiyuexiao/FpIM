-- ============================================================
-- 首问责任平台 — 数据库 Schema v1
-- 数据库：PostgreSQL 15+
-- 日期：2026-07-07
-- ============================================================

BEGIN;

-- ============================================================
-- 1. 部门树表
-- ============================================================
CREATE TABLE departments (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,
    level           INT NOT NULL CHECK (level IN (1, 2, 3)),
    parent_id       INT REFERENCES departments(id),
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_dept_parent ON departments(parent_id);
CREATE INDEX idx_dept_level ON departments(level);

-- ============================================================
-- 2. 用户表
-- ============================================================
CREATE TABLE users (
    id               VARCHAR(32) PRIMARY KEY,
    account          VARCHAR(64) UNIQUE NOT NULL,
    phone            VARCHAR(20) UNIQUE,
    password_hash    VARCHAR(256) NOT NULL,
    name             VARCHAR(64) NOT NULL,
    role_type        VARCHAR(16) DEFAULT 'user',      -- admin | user
    department_id    INT REFERENCES departments(id),
    role             VARCHAR(128),
    contact          VARCHAR(64),
    domains          JSONB DEFAULT '[]',
    self_portrait    TEXT,
    completeness     INT DEFAULT 0,
    recommended_count INT DEFAULT 0,
    status           VARCHAR(16) DEFAULT 'active',
    last_login_at    TIMESTAMP,
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_department ON users(department_id);
CREATE INDEX idx_users_domains ON users USING GIN (domains);

-- ============================================================
-- 3. 会话表
-- ============================================================
CREATE TABLE sessions (
    id              VARCHAR(64) PRIMARY KEY,
    user_id         VARCHAR(32) NOT NULL REFERENCES users(id),
    title           VARCHAR(128) DEFAULT '新对话',
    is_active       BOOLEAN DEFAULT TRUE,
    deleted_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sessions_user ON sessions(user_id, deleted_at);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);

-- ============================================================
-- 4. 消息表
-- ============================================================
CREATE TABLE messages (
    id                VARCHAR(64) PRIMARY KEY,
    session_id        VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id           VARCHAR(32) NOT NULL REFERENCES users(id),
    question          TEXT NOT NULL,
    intent            VARCHAR(32),
    domains           JSONB,
    tokens            JSONB,
    confidence        INT,
    action_type       VARCHAR(32),
    action_json       JSONB,
    matches_json      JSONB,
    content_hits_json JSONB,
    reply_text        TEXT,
    confirmed_at      TIMESTAMP,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_messages_intent ON messages(intent);
CREATE INDEX idx_messages_created ON messages(created_at DESC);

-- ============================================================
-- 5. 内容表
-- ============================================================
CREATE TABLE contents (
    id                   VARCHAR(32) PRIMARY KEY,
    owner_id             VARCHAR(32) NOT NULL REFERENCES users(id),
    type                 VARCHAR(32) NOT NULL,
    title                VARCHAR(256) NOT NULL,
    tags                 JSONB DEFAULT '[]',
    summary              TEXT NOT NULL,
    body                 TEXT,
    status               VARCHAR(16) DEFAULT '已发布',       -- 已发布
    deleted_at           TIMESTAMP,                         -- 不为 NULL 即已删除
    pinned               BOOLEAN DEFAULT FALSE,
    published_at         DATE DEFAULT CURRENT_DATE,
    weekly_query_count   INT DEFAULT 0,
    weekly_recommend_count INT DEFAULT 0,
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_contents_owner ON contents(owner_id);
CREATE INDEX idx_contents_type ON contents(type);
CREATE INDEX idx_contents_pinned ON contents(pinned DESC, published_at DESC);
CREATE INDEX idx_contents_tags ON contents USING GIN (tags);

-- ============================================================
-- 6. 反馈表
-- ============================================================
CREATE TABLE feedback (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(32) NOT NULL REFERENCES users(id),
    target_type     VARCHAR(32) NOT NULL,
    target_key      VARCHAR(256) NOT NULL,
    value           VARCHAR(8) NOT NULL CHECK (value IN ('up', 'down')),
    created_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE (user_id, target_type, target_key)
);

CREATE INDEX idx_feedback_target ON feedback(target_type, target_key);
CREATE INDEX idx_feedback_user ON feedback(user_id);

-- ============================================================
-- 7. 推荐日志表
-- ============================================================
CREATE TABLE recommendation_logs (
    id              SERIAL PRIMARY KEY,
    message_id      VARCHAR(64) REFERENCES messages(id),
    session_id      VARCHAR(64) REFERENCES sessions(id),
    user_id         VARCHAR(32) NOT NULL REFERENCES users(id),
    query_text      TEXT NOT NULL,
    person_id       VARCHAR(32) NOT NULL REFERENCES users(id),
    rank            INT NOT NULL,
    score           INT NOT NULL,
    reasons         JSONB DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_rec_log_user ON recommendation_logs(user_id);
CREATE INDEX idx_rec_log_person ON recommendation_logs(person_id);
CREATE INDEX idx_rec_log_created ON recommendation_logs(created_at DESC);

-- ============================================================
-- 8. Query 日志表
-- ============================================================
CREATE TABLE query_logs (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(64) REFERENCES sessions(id),
    message_id      VARCHAR(64) REFERENCES messages(id),
    user_id         VARCHAR(32) NOT NULL REFERENCES users(id),
    query_text      TEXT NOT NULL,
    intent          VARCHAR(32),
    domains         JSONB,
    tokens          JSONB,
    confidence      INT,
    has_result      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_query_log_user ON query_logs(user_id);
CREATE INDEX idx_query_log_created ON query_logs(created_at DESC);
CREATE INDEX idx_query_log_date ON query_logs((created_at::DATE));

-- ============================================================
-- 9. 统计口径定义表
-- ============================================================
CREATE TABLE statistics_definitions (
    id              SERIAL PRIMARY KEY,
    metric_key      VARCHAR(64) UNIQUE NOT NULL,
    metric_name     VARCHAR(64) NOT NULL,
    metric_category VARCHAR(32) DEFAULT 'admin',
    formula         TEXT,
    unit            VARCHAR(16) DEFAULT '次',
    refresh_cron    VARCHAR(32),
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 10. 操作手册表
-- ============================================================
CREATE TABLE manuals (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(256) NOT NULL,
    body            TEXT NOT NULL,
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 11. (辅助) 他画像表
-- ============================================================
CREATE TABLE peer_reviews (
    id              VARCHAR(64) PRIMARY KEY,
    person_id       VARCHAR(32) NOT NULL REFERENCES users(id),
    reviewer_id     VARCHAR(32) NOT NULL REFERENCES users(id),
    reviewer_name   VARCHAR(64),
    review_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    review_text     TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_reviews_person ON peer_reviews(person_id, review_date DESC);

COMMIT;

-- ============================================================
-- Seed Data
-- ============================================================
BEGIN;

-- 部门树 (6 个一级 → 6 个二级 → 12 个三级)
INSERT INTO departments (id, name, level, parent_id, sort_order) VALUES
-- L1
(1,  '数字化建设部',  1, NULL, 1),
(2,  '综合管理部',    1, NULL, 2),
(3,  '风险管理部',    1, NULL, 3),
(4,  '业务管理部',    1, NULL, 4),
(5,  '服务管理部',    1, NULL, 5),
-- L2 (parent → L1)
(6,  '智能能力处',    2, 1, 1),
(7,  '数据治理处',    2, 1, 2),
(8,  '平台运维处',    2, 1, 3),
(9,  '流程运营处',    2, 2, 1),
(10, '知识运营处',    2, 2, 2),
(11, '协同服务处',    2, 2, 3),
(12, '财务保障处',    2, 2, 4),
(13, '组织人事处',    2, 2, 5),
(14, '安全治理处',    2, 3, 1),
(15, '政策研究处',    2, 4, 1),
(16, '服务督导处',    2, 5, 1),
(17, '宣贯推广处',    2, 5, 2),
-- L3 (parent → L2)
(18, '数字能力中心',  3, 6, 1),
(19, '数据治理科',    3, 7, 1),
(20, '应用运维科',    3, 8, 1),
(21, '流程管理室',    3, 9, 1),
(22, '内容运营组',    3, 10, 1),
(23, '综合协同办公室', 3, 11, 1),
(24, '财务资产科',    3, 12, 1),
(25, '人事培训组',    3, 13, 1),
(26, '安全合规科',    3, 14, 1),
(27, '政策研究室',    3, 15, 1),
(28, '质量监督办',    3, 16, 1),
(29, '培训推广组',    3, 17, 1);

-- 重置序列
SELECT setval('departments_id_seq', 29);

-- 用户 (12 人，密码均为 123456 的 bcrypt hash)
-- BCrypt hash for "123456": $2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u
INSERT INTO users (id, account, phone, password_hash, name, department_id, role, contact, domains, self_portrait, completeness, recommended_count) VALUES
('p-chen', 'chenyizhou',  '13800001201', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '陈亦舟', 18, '大模型平台主管', '13800001201',
 '["大模型","Key 申请","模型调用","智能体"]',
 '我负责大模型能力接入、Key 申请流程支持，以及智能体应用建设中的模型侧问题答疑。', 98, 126),

('p-luo', 'luocheng',    '13800001202', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '罗澄',   19, '数据治理专员', '13800001202',
 '["数据治理","指标口径","数据报表","数据质量"]',
 '我主要负责指标口径管理、数据质量核查、报表字段解释和数据治理规范维护。', 92, 103),

('p-song', 'songkewei',  '13800001203', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '宋可为', 20, '系统运维主管', '13800001203',
 '["系统运维","权限申请","账号问题","故障排查"]',
 '我负责内部系统账号开通、权限问题排查、应用故障定位和运行监控。', 88, 91),

('p-tang', 'tangmu',     '13800001204', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '唐沐',   21, '流程审批负责人', '13800001204',
 '["流程审批","制度规范","事项流转","责任边界"]',
 '我维护跨部门流程审批规则、事项流转路径和首问责任边界说明。', 90, 88),

('p-xu', 'xunian',      '13800001205', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '徐念',   22, '内容运营专员', '13800001205',
 '["内容运营","知识发布","标签体系","常见问题"]',
 '我负责平台内容运营、标签体系维护、常见问题归档和个人发布内容整理。', 86, 72),

('p-lin', 'linzhixia',  '13800001206', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '林知夏', 23, '平台用户', '13800001206',
 '["首问责任","协同流转","问题分派"]',
 '我负责首问责任制平台日常使用反馈、问题流转记录和跨部门协同跟进。', 82, 64),

('p-zhou', 'zhouxian',  '13800001207', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '周弦',   26, '安全合规负责人', '13800001207',
 '["安全合规","数据脱敏","审计检查","风险评估"]',
 '我负责系统上线安全评估、数据脱敏规则、审计检查材料准备和安全风险整改跟踪。', 91, 79),

('p-jiang', 'jiangning','13800001208', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '蒋宁',   27, '政策解读专员', '13800001208',
 '["政策解读","政策口径","材料报送","业务咨询"]',
 '我负责政策文件解读、对外材料口径确认、业务报送要求梳理和政策问答沉淀。', 87, 68),

('p-he', 'heyu',        '13800001209', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '何予',   24, '采购与预算主管', '13800001209',
 '["采购流程","预算管理","合同付款","资产登记"]',
 '我负责采购申请、预算占用、合同付款节点、固定资产入库和费用报销规则解释。', 89, 74),

('p-ye', 'yelan',       '13800001210', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '叶澜',   25, '培训与账号协同专员', '13800001210',
 '["培训报名","人员信息","入职离职","账号联动"]',
 '我负责培训报名、人员信息变更、入职离职协同和账号权限联动通知。', 84, 61),

('p-han', 'hanshu',     '13800001211', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '韩书',   28, '督办评价专员', '13800001211',
 '["督办跟踪","服务评价","投诉处理","闭环管理"]',
 '我负责问题督办、服务评价回收、投诉处理记录和跨部门闭环跟踪。', 86, 57),

('p-cai', 'caining',    '13800001212', '$2b$12$LJ3m4ys3Gy0cUQeJqTCPdOM1VBkRkTIeF5Z0kD9hRuH6qktzJhO0u', '蔡宁',   29, '平台推广专员', '13800001212',
 '["平台培训","使用手册","宣贯材料","用户答疑"]',
 '我负责平台培训安排、使用手册编写、宣贯材料维护和一线用户答疑。', 86, 52);

-- 内容 (11 条)
INSERT INTO contents (id, owner_id, type, title, tags, summary, body, pinned, published_at, weekly_query_count, weekly_recommend_count) VALUES
('c-key',     'p-chen', '流程说明', '大模型 Key 申请流程',   '["大模型","Key 申请","权限流程"]',
 '说明大模型 Key 的申请条件、审批节点、调用额度和常见驳回原因。',
 '申请前需明确用途、调用模型、预计额度和责任部门。提交后按部门负责人、平台管理员两级审批。', true,  '2026-07-05', 82, 64),

('c-agent',   'p-chen', '常见问题', '智能体应用常见问题处理说明', '["智能体","模型调用","故障排查"]',
 '整理智能体运行报错、模型无响应、工具调用失败等常见问题的排查方法。',
 '重点排查模型配置、网络连通性、工具权限与输入参数完整性。', true,  '2026-07-04', 77, 59),

('c-report',  'p-luo',  '经验文章', '数据报表口径核对清单', '["数据报表","指标口径","数据质量"]',
 '给出跨部门报表口径核对步骤，帮助定位字段来源、统计周期和计算规则差异。',
 '先确认指标定义，再核对统计周期、数据来源表和口径变更记录。', false, '2026-07-03', 71, 44),

('c-auth',    'p-song', '流程说明', '内部系统权限申请注意事项', '["权限申请","账号问题","系统运维"]',
 '说明系统权限申请材料、审批人选择、账号异常处理和权限回收规则。',
 '所有权限申请需关联岗位职责，离岗后 24 小时内完成权限回收。', false, '2026-07-02', 69, 51),

('c-flow',    'p-tang', '流程说明', '跨部门事项流转路径说明', '["流程审批","事项流转","责任边界"]',
 '解释跨部门事项如何判断首问责任人、协助人和最终处理部门。',
 '首问人先受理，再判断责任归属，如需协同须同步记录协助链路。', true,  '2026-07-01', 74, 56),

('c-security','p-zhou','流程说明', '系统上线安全评估材料清单', '["安全合规","审计检查","风险评估"]',
 '列出系统上线前需要提交的安全评估材料、日志留存要求、脱敏证明和整改闭环记录。',
 '材料需至少包含安全评估表、日志策略、整改清单和责任人确认记录。', false, '2026-06-30', 58, 36),

('c-policy',  'p-jiang','经验文章', '政策口径确认与材料报送说明', '["政策解读","政策口径","材料报送"]',
 '说明政策条款不明确时的确认路径、材料报送格式和对外答复口径留痕要求。',
 '建议先内部形成统一口径，再进行对外答复，并保留确认记录。', false, '2026-06-29', 46, 29),

('c-purchase','p-he',   '流程说明', '采购申请到合同付款流程', '["采购流程","预算管理","合同付款"]',
 '串联采购申请、预算占用、合同审批、验收确认和付款申请的关键节点。',
 '流程关键在预算校验、验收凭证和付款资料完整性。', false, '2026-06-28', 43, 31),

('c-training','p-ye',   '流程说明', '培训报名与人员信息维护流程', '["培训报名","人员信息","入职离职"]',
 '说明培训报名入口、人员信息变更、入职离职联动和账号开通通知路径。',
 '涉及人员信息变更时需同步组织、人事和系统账号三方。', false, '2026-06-27', 38, 24),

('c-supervise','p-han', '经验文章', '首问事项督办和闭环管理办法', '["督办跟踪","闭环管理","服务评价"]',
 '说明首问事项超过响应时限后的督办机制、协同记录要求和闭环评价方式。',
 '超时事项需触发督办，闭环前必须补齐协同说明和结果反馈。', false, '2026-06-26', 35, 22),

('c-training-manual','p-cai','常见问题', '平台培训报名和使用手册获取', '["平台培训","使用手册","用户答疑"]',
 '说明平台培训报名方式、手册下载路径、常见操作问题和宣贯材料更新流程。',
 '新用户可先阅读手册，再报名体验场培训。手册版本按月更新。', true,  '2026-06-25', 62, 48);

-- 操作手册 (4 条)
INSERT INTO manuals (title, body, sort_order) VALUES
('1. 登录与首页',   '支持用户名/手机号 + 密码登录。进入后默认看到首问助手首页，可直接发起提问或进入历史对话。', 1),
('2. 智能问答与历史对话', '每次提问都会生成会话记录，支持搜索、标题修改和直接删除。', 2),
('3. 名片库与内容检索',   '名片库支持一级、二级、三级部门联动筛选；内容检索入口位于个人中心，可按关键词、类型、发布人和置顶状态筛选。', 3),
('4. 个人中心与后台',     '个人中心可维护资料、发布内容、查看操作手册；后台支持查看本周咨询热度、本周推荐热度和近 14 天 Query 趋势。', 4);

-- 统计口径定义 (4 条)
INSERT INTO statistics_definitions (metric_key, metric_name, metric_category, formula, unit, sort_order) VALUES
('people_count',           '参与人员数量', 'admin', 'SELECT COUNT(*) FROM users WHERE status = ''active''', '人', 1),
('content_count',          '发布内容数量', 'admin', 'SELECT COUNT(*) FROM contents WHERE status = ''已发布''', '条', 2),
('domain_count',           '覆盖领域数',   'admin', 'SELECT COUNT(DISTINCT j) FROM users, jsonb_array_elements(domains) j', '个', 3),
('weekly_recommendations', '本周推荐量',   'admin', 'SELECT COUNT(*) FROM recommendation_logs WHERE created_at >= date_trunc(''week'', NOW())', '次', 4);

-- 他画像 (12 条 seed)
INSERT INTO peer_reviews (id, person_id, reviewer_id, reviewer_name, review_date, review_text) VALUES
('review-p-chen-seed', 'p-chen', 'p-lin', '王珂', '2026-07-05', '熟悉大模型平台接入流程，能快速判断 Key、权限、额度和调用报错问题。'),
('review-p-luo-seed',  'p-luo',  'p-lin', '赵敏', '2026-07-03', '对跨部门报表口径很敏感，适合处理数据不一致、指标解释、数据来源追溯等问题。'),
('review-p-song-seed', 'p-song', 'p-lin', '林知夏', '2026-06-29', '处理系统登录、权限、网络和应用异常经验丰富，能给出明确排查路径。'),
('review-p-tang-seed', 'p-tang', 'p-lin', '运营管理员', '2026-06-26', '适合咨询流程卡点、责任归属、审批路径和制度解释类问题。'),
('review-p-xu-seed',   'p-xu',   'p-lin', '王珂', '2026-06-21', '能帮助同事把零散经验整理成可复用内容，适合知识发布和标签治理问题。'),
('review-p-lin-seed',  'p-lin',  'p-chen', '赵敏', '2026-06-16', '熟悉业务咨询入口和首问流转过程，适合反馈平台体验和协同效率问题。'),
('review-p-zhou-seed', 'p-zhou', 'p-lin', '林知夏', '2026-07-05', '对合规材料和审计口径熟悉，适合咨询上线前安全检查、数据出境、日志留存和脱敏问题。'),
('review-p-jiang-seed','p-jiang','p-lin', '运营管理员', '2026-07-03', '适合处理政策条款怎么理解、材料怎么写、对外口径怎么统一等问题。'),
('review-p-he-seed',   'p-he',   'p-lin', '王珂', '2026-06-29', '能快速判断采购事项该走哪个流程、需要哪些附件，以及付款和预算是否满足条件。'),
('review-p-ye-seed',   'p-ye',   'p-lin', '赵敏', '2026-06-26', '适合咨询人员信息维护、培训安排、新员工账号开通和离职权限回收问题。'),
('review-p-han-seed',  'p-han',  'p-lin', '林知夏', '2026-06-21', '适合咨询问题迟迟未响应、责任流转不清、服务评价和投诉反馈类事项。'),
('review-p-cai-seed',  'p-cai',  'p-lin', '运营管理员', '2026-06-16', '适合咨询平台怎么用、培训怎么报名、操作手册在哪里和宣贯材料如何更新。');

COMMIT;
