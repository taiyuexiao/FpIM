// ═══════════════════════════════════════════════════════════════════════════
// state.js — 首问必答平台 数据层
// ═══════════════════════════════════════════════════════════════════════════
//
// 包含：localStorage 键名、种子人员、部门层级、推荐次数、种子内容、
//       操作手册章节、领域词典、当前用户、评价日期、导航项、工具函数
// ═══════════════════════════════════════════════════════════════════════════

// ── localStorage 键名 ──────────────────────────────────────────────────────
export const STORAGE_KEYS = {
  people: "firstResponsibilityDemo.people",
  departments: "firstResponsibilityDemo.departments",
  roles: "firstResponsibilityDemo.roles",
  profile: "firstResponsibilityDemo.profile",
  content: "firstResponsibilityDemo.content",
  peerReviews: "firstResponsibilityDemo.peerReviews",
  deletedPeerReviews: "firstResponsibilityDemo.deletedPeerReviews",
  sessions: "firstResponsibilityDemo.sessions",
  agui: "firstResponsibilityDemo.agui",
  interactions: "firstResponsibilityDemo.interactions",
  auth: "firstResponsibilityDemo.auth",
  feedback: "firstResponsibilityDemo.feedback",
  drafts: "firstResponsibilityDemo.drafts",
  organizationSchemaVersion: "firstResponsibilityDemo.organizationSchemaVersion",
};

// ── 种子人员 ───────────────────────────────────────────────────────────────
// id / name / department / role / contact / domains / selfPortrait / peerPortrait / completeness
export const seedPeople = [
  {
    id: "p-chen", name: "陈亦舟", department: "数字能力中心", role: "大模型平台主管",
    contact: "13800001201",
    domains: ["大模型", "Key 申请", "模型调用", "智能体"],
    selfPortrait: "我负责大模型能力接入、Key 申请流程支持，以及智能体应用建设中的模型侧问题答疑。",
    peerPortrait: "熟悉大模型平台接入流程，能快速判断 Key、权限、额度和调用报错问题。",
    completeness: 98,
  },
  {
    id: "p-luo", name: "罗澄", department: "数据治理科", role: "数据治理专员",
    contact: "13800001202",
    domains: ["数据治理", "指标口径", "数据报表", "数据质量"],
    selfPortrait: "我主要负责指标口径管理、数据质量核查、报表字段解释和数据治理规范维护。",
    peerPortrait: "对跨部门报表口径很敏感，适合处理数据不一致、指标解释、数据来源追溯等问题。",
    completeness: 92,
  },
  {
    id: "p-song", name: "宋可为", department: "应用运维科", role: "系统运维主管",
    contact: "13800001203",
    domains: ["系统运维", "权限申请", "账号问题", "故障排查"],
    selfPortrait: "我负责内部系统账号开通、权限问题排查、应用故障定位和运行监控。",
    peerPortrait: "处理系统登录、权限、网络和应用异常经验丰富，能给出明确排查路径。",
    completeness: 88,
  },
  {
    id: "p-tang", name: "唐沐", department: "综合管理部", role: "综合管理部负责人",
    contact: "13800001204",
    domains: ["流程审批", "制度规范", "事项流转", "责任边界"],
    selfPortrait: "我负责综合管理部的协同服务、流程运营和资源统筹，推进下级部门明确首问责任边界。",
    peerPortrait: "擅长统筹跨部门事项、流程协同和服务机制建设。",
    completeness: 90,
  },
  {
    id: "p-xu", name: "徐念", department: "内容运营组", role: "内容运营专员",
    contact: "13800001205",
    domains: ["内容运营", "知识发布", "标签体系", "常见问题"],
    selfPortrait: "我负责平台内容运营、标签体系维护、常见问题归档和个人发布内容整理。",
    peerPortrait: "能帮助同事把零散经验整理成可复用内容，适合知识发布和标签治理问题。",
    completeness: 86,
  },
  {
    id: "p-lin", name: "林知夏", department: "协同服务处", role: "协同服务处负责人",
    contact: "13800001206",
    domains: ["首问责任", "协同流转", "问题分派"],
    selfPortrait: "我负责协同服务处的首问受理、事项流转和服务体验统筹，并推动下级部门持续完善服务职责。",
    peerPortrait: "熟悉业务咨询入口和首问流转过程，适合反馈平台体验和协同效率问题。",
    completeness: 82,
  },
  {
    id: "p-zhou", name: "周弦", department: "安全合规科", role: "安全合规负责人",
    contact: "13800001207",
    domains: ["安全合规", "数据脱敏", "审计检查", "风险评估"],
    selfPortrait: "我负责系统上线安全评估、数据脱敏规则、审计检查材料准备和安全风险整改跟踪。",
    peerPortrait: "对合规材料和审计口径熟悉，适合咨询上线前安全检查、数据出境、日志留存和脱敏问题。",
    completeness: 91,
  },
  {
    id: "p-jiang", name: "蒋宁", department: "政策研究室", role: "政策解读专员",
    contact: "13800001208",
    domains: ["政策解读", "政策口径", "材料报送", "业务咨询"],
    selfPortrait: "我负责政策文件解读、对外材料口径确认、业务报送要求梳理和政策问答沉淀。",
    peerPortrait: "适合处理政策条款怎么理解、材料怎么写、对外口径怎么统一等问题。",
    completeness: 87,
  },
  {
    id: "p-he", name: "何予", department: "财务资产科", role: "采购与预算主管",
    contact: "13800001209",
    domains: ["采购流程", "预算管理", "合同付款", "资产登记"],
    selfPortrait: "我负责采购申请、预算占用、合同付款节点、固定资产入库和费用报销规则解释。",
    peerPortrait: "能快速判断采购事项该走哪个流程、需要哪些附件，以及付款和预算是否满足条件。",
    completeness: 89,
  },
  {
    id: "p-ye", name: "叶澜", department: "人事培训组", role: "培训与账号协同专员",
    contact: "13800001210",
    domains: ["培训报名", "人员信息", "入职离职", "账号联动"],
    selfPortrait: "我负责培训报名、人员信息变更、入职离职协同和账号权限联动通知。",
    peerPortrait: "适合咨询人员信息维护、培训安排、新员工账号开通和离职权限回收问题。",
    completeness: 84,
  },
  {
    id: "p-han", name: "韩书", department: "质量监督办", role: "督办评价专员",
    contact: "13800001211",
    domains: ["督办跟踪", "服务评价", "投诉处理", "闭环管理"],
    selfPortrait: "我负责问题督办、服务评价回收、投诉处理记录和跨部门闭环跟踪。",
    peerPortrait: "适合咨询问题迟迟未响应、责任流转不清、服务评价和投诉反馈类事项。",
    completeness: 86,
  },
  {
    id: "p-cai", name: "蔡宁", department: "培训推广组", role: "平台推广专员",
    contact: "13800001212",
    domains: ["平台培训", "使用手册", "宣贯材料", "用户答疑"],
    selfPortrait: "我负责平台培训安排、使用手册编写、宣贯材料维护和一线用户答疑。",
    peerPortrait: "适合咨询平台怎么用、培训怎么报名、操作手册在哪里和宣贯材料如何更新。",
    completeness: 86,
  },
];

// 演示组织规模：10 位负责人 + 50 位成员。负责人职务独立于负责人身份。
seedPeople.splice(10);
seedPeople[0].department = "数字化建设部";
seedPeople[0].role = "部门经理";
const clerkNames = [
  "王珂", "赵敏", "周航", "吴菲", "郑然", "冯昕", "褚然", "卫澜", "沈言", "韩月",
  "杨帆", "朱宁", "秦川", "尤佳", "许墨", "何川", "吕晴", "施晨", "张悦", "孔维",
  "曹宇", "严清", "华宁", "金晨", "魏安", "陶然", "姜雪", "戚可", "谢宁", "邹远",
  "喻航", "柏然", "水清", "窦宁", "章悦", "云帆", "苏杭", "潘宁", "葛星", "奚晨",
  "范可", "彭程", "郎宁", "鲁明", "昌宇", "马欣", "苗宁", "凤扬", "花语", "方正",
];
seedPeople.push(...clerkNames.map((name, index) => {
  const departmentHead = seedPeople[index % 10];
  return {
    id: `p-clerk-${index + 1}`,
    name,
    department: departmentHead.department,
    role: "专员",
    contact: `1380000${String(1301 + index).padStart(4, "0")}`,
    domains: departmentHead.domains.slice(0, 2),
    selfPortrait: `协助处理${departmentHead.department}相关的日常咨询、事项流转和材料整理。`,
    peerPortrait: "能够配合完成部门日常咨询和协同事项跟进。",
    completeness: 72 + (index % 20),
  };
}));

// 账号与组织数据分离：个人资料不再承担部门、岗位和系统角色的维护职责。
const departmentLeads = {
  数字化建设部: "p-chen", 数据治理科: "p-luo", 应用运维科: "p-song", 综合管理部: "p-tang",
  内容运营组: "p-xu", 协同服务处: "p-lin", 安全合规科: "p-zhou", 政策研究室: "p-jiang",
  财务资产科: "p-he", 人事培训组: "p-ye",
};

// ── 部门树 ───────────────────────────────────────────────────────────────
// parentId 允许组织架构按实际情况无限向下扩展，path 仅用于展示和筛选。
const departmentPaths = {
  "上海银行": ["上海银行"],
  "数字化建设部": ["上海银行", "数字化建设部"],
  "智能能力处": ["上海银行", "数字化建设部", "智能能力处"],
  "数字能力中心": ["上海银行", "数字化建设部", "智能能力处", "数字能力中心"],
  "数据治理处": ["上海银行", "数字化建设部", "数据治理处"],
  "数据治理科": ["上海银行", "数字化建设部", "数据治理处", "数据治理科"],
  "平台运维处": ["上海银行", "数字化建设部", "平台运维处"],
  "应用运维科": ["上海银行", "数字化建设部", "平台运维处", "应用运维科"],
  "综合管理部": ["上海银行", "综合管理部"],
  "流程运营处": ["上海银行", "综合管理部", "流程运营处"],
  "流程管理室": ["上海银行", "综合管理部", "流程运营处", "流程管理室"],
  "知识运营处": ["上海银行", "综合管理部", "知识运营处"],
  "内容运营组": ["上海银行", "综合管理部", "知识运营处", "内容运营组"],
  "协同服务处": ["上海银行", "综合管理部", "协同服务处"],
  "综合协同办公室": ["上海银行", "综合管理部", "协同服务处", "综合协同办公室"],
  "协同受理组": ["上海银行", "综合管理部", "协同服务处", "协同受理组"],
  "事项流转组": ["上海银行", "综合管理部", "协同服务处", "事项流转组"],
  "服务体验组": ["上海银行", "综合管理部", "协同服务处", "服务体验组"],
  "知识支持组": ["上海银行", "综合管理部", "协同服务处", "知识支持组"],
  "渠道运营组": ["上海银行", "综合管理部", "协同服务处", "渠道运营组"],
  "财务保障处": ["上海银行", "综合管理部", "财务保障处"],
  "财务资产科": ["上海银行", "综合管理部", "财务保障处", "财务资产科"],
  "组织人事处": ["上海银行", "综合管理部", "组织人事处"],
  "人事培训组": ["上海银行", "综合管理部", "组织人事处", "人事培训组"],
  "风险管理部": ["上海银行", "风险管理部"],
  "安全治理处": ["上海银行", "风险管理部", "安全治理处"],
  "安全合规科": ["上海银行", "风险管理部", "安全治理处", "安全合规科"],
  "业务管理部": ["上海银行", "业务管理部"],
  "政策研究处": ["上海银行", "业务管理部", "政策研究处"],
  "政策研究室": ["上海银行", "业务管理部", "政策研究处", "政策研究室"],
};

export const departmentHierarchyMap = departmentPaths;

export const seedDepartments = Object.entries(departmentPaths).map(([name, path]) => {
  const parentPath = path.slice(0, -1);
  const parentName = parentPath.at(-1);
  return {
    id: `dept-${name}`,
    name,
    parentId: parentName ? `dept-${parentName}` : "",
    path,
    leaderId: departmentLeads[name] || "",
    responsibility: `负责${name}相关事项的受理、协同与业务支撑，明确首问责任边界并持续维护服务指引。`,
  };
});

const generatedLeaderNames = [
  "沈嘉言", "顾南乔", "陆知衡", "许清和", "程予安", "苏明澈", "谢闻川", "顾念之", "江叙白", "温书言",
  "秦知远", "周静宜", "林墨言", "宋清越", "叶承安", "方予宁", "陆行舟", "沈昭然", "许望舒", "顾行简",
  "周亦安", "程书言", "林清越", "苏景行", "江知夏", "谢安然", "陆昭明", "温予安", "秦书衡", "宋知远",
];
const generatedMemberNames = [
  "陈思远", "李若宁", "王书涵", "赵嘉禾", "吴明轩", "郑知意", "冯予安", "褚清言", "卫景然", "沈之遥",
  "韩书宁", "杨知行", "朱予希", "秦乐言", "尤安然", "何清越", "吕明澈", "施念安", "张书怡", "孔景行",
  "曹若溪", "严嘉言", "华清妍", "金予安", "魏昭然", "陶书言", "姜知远", "戚安宁", "谢明澈", "邹清和",
];

// 每个演示部门至少有一名负责人和一名成员，便于完整展示组织、上级和名片筛选。
seedDepartments.forEach((department, index) => {
  if (!department.leaderId) {
    const leaderId = `p-dept-leader-${index + 1}`;
    department.leaderId = leaderId;
    seedPeople.push({
      id: leaderId,
      name: department.name === "上海银行" ? "董事长" : generatedLeaderNames[index],
      department: department.name,
      departmentPath: department.path.slice(),
      role: department.name === "上海银行" ? "董事长" : "部门负责人",
      contact: `1390000${String(2001 + index).padStart(4, "0")}`,
      domains: [department.name, "首问责任", "协同管理"],
      selfPortrait: `我负责${department.name}的团队管理、事项统筹和部门职责维护。`,
      peerPortrait: `熟悉${department.name}的服务边界与协同机制。`,
      completeness: 90,
    });
  }
  const hasMember = seedPeople.some((person) => person.department === department.name && person.id !== department.leaderId);
  if (!hasMember) {
    seedPeople.push({
      id: `p-dept-member-${index + 1}`,
      name: generatedMemberNames[index],
      department: department.name,
      departmentPath: department.path.slice(),
      role: "协同专员",
      contact: `1390000${String(2101 + index).padStart(4, "0")}`,
      domains: [department.name, "事项协同"],
      selfPortrait: `我协助处理${department.name}的日常咨询、事项登记和协同跟进。`,
      peerPortrait: `能够配合完成${department.name}的日常服务和材料整理。`,
      completeness: 78,
    });
  }
});

export const seedRoles = ["董事长", "副行长", "部门负责人", "部门经理", "经理", "科长", "主管", "专员", "协同专员"];

// ── 本周推荐次数 ───────────────────────────────────────────────────────────
export const recommendedCountMap = {
  "p-chen": 126,
  "p-luo": 103,
  "p-song": 91,
  "p-tang": 88,
  "p-xu": 72,
  "p-lin": 64,
  "p-zhou": 79,
  "p-jiang": 68,
  "p-he": 74,
  "p-ye": 61,
  "p-han": 57,
  "p-cai": 52,
};

// ── 种子内容 ───────────────────────────────────────────────────────────────
// id / ownerId / title / tags / summary / body / publishedAt / pinned / weeklyQueryCount / weeklyRecommendCount
export const seedContent = [
  {
    id: "c-key", ownerId: "p-chen",
    title: "大模型 Key 申请流程",
    tags: ["大模型", "Key 申请", "权限流程"],
    summary: "说明大模型 Key 的申请条件、审批节点、调用额度和常见驳回原因。",
    body: "申请前需明确用途、调用模型、预计额度和责任部门。提交后按部门负责人、平台管理员两级审批。",
    publishedAt: "2026-07-05", pinned: true, weeklyQueryCount: 82, weeklyRecommendCount: 64,
  },
  {
    id: "c-agent", ownerId: "p-chen",
    title: "智能体应用常见问题处理说明",
    tags: ["智能体", "模型调用", "故障排查"],
    summary: "整理智能体运行报错、模型无响应、工具调用失败等常见问题的排查方法。",
    body: "重点排查模型配置、网络连通性、工具权限与输入参数完整性。",
    publishedAt: "2026-07-04", pinned: true, weeklyQueryCount: 77, weeklyRecommendCount: 59,
  },
  {
    id: "c-report", ownerId: "p-luo",
    title: "数据报表口径核对清单",
    tags: ["数据报表", "指标口径", "数据质量"],
    summary: "给出跨部门报表口径核对步骤，帮助定位字段来源、统计周期和计算规则差异。",
    body: "先确认指标定义，再核对统计周期、数据来源表和口径变更记录。",
    publishedAt: "2026-07-03", pinned: false, weeklyQueryCount: 71, weeklyRecommendCount: 44,
  },
  {
    id: "c-auth", ownerId: "p-song",
    title: "内部系统权限申请注意事项",
    tags: ["权限申请", "账号问题", "系统运维"],
    summary: "说明系统权限申请材料、审批人选择、账号异常处理和权限回收规则。",
    body: "所有权限申请需关联岗位职责，离岗后 24 小时内完成权限回收。",
    publishedAt: "2026-07-02", pinned: false, weeklyQueryCount: 69, weeklyRecommendCount: 51,
  },
  {
    id: "c-flow", ownerId: "p-tang",
    title: "跨部门事项流转路径说明",
    tags: ["流程审批", "事项流转", "责任边界"],
    summary: "解释跨部门事项如何判断首问责任人、协助人和最终处理部门。",
    body: "首问人先受理，再判断责任归属，如需协同须同步记录协助链路。",
    publishedAt: "2026-07-01", pinned: true, weeklyQueryCount: 74, weeklyRecommendCount: 56,
  },
  {
    id: "c-security", ownerId: "p-zhou",
    title: "系统上线安全评估材料清单",
    tags: ["安全合规", "审计检查", "风险评估"],
    summary: "列出系统上线前需要提交的安全评估材料、日志留存要求、脱敏证明和整改闭环记录。",
    body: "材料需至少包含安全评估表、日志策略、整改清单和责任人确认记录。",
    publishedAt: "2026-06-30", pinned: false, weeklyQueryCount: 58, weeklyRecommendCount: 36,
  },
  {
    id: "c-policy", ownerId: "p-jiang",
    title: "政策口径确认与材料报送说明",
    tags: ["政策解读", "政策口径", "材料报送"],
    summary: "说明政策条款不明确时的确认路径、材料报送格式和对外答复口径留痕要求。",
    body: "建议先内部形成统一口径，再进行对外答复，并保留确认记录。",
    publishedAt: "2026-06-29", pinned: false, weeklyQueryCount: 46, weeklyRecommendCount: 29,
  },
  {
    id: "c-purchase", ownerId: "p-he",
    title: "采购申请到合同付款流程",
    tags: ["采购流程", "预算管理", "合同付款"],
    summary: "串联采购申请、预算占用、合同审批、验收确认和付款申请的关键节点。",
    body: "流程关键在预算校验、验收凭证和付款资料完整性。",
    publishedAt: "2026-06-28", pinned: false, weeklyQueryCount: 43, weeklyRecommendCount: 31,
  },
  {
    id: "c-training", ownerId: "p-ye",
    title: "培训报名与人员信息维护流程",
    tags: ["培训报名", "人员信息", "入职离职"],
    summary: "说明培训报名入口、人员信息变更、入职离职联动和账号开通通知路径。",
    body: "涉及人员信息变更时需同步组织、人事和系统账号三方。",
    publishedAt: "2026-06-27", pinned: false, weeklyQueryCount: 38, weeklyRecommendCount: 24,
  },
  {
    id: "c-supervise", ownerId: "p-han",
    title: "首问事项督办和闭环管理办法",
    tags: ["督办跟踪", "闭环管理", "服务评价"],
    summary: "说明首问事项超过响应时限后的督办机制、协同记录要求和闭环评价方式。",
    body: "超时事项需触发督办，闭环前必须补齐协同说明和结果反馈。",
    publishedAt: "2026-06-26", pinned: false, weeklyQueryCount: 35, weeklyRecommendCount: 22,
  },
  {
    id: "c-training-manual", ownerId: "p-cai",
    title: "平台培训报名和使用手册获取",
    tags: ["平台培训", "使用手册", "用户答疑"],
    summary: "说明平台培训报名方式、手册下载路径、常见操作问题和宣贯材料更新流程。",
    body: "新用户可先阅读手册，再报名体验场培训。手册版本按月更新。",
    publishedAt: "2026-06-25", pinned: true, weeklyQueryCount: 62, weeklyRecommendCount: 48,
  },
  {
    id: "c-pending-model", ownerId: "p-chen", title: "模型调用额度申请补充说明",
    tags: ["大模型", "额度申请"], summary: "补充额度申请需要准备的业务说明和容量预估信息。",
    body: "请提交使用场景、模型类型、调用峰值和责任人信息，便于完成额度评估。",
    status: "待审核", submittedAt: "2026-07-22", updatedAt: "2026-07-22", version: 1, pinned: false, weeklyQueryCount: 0, weeklyRecommendCount: 0,
  },
  {
    id: "c-pending-data", ownerId: "p-luo", title: "数据质量问题提报规范",
    tags: ["数据治理", "数据质量"], summary: "统一数据质量问题的提报字段、影响范围和反馈时限。",
    body: "提报时应包含数据来源、异常样例、影响范围和期望处理时限。",
    status: "待审核", submittedAt: "2026-07-21", updatedAt: "2026-07-21", version: 1, pinned: false, weeklyQueryCount: 0, weeklyRecommendCount: 0,
  },
  {
    id: "c-pending-flow", ownerId: "p-tang", title: "跨部门事项协同登记要求",
    tags: ["流程审批", "协同流转"], summary: "明确跨部门事项的协同登记时点和责任记录要求。",
    body: "首问受理后需要记录协同部门、协同事项、反馈时限和最终结论。",
    status: "待审核", submittedAt: "2026-07-20", updatedAt: "2026-07-20", version: 1, pinned: false, weeklyQueryCount: 0, weeklyRecommendCount: 0,
  },
];

// ── 操作手册章节 ───────────────────────────────────────────────────────────
export const manualSections = [
  { title: "1. 登录与首页", body: "支持用户名/手机号 + 密码登录。进入后默认看到首问助手首页，可直接发起提问或进入历史对话。" },
  { title: "2. 智能问答与历史对话", body: "每次提问都会生成会话记录，支持搜索、标题修改和直接删除。" },
  { title: "3. 名片库与人员主页", body: "名片库支持按实际组织层级逐级筛选；点击名片可进入人员主页查看职责、画像和公开发布内容。" },
  { title: "4. 个人中心与后台", body: "个人中心可维护资料、发布内容、查看操作手册；后台支持查看人员规模、发布内容、本周推荐热度和周活趋势。" },
];

// ── 领域词典 ───────────────────────────────────────────────────────────────
// 领域名 → 匹配关键词列表（用于问题意图识别和人员匹配）
export const domainDictionary = {
  大模型: ["大模型", "模型", "llm", "key", "调用", "额度", "api"],
  智能体: ["智能体", "agent", "工具调用", "应用建设", "报错"],
  数据治理: ["数据", "治理", "质量", "字段", "来源"],
  指标口径: ["指标", "口径", "统计", "报表", "不一致"],
  系统运维: ["系统", "运维", "故障", "登录", "账号", "异常"],
  权限申请: ["权限", "申请", "开通", "审批", "账号"],
  流程审批: ["流程", "审批", "事项", "流转", "制度", "责任边界"],
  内容运营: ["内容", "发布", "知识", "标签", "常见问题"],
  安全合规: ["安全", "合规", "上线", "风险", "审计", "日志"],
  政策解读: ["政策", "条款", "口径", "解读", "材料", "报送"],
  采购流程: ["采购", "合同", "付款", "预算", "报销", "资产"],
  培训报名: ["培训", "报名", "课程", "人员信息", "入职", "离职"],
  督办跟踪: ["督办", "超时", "响应", "投诉", "评价", "闭环"],
  平台培训: ["培训", "手册", "宣贯", "怎么用", "操作", "答疑"],
};

// ── 当前登录用户 ───────────────────────────────────────────────────────────
export const currentUserId = "p-lin";

/** 当前会话用户；无会话时回退到管理员演示账号。 */
export function getActiveUserId() {
  return loadJson(STORAGE_KEYS.auth, {}).userId || currentUserId;
}

// ── 种子评价日期 ───────────────────────────────────────────────────────────
export const reviewDates = ["2026-07-05", "2026-07-03", "2026-06-29", "2026-06-26", "2026-06-21", "2026-06-16"];

// ── 导航项（图标在 App.vue 中绑定）──────────────────────────────────────────
export const navItems = [
  { view: "ask", label: "智能问答" },
  { view: "directory", label: "名片库" },
  { view: "mine", label: "个人中心" },
  { view: "admin", label: "后台管理" },
];

// ═══════════════════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════════════════

/** 从 localStorage 读取 JSON，解析失败时返回 fallback */
export function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

/** 将 value 序列化为 JSON 写入 localStorage */
export function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

/** 返回今天日期的 ISO 文本，如 "2026-07-08" */
export function getTodayText() {
  return new Date().toISOString().slice(0, 10);
}

/** 将标签字符串拆分为数组，支持顿号、逗号、空格分隔 */
export function splitTags(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || "").split(/[、,，\s]+/).map((item) => item.trim()).filter(Boolean);
}

/** 统一小写去空格，用于模糊匹配 */
export function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

/** 规范化人员记录：补齐 departmentPath 和 recommendedCount */
export function normalizePersonRecord(person) {
  const department = person.department || person.departmentPath?.at(-1) || "未分组";
  const recommendedCount =
    typeof person.recommendedCount === "number"
      ? person.recommendedCount
      : (typeof person.recommended_count === "number"
          ? person.recommended_count
          : (recommendedCountMap[person.id] || 0));
  return {
    ...person,
    department,
    departmentPath:
      Array.isArray(person.departmentPath) && person.departmentPath.length
        ? person.departmentPath.slice()
        : (departmentHierarchyMap[department] || ["未分组", department]),
    selfPortrait: person.selfPortrait ?? person.self_portrait ?? "",
    domains: Array.isArray(person.domains) ? person.domains : [],
    recommendedCount,
    systemRole: person.systemRole || person.system_role || (person.id === currentUserId ? "管理员" : "普通成员"),
    active: person.active !== false,
    // 直接上级(server 模式来自 users.manager_id;验收#7 树状汇报关系)
    managerId: person.managerId || person.manager_id || null,
  };
}

/** 规范化内容记录：补齐所有字段默认值 */
export function normalizeContentRecord(item) {
  return {
    ...item,
    ownerId: item.ownerId || "p-lin",

    title: item.title || "未命名内容",
    tags: splitTags(item.tags),
    summary: item.summary || "",
    body: item.body || item.summary || "",
    status: item.status || "已发布",
    submittedAt: item.submittedAt || item.updatedAt || item.publishedAt || getTodayText(),
    updatedAt: item.updatedAt || item.publishedAt || getTodayText(),
    version: Number(item.version || 1),
    auditTrail: Array.isArray(item.auditTrail) ? item.auditTrail : [],
    publishedSnapshot: item.publishedSnapshot || null,
    publishedAt: item.publishedAt || getTodayText(),
    pinned: Boolean(item.pinned),
    weeklyQueryCount: Number.isFinite(item.weeklyQueryCount) ? item.weeklyQueryCount : 0,
    weeklyRecommendCount: Number.isFinite(item.weeklyRecommendCount) ? item.weeklyRecommendCount : 0,
  };
}

/** 创建一条空白会话 */
export function createSession() {
  return {
    id: `session-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title: "新对话",
    conversation: [],
    pendingAction: null,
    lastResult: null,
  };
}
