(function () {
  "use strict";

  const STORAGE_KEYS = {
    profile: "firstResponsibilityDemo.profile",
    content: "firstResponsibilityDemo.content",
    peerReviews: "firstResponsibilityDemo.peerReviews",
    deletedPeerReviews: "firstResponsibilityDemo.deletedPeerReviews",
    sessions: "firstResponsibilityDemo.sessions",
    auth: "firstResponsibilityDemo.auth",
    feedback: "firstResponsibilityDemo.feedback"
  };

  const seedPeople = [
    { id: "p-chen", name: "陈亦舟", department: "数字能力中心", role: "大模型平台主管", contact: "13800001201", domains: ["大模型", "Key 申请", "模型调用", "智能体"], selfPortrait: "我负责大模型能力接入、Key 申请流程支持，以及智能体应用建设中的模型侧问题答疑。", peerPortrait: "熟悉大模型平台接入流程，能快速判断 Key、权限、额度和调用报错问题。", completeness: 98 },
    { id: "p-luo", name: "罗澄", department: "数据治理科", role: "数据治理专员", contact: "13800001202", domains: ["数据治理", "指标口径", "数据报表", "数据质量"], selfPortrait: "我主要负责指标口径管理、数据质量核查、报表字段解释和数据治理规范维护。", peerPortrait: "对跨部门报表口径很敏感，适合处理数据不一致、指标解释、数据来源追溯等问题。", completeness: 92 },
    { id: "p-song", name: "宋可为", department: "应用运维科", role: "系统运维主管", contact: "13800001203", domains: ["系统运维", "权限申请", "账号问题", "故障排查"], selfPortrait: "我负责内部系统账号开通、权限问题排查、应用故障定位和运行监控。", peerPortrait: "处理系统登录、权限、网络和应用异常经验丰富，能给出明确排查路径。", completeness: 88 },
    { id: "p-tang", name: "唐沐", department: "流程管理室", role: "流程审批负责人", contact: "13800001204", domains: ["流程审批", "制度规范", "事项流转", "责任边界"], selfPortrait: "我维护跨部门流程审批规则、事项流转路径和首问责任边界说明。", peerPortrait: "适合咨询流程卡点、责任归属、审批路径和制度解释类问题。", completeness: 90 },
    { id: "p-xu", name: "徐念", department: "内容运营组", role: "内容运营专员", contact: "13800001205", domains: ["内容运营", "知识发布", "标签体系", "常见问题"], selfPortrait: "我负责平台内容运营、标签体系维护、常见问题归档和个人发布内容整理。", peerPortrait: "能帮助同事把零散经验整理成可复用内容，适合知识发布和标签治理问题。", completeness: 86 },
    { id: "p-lin", name: "林知夏", department: "综合协同办公室", role: "平台用户", contact: "13800001206", domains: ["首问责任", "协同流转", "问题分派"], selfPortrait: "我负责首问责任制平台日常使用反馈、问题流转记录和跨部门协同跟进。", peerPortrait: "熟悉业务咨询入口和首问流转过程，适合反馈平台体验和协同效率问题。", completeness: 82 },
    { id: "p-zhou", name: "周弦", department: "安全合规科", role: "安全合规负责人", contact: "13800001207", domains: ["安全合规", "数据脱敏", "审计检查", "风险评估"], selfPortrait: "我负责系统上线安全评估、数据脱敏规则、审计检查材料准备和安全风险整改跟踪。", peerPortrait: "对合规材料和审计口径熟悉，适合咨询上线前安全检查、数据出境、日志留存和脱敏问题。", completeness: 91 },
    { id: "p-jiang", name: "蒋宁", department: "政策研究室", role: "政策解读专员", contact: "13800001208", domains: ["政策解读", "政策口径", "材料报送", "业务咨询"], selfPortrait: "我负责政策文件解读、对外材料口径确认、业务报送要求梳理和政策问答沉淀。", peerPortrait: "适合处理政策条款怎么理解、材料怎么写、对外口径怎么统一等问题。", completeness: 87 },
    { id: "p-he", name: "何予", department: "财务资产科", role: "采购与预算主管", contact: "13800001209", domains: ["采购流程", "预算管理", "合同付款", "资产登记"], selfPortrait: "我负责采购申请、预算占用、合同付款节点、固定资产入库和费用报销规则解释。", peerPortrait: "能快速判断采购事项该走哪个流程、需要哪些附件，以及付款和预算是否满足条件。", completeness: 89 },
    { id: "p-ye", name: "叶澜", department: "人事培训组", role: "培训与账号协同专员", contact: "13800001210", domains: ["培训报名", "人员信息", "入职离职", "账号联动"], selfPortrait: "我负责培训报名、人员信息变更、入职离职协同和账号权限联动通知。", peerPortrait: "适合咨询人员信息维护、培训安排、新员工账号开通和离职权限回收问题。", completeness: 84 },
    { id: "p-han", name: "韩书", department: "质量监督办", role: "督办评价专员", contact: "13800001211", domains: ["督办跟踪", "服务评价", "投诉处理", "闭环管理"], selfPortrait: "我负责问题督办、服务评价回收、投诉处理记录和跨部门闭环跟踪。", peerPortrait: "适合咨询问题迟迟未响应、责任流转不清、服务评价和投诉反馈类事项。", completeness: 86 },
    { id: "p-cai", name: "蔡宁", department: "培训推广组", role: "平台推广专员", contact: "13800001212", domains: ["平台培训", "使用手册", "宣贯材料", "用户答疑"], selfPortrait: "我负责平台培训安排、使用手册编写、宣贯材料维护和一线用户答疑。", peerPortrait: "适合咨询平台怎么用、培训怎么报名、操作手册在哪里和宣贯材料如何更新。", completeness: 86 }
  ];

  const departmentHierarchyMap = {
    "数字能力中心": ["数字化建设部", "智能能力处", "数字能力中心"],
    "数据治理科": ["数字化建设部", "数据治理处", "数据治理科"],
    "应用运维科": ["数字化建设部", "平台运维处", "应用运维科"],
    "流程管理室": ["综合管理部", "流程运营处", "流程管理室"],
    "内容运营组": ["综合管理部", "知识运营处", "内容运营组"],
    "综合协同办公室": ["综合管理部", "协同服务处", "综合协同办公室"],
    "安全合规科": ["风险管理部", "安全治理处", "安全合规科"],
    "政策研究室": ["业务管理部", "政策研究处", "政策研究室"],
    "财务资产科": ["综合管理部", "财务保障处", "财务资产科"],
    "人事培训组": ["综合管理部", "组织人事处", "人事培训组"],
    "质量监督办": ["服务管理部", "服务督导处", "质量监督办"],
    "培训推广组": ["服务管理部", "宣贯推广处", "培训推广组"]
  };

  const recommendedCountMap = {
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
    "p-cai": 52
  };

  const seedContent = [
    { id: "c-key", ownerId: "p-chen", type: "流程说明", title: "大模型 Key 申请流程", tags: ["大模型", "Key 申请", "权限流程"], summary: "说明大模型 Key 的申请条件、审批节点、调用额度和常见驳回原因。", body: "申请前需明确用途、调用模型、预计额度和责任部门。提交后按部门负责人、平台管理员两级审批。", publishedAt: "2026-07-05", pinned: true, weeklyQueryCount: 82, weeklyRecommendCount: 64 },
    { id: "c-agent", ownerId: "p-chen", type: "常见问题", title: "智能体应用常见问题处理说明", tags: ["智能体", "模型调用", "故障排查"], summary: "整理智能体运行报错、模型无响应、工具调用失败等常见问题的排查方法。", body: "重点排查模型配置、网络连通性、工具权限与输入参数完整性。", publishedAt: "2026-07-04", pinned: true, weeklyQueryCount: 77, weeklyRecommendCount: 59 },
    { id: "c-report", ownerId: "p-luo", type: "经验文章", title: "数据报表口径核对清单", tags: ["数据报表", "指标口径", "数据质量"], summary: "给出跨部门报表口径核对步骤，帮助定位字段来源、统计周期和计算规则差异。", body: "先确认指标定义，再核对统计周期、数据来源表和口径变更记录。", publishedAt: "2026-07-03", pinned: false, weeklyQueryCount: 71, weeklyRecommendCount: 44 },
    { id: "c-auth", ownerId: "p-song", type: "流程说明", title: "内部系统权限申请注意事项", tags: ["权限申请", "账号问题", "系统运维"], summary: "说明系统权限申请材料、审批人选择、账号异常处理和权限回收规则。", body: "所有权限申请需关联岗位职责，离岗后 24 小时内完成权限回收。", publishedAt: "2026-07-02", pinned: false, weeklyQueryCount: 69, weeklyRecommendCount: 51 },
    { id: "c-flow", ownerId: "p-tang", type: "流程说明", title: "跨部门事项流转路径说明", tags: ["流程审批", "事项流转", "责任边界"], summary: "解释跨部门事项如何判断首问责任人、协助人和最终处理部门。", body: "首问人先受理，再判断责任归属，如需协同须同步记录协助链路。", publishedAt: "2026-07-01", pinned: true, weeklyQueryCount: 74, weeklyRecommendCount: 56 },
    { id: "c-security", ownerId: "p-zhou", type: "流程说明", title: "系统上线安全评估材料清单", tags: ["安全合规", "审计检查", "风险评估"], summary: "列出系统上线前需要提交的安全评估材料、日志留存要求、脱敏证明和整改闭环记录。", body: "材料需至少包含安全评估表、日志策略、整改清单和责任人确认记录。", publishedAt: "2026-06-30", pinned: false, weeklyQueryCount: 58, weeklyRecommendCount: 36 },
    { id: "c-policy", ownerId: "p-jiang", type: "经验文章", title: "政策口径确认与材料报送说明", tags: ["政策解读", "政策口径", "材料报送"], summary: "说明政策条款不明确时的确认路径、材料报送格式和对外答复口径留痕要求。", body: "建议先内部形成统一口径，再进行对外答复，并保留确认记录。", publishedAt: "2026-06-29", pinned: false, weeklyQueryCount: 46, weeklyRecommendCount: 29 },
    { id: "c-purchase", ownerId: "p-he", type: "流程说明", title: "采购申请到合同付款流程", tags: ["采购流程", "预算管理", "合同付款"], summary: "串联采购申请、预算占用、合同审批、验收确认和付款申请的关键节点。", body: "流程关键在预算校验、验收凭证和付款资料完整性。", publishedAt: "2026-06-28", pinned: false, weeklyQueryCount: 43, weeklyRecommendCount: 31 },
    { id: "c-training", ownerId: "p-ye", type: "流程说明", title: "培训报名与人员信息维护流程", tags: ["培训报名", "人员信息", "入职离职"], summary: "说明培训报名入口、人员信息变更、入职离职联动和账号开通通知路径。", body: "涉及人员信息变更时需同步组织、人事和系统账号三方。", publishedAt: "2026-06-27", pinned: false, weeklyQueryCount: 38, weeklyRecommendCount: 24 },
    { id: "c-supervise", ownerId: "p-han", type: "经验文章", title: "首问事项督办和闭环管理办法", tags: ["督办跟踪", "闭环管理", "服务评价"], summary: "说明首问事项超过响应时限后的督办机制、协同记录要求和闭环评价方式。", body: "超时事项需触发督办，闭环前必须补齐协同说明和结果反馈。", publishedAt: "2026-06-26", pinned: false, weeklyQueryCount: 35, weeklyRecommendCount: 22 },
    { id: "c-training-manual", ownerId: "p-cai", type: "常见问题", title: "平台培训报名和使用手册获取", tags: ["平台培训", "使用手册", "用户答疑"], summary: "说明平台培训报名方式、手册下载路径、常见操作问题和宣贯材料更新流程。", body: "新用户可先阅读手册，再报名体验场培训。手册版本按月更新。", publishedAt: "2026-06-25", pinned: true, weeklyQueryCount: 62, weeklyRecommendCount: 48 }
  ];

  const manualSections = [
    { title: "1. 登录与首页", body: "支持用户名/手机号 + 密码登录。进入后默认看到首问助手首页，可直接发起提问或进入历史对话。" },
    { title: "2. 智能问答与历史对话", body: "每次提问都会生成会话记录，支持搜索、标题修改和直接删除。" },
    { title: "3. 名片库与内容检索", body: "名片库支持一级、二级、三级部门联动筛选；内容检索入口位于个人中心，可按关键词、类型、发布人和置顶状态筛选。" },
    { title: "4. 个人中心与后台", body: "个人中心可维护资料、发布内容、查看操作手册；后台支持查看本周咨询热度、本周推荐热度和近 14 天 Query 趋势。" }
  ];

  const domainDictionary = {
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
    平台培训: ["培训", "手册", "宣贯", "怎么用", "操作", "答疑"]
  };

  const reviewDates = ["2026-07-05", "2026-07-03", "2026-06-29", "2026-06-26", "2026-06-21", "2026-06-16"];
  const seedPeerReviews = seedPeople.map((person, index) => ({
    id: `review-${person.id}-seed`,
    personId: person.id,
    reviewer: ["王珂", "赵敏", "林知夏", "运营管理员"][index % 4],
    date: reviewDates[index % reviewDates.length],
    text: person.peerPortrait
  }));

  const state = {
    people: hydratePeople(),
    content: loadContent(),
    peerReviews: loadPeerReviews(),
    feedback: loadFeedback(),
    sessions: loadSessions(),
    activeSessionId: null,
    activeHistoryIndex: 0,
    conversation: [],
    pendingAction: null,
    lastResult: null,
    awaitingInput: null,
    currentView: "ask",
    previousView: "ask",
    activePersonId: "p-chen",
    activeDetail: { type: "empty" },
    historySearch: "",
    isHistorySearchOpen: false,
    activeHistoryMenuId: null,
    activeAdminWeek: 0,
    isDetailSidebarVisible: false,
    isMineContentSearchOpen: false,
    mineContentSearch: "",
    directoryFilters: { level1: "全部一级部门", level2: "全部二级部门", level3: "全部三级部门" },
    contentFilters: { keyword: "", type: "全部类型", ownerId: "全部发布人", pin: "all" },
    auth: loadAuth()
  };

  const viewTitles = {
    login: "登录页",
    ask: "智能问答",
    directory: "名片库",
    mine: "个人中心",
    manual: "操作手册",
    profile: "人员主页",
    review: "为他人画像",
    publish: "内容发布",
    contentDetail: "内容详情",
    contentSearch: "内容检索",
    admin: "后台管理"
  };

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    ensureSessions();
    hydrateMyProfile();
    bindNavigation();
    bindHistory();
    bindBackButtons();
    bindAvatarEntry();
    bindAvatarMenu();
    bindLoginForm();
    bindPasswordForm();
    bindNewChat();
    bindConversationSearch();
    bindDetailSidebarToggle();
    bindQuestion();
    bindDirectory();
    bindMineForm();
    bindPeerReviewForm();
    bindContentForm();
    bindContentSearch();
    bindContentDetail();
    bindGlobalDelegation();
    renderManualPage();
    renderConversation();
    renderConversationHistory();
    renderConversationSearchResults();
    renderTopbarUser();
    renderDirectory();
    renderMineSummary();
    renderProfile(state.activePersonId);
    renderContentSearch();
    renderSentReviewList();
    renderAdmin();
    renderDetailPanel();
    setProfileEditMode(false);
    restoreInitialView();
  }

  function hydratePeople() {
    return seedPeople.map(normalizePersonRecord);
  }

  function normalizeContentRecord(item) {
    return {
      ...item,
      ownerId: item.ownerId || "p-lin",
      type: item.type || "流程说明",
      title: item.title || "未命名内容",
      tags: Array.isArray(item.tags) ? item.tags : splitTags(item.tags),
      summary: item.summary || "",
      body: item.body || item.summary || "",
      status: item.status || "已发布",
      publishedAt: item.publishedAt || getTodayText(),
      pinned: Boolean(item.pinned),
      weeklyQueryCount: Number.isFinite(item.weeklyQueryCount) ? item.weeklyQueryCount : 0,
      weeklyRecommendCount: Number.isFinite(item.weeklyRecommendCount) ? item.weeklyRecommendCount : 0
    };
  }

  function normalizePersonRecord(person) {
    const department = person.department || person.departmentPath?.[2] || "未分组";
    return {
      ...person,
      department,
      departmentPath: Array.isArray(person.departmentPath) && person.departmentPath.length >= 3
        ? person.departmentPath.slice(0, 3)
        : (departmentHierarchyMap[department] || ["未分组", "未分组", department]),
      recommendedCount: typeof person.recommendedCount === "number" ? person.recommendedCount : (recommendedCountMap[person.id] || 0)
    };
  }

  function ensureSessions() {
    if (!state.sessions.length) {
      state.sessions = [createSession()];
      saveSessions();
    }
    compactEmptySessions();
    const visible = getVisibleSessions();
    const firstSession = visible[0] || state.sessions[0];
    state.activeSessionId = firstSession.id;
    loadSessionIntoState(firstSession.id);
  }

  function createSession() {
    return {
      id: `session-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      title: "新对话",
      conversation: [],
      pendingAction: null,
      lastResult: null,
      awaitingInput: null,
      deletedAt: null
    };
  }

  function getActiveSession() {
    return state.sessions.find((session) => session.id === state.activeSessionId) || null;
  }

  function getVisibleSessions() {
    return state.sessions;
  }

  function loadSessionIntoState(sessionId) {
    const session = state.sessions.find((item) => item.id === sessionId);
    if (!session) return;
    state.activeSessionId = session.id;
    state.conversation = Array.isArray(session.conversation) ? session.conversation.slice() : [];
    state.pendingAction = session.pendingAction || null;
    state.lastResult = session.lastResult || null;
    state.awaitingInput = session.awaitingInput || null;
    state.activeHistoryIndex = state.sessions.findIndex((item) => item.id === sessionId);
  }

  function syncStateToActiveSession() {
    const session = getActiveSession();
    if (!session) return;
    session.conversation = state.conversation.slice();
    session.pendingAction = state.pendingAction;
    session.lastResult = state.lastResult;
    session.awaitingInput = state.awaitingInput;
    session.title = state.conversation[0]?.question?.slice(0, 28) || session.title || "新对话";
    saveSessions();
  }

  function bindNavigation() {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", () => navigateTo(button.dataset.view));
    });
  }

  function bindHistory() {
    window.addEventListener("popstate", (event) => {
      const route = event.state || { view: state.auth.isLoggedIn ? "ask" : "login" };
      applyRoute(route, { pushHistory: false });
    });
  }

  function restoreInitialView() {
    const hashView = decodeURIComponent(String(location.hash || "").replace(/^#/, "")).trim();
    const initialView = hashView || (state.auth.isLoggedIn ? "ask" : "login");
    applyRoute({ view: initialView }, { replaceHistory: true });
  }

  function navigateTo(view, extras = {}) {
    applyRoute({ view, ...extras }, { pushHistory: true });
  }

  function applyRoute(route, options = {}) {
    const { pushHistory = false, replaceHistory = false } = options;
    const requestedView = route.view || "ask";
    const nextView = !state.auth.isLoggedIn && requestedView !== "login" ? "login" : requestedView;

    if (nextView === "profile" && route.personId) renderProfile(route.personId);
    if (nextView === "mine") {
      renderMineSummary();
      setProfileEditMode(Boolean(route.editing));
    }
    if (nextView === "review") resetPeerReviewForm();
    if (nextView === "publish" && route.draftContent) fillContentForm(route.draftContent);
    if (nextView === "contentDetail" && route.contentId) {
      const item = state.content.find((content) => content.id === route.contentId);
      if (item) {
        state.previousView = route.previousView || state.previousView || "contentSearch";
        renderContentDetail(item);
      }
    }
    if (nextView === "contentSearch") renderContentSearch();
    if (nextView === "directory") renderDirectory();
    if (nextView === "admin") renderAdmin();
    if (nextView === "manual") renderManualPage();

    switchView(nextView);

    if (pushHistory) {
      history.pushState({ ...route, view: nextView }, "", `#${encodeURIComponent(nextView)}`);
    } else if (replaceHistory) {
      history.replaceState({ ...route, view: nextView }, "", `#${encodeURIComponent(nextView)}`);
    }
  }

  function switchView(viewName) {
    state.currentView = viewName;
    document.body.classList.toggle("is-login-view", viewName === "login");
    if (viewName !== "ask") {
      state.activeDetail = { type: "empty" };
      state.isDetailSidebarVisible = false;
    }
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === viewName);
    });
    document.querySelectorAll(".view").forEach((view) => {
      view.classList.toggle("active", view.id === `view-${viewName}`);
    });
    const title = document.getElementById("view-title");
    if (title) title.textContent = viewTitles[viewName] || "首问责任平台";
    renderDetailPanel();
  }

  function bindBackButtons() {
    document.querySelectorAll("[data-back-button]").forEach((button) => {
      button.addEventListener("click", () => {
        if (history.length > 1) {
          history.back();
          return;
        }
        navigateTo("ask");
      });
    });
  }

  function bindAvatarEntry() {
    const entry = document.getElementById("avatar-entry");
    if (!entry) return;
    entry.addEventListener("click", (event) => {
      event.stopPropagation();
      const menu = document.getElementById("avatar-menu");
      if (!menu) return;
      menu.hidden = !menu.hidden;
    });
  }

  function bindAvatarMenu() {
    const menu = document.getElementById("avatar-menu");
    if (!menu) return;
    menu.addEventListener("click", (event) => {
      const button = event.target.closest("[data-avatar-action]");
      if (!button) return;
      const action = button.dataset.avatarAction;
      menu.hidden = true;
      if (action === "mine") navigateTo("mine");
      if (action === "manual") navigateTo("manual");
      if (action === "password") openPasswordModal();
      if (action === "logout") logout();
      if (action === "login") navigateTo("login");
    });
    document.addEventListener("click", (event) => {
      const avatarEntry = document.getElementById("avatar-entry");
      if (!menu.hidden && !menu.contains(event.target) && !avatarEntry.contains(event.target)) {
        menu.hidden = true;
      }
    });
  }

  function bindLoginForm() {
    const form = document.getElementById("login-form");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const account = String(data.get("account") || "").trim();
      const password = String(data.get("password") || "").trim();
      const candidates = ["linzhixia", "林知夏", "13800001206"];
      const status = document.getElementById("login-status");
      if (!candidates.includes(account) || password !== state.auth.password) {
        status.textContent = "账号或密码不正确，请使用演示账号重试";
        return;
      }
      state.auth.isLoggedIn = true;
      state.auth.account = account;
      state.auth.name = "林知夏";
      saveAuth();
      status.textContent = "登录成功，正在进入平台";
      renderTopbarUser();
      navigateTo("ask");
    });
  }

  function bindPasswordForm() {
    const form = document.getElementById("password-form");
    const closeButton = document.getElementById("password-modal-close");
    const cancel = document.getElementById("password-cancel");
    [closeButton, cancel].forEach((button) => {
      if (button) button.addEventListener("click", closePasswordModal);
    });
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const currentPassword = String(data.get("currentPassword") || "").trim();
      const nextPassword = String(data.get("nextPassword") || "").trim();
      const confirmPassword = String(data.get("confirmPassword") || "").trim();
      const status = document.getElementById("password-status");
      if (currentPassword !== state.auth.password) {
        status.textContent = "原密码不正确";
        return;
      }
      if (nextPassword.length < 6) {
        status.textContent = "新密码至少 6 位";
        return;
      }
      if (nextPassword !== confirmPassword) {
        status.textContent = "两次输入的新密码不一致";
        return;
      }
      state.auth.password = nextPassword;
      saveAuth();
      status.textContent = "密码已修改";
      window.setTimeout(closePasswordModal, 480);
    });
  }

  function openPasswordModal() {
    const modal = document.getElementById("password-modal");
    if (!modal || !state.auth.isLoggedIn) return;
    modal.hidden = false;
    document.getElementById("password-status").textContent = "";
    document.getElementById("password-form").reset();
  }

  function closePasswordModal() {
    const modal = document.getElementById("password-modal");
    if (modal) modal.hidden = true;
  }

  function logout() {
    state.auth.isLoggedIn = false;
    saveAuth();
    renderTopbarUser();
    navigateTo("login");
  }

  function renderTopbarUser() {
    const avatar = document.querySelector("#avatar-entry .avatar");
    const name = document.querySelector("#avatar-entry .operator-copy strong");
    const mineButton = document.querySelector('[data-avatar-action="mine"]');
    const logoutButton = document.querySelector('[data-avatar-action="logout"]');
    const loginButton = document.querySelector('[data-avatar-action="login"]');
    const passwordButton = document.querySelector('[data-avatar-action="password"]');
    const manualButton = document.querySelector('[data-avatar-action="manual"]');
    const displayName = state.auth.isLoggedIn ? state.auth.name : "未登录";
    if (avatar) avatar.textContent = state.auth.isLoggedIn ? state.auth.name.slice(0, 1) : "?";
    if (name) name.textContent = displayName;
    [mineButton, logoutButton, passwordButton, manualButton].forEach((button) => {
      if (button) button.hidden = !state.auth.isLoggedIn;
    });
    if (loginButton) loginButton.hidden = state.auth.isLoggedIn;
  }

  function bindNewChat() {
    const button = document.getElementById("new-chat-button");
    if (!button) return;
    button.addEventListener("click", () => {
      startNewSession();
      navigateTo("ask");
    });
  }

  function startNewSession() {
    compactEmptySessions();
    const existingEmpty = state.sessions.find((session) => !session.conversation?.length);
    if (existingEmpty) {
      loadSessionIntoState(existingEmpty.id);
    } else {
      const nextSession = createSession();
      state.sessions.unshift(nextSession);
      loadSessionIntoState(nextSession.id);
    }
    saveSessions();
    state.pendingAction = null;
    state.lastResult = null;
    state.awaitingInput = null;
    const input = document.getElementById("question-input");
    if (input) input.value = "";
    renderConversation();
    renderConversationHistory();
    renderConversationSearchResults();
  }

  function bindConversationSearch() {
    const input = document.getElementById("conversation-search");
    const trigger = document.getElementById("conversation-search-trigger");
    const close = document.getElementById("conversation-search-close");
    const popover = document.getElementById("history-search-popover");
    if (!input || !trigger || !close || !popover) return;
    trigger.addEventListener("click", () => {
      state.isHistorySearchOpen = true;
      popover.hidden = false;
      input.focus();
      renderConversationSearchResults();
    });
    close.addEventListener("click", closeConversationSearch);
    input.addEventListener("input", () => {
      state.historySearch = input.value.trim();
      renderConversationSearchResults();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeConversationSearch();
    });
    document.addEventListener("click", (event) => {
      if (!state.isHistorySearchOpen) return;
      if (popover.contains(event.target) || trigger.contains(event.target)) return;
      closeConversationSearch();
    });
  }

  function closeConversationSearch() {
    state.isHistorySearchOpen = false;
    state.historySearch = "";
    const popover = document.getElementById("history-search-popover");
    const input = document.getElementById("conversation-search");
    if (popover) popover.hidden = true;
    if (input) input.value = "";
    renderConversationSearchResults();
  }

  function bindQuestion() {
    const askButton = document.getElementById("ask-button");
    const input = document.getElementById("question-input");
    if (askButton) askButton.addEventListener("click", runCurrentQuestion);
    if (input) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          runCurrentQuestion();
        }
      });
    }
    document.querySelectorAll(".sample-question").forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.textContent.trim();
        input.focus();
      });
    });
  }

  function bindDetailSidebarToggle() {
    const button = document.getElementById("detail-sidebar-toggle");
    if (!button) return;
    button.addEventListener("click", () => {
      state.isDetailSidebarVisible = !state.isDetailSidebarVisible;
      renderDetailPanel();
    });
  }

  async function runCurrentQuestion() {
    const input = document.getElementById("question-input");
    const question = String(input?.value || "").trim();
    if (!question) return;
    switchView("ask");
    renderLoadingState();
    await wait(320);
    const result = await matchQuestion(question);
    const turn = { id: `turn-${Date.now()}`, question, result };
    state.conversation.push(turn);
    state.lastResult = result;
    if (["profile", "content", "review"].includes(result.action.type)) {
      state.pendingAction = result.action;
    }
    if (result.action.type === "profile") {
      state.activeDetail = { type: "profileAction" };
      state.isDetailSidebarVisible = true;
    }
    syncStateToActiveSession();
    input.value = "";
    renderConversation();
    renderConversationHistory();
    renderAdmin();
  }

  function renderLoadingState() {
    const shell = document.getElementById("chat-shell");
    const workspace = document.getElementById("ask-workspace");
    const thread = document.getElementById("assistant-thread");
    shell.classList.add("has-session", "is-loading");
    workspace.classList.add("has-session");
    thread.innerHTML = `
      <div class="answer-skeleton">
        <span></span>
        <span></span>
        <span></span>
      </div>
    `;
  }

  async function matchQuestion(question) {
    const analysis = analyzeQuestion(question);
    const contentHits = matchContent(analysis).slice(0, 5);
    const matches = state.people
      .map((person) => scorePerson(person, analysis, contentHits))
      .sort((left, right) => right.score - left.score)
      .slice(0, 3);
    const action = buildAssistantAction(question, analysis, matches, contentHits);
    return { analysis, action, matches, contentHits };
  }

  function analyzeQuestion(question) {
    const normalized = normalize(question);
    const domains = Object.entries(domainDictionary)
      .filter(([, words]) => words.some((word) => normalized.includes(word.toLowerCase())))
      .map(([domain]) => domain);
    const tokens = extractTokens(normalized);
    const intent = inferIntent(normalized);
    return {
      original: question,
      normalized,
      intent,
      domains: domains.length ? domains : ["待判断"],
      tokens: Array.from(new Set(tokens.concat(domains))).slice(0, 10),
      confidence: Math.min(95, 50 + domains.length * 12 + Math.min(tokens.length, 6) * 4)
    };
  }

  function extractTokens(normalized) {
    const words = [];
    Object.values(domainDictionary).flat().forEach((word) => {
      const key = word.toLowerCase();
      if (normalized.includes(key)) words.push(word);
    });
    const chineseChunks = normalized.match(/[\u4e00-\u9fa5]{2,}/g) || [];
    chineseChunks.forEach((chunk) => {
      if (chunk.length <= 8) words.push(chunk);
    });
    return words;
  }

  function inferIntent(normalized) {
    if (/(登录|密码)/.test(normalized)) return "账号访问";
    if (/(操作手册|手册|怎么用)/.test(normalized)) return "查询内容";
    if (/(我要评价|评价一下|补充评价)/.test(normalized)) return "评价他人";
    if (/(我要发布|发布|发一篇|写一个|流程说明|常见问题)/.test(normalized)) return "内容发布";
    if (/(修改|更新|维护|改我的|联系方式|负责领域|自画像|个人信息)/.test(normalized)) return "信息维护";
    if (/(有没有|哪里看|查看|材料清单|说明|文档|内容)/.test(normalized)) return "查询内容";
    if (/(找谁|谁负责|问谁|联系谁)/.test(normalized)) return "问题找人";
    if (/(申请|开通|审批)/.test(normalized)) return "流程咨询";
    if (/(报错|异常|失败|不一致|排查)/.test(normalized)) return "问题排查";
    return "业务咨询";
  }

  function buildAssistantAction(question, analysis, matches, contentHits) {
    const normalized = analysis.normalized;
    if (/(修改|更新|改我的|联系方式|负责领域|自画像)/.test(normalized)) {
      const changes = [];
      const nextProfilePatch = {};
      const phone = question.match(/1\d{10}/);
      if (phone) {
        nextProfilePatch.contact = phone[0];
        changes.push(`联系方式将更新为 ${phone[0]}`);
      }
      const domainMatch = question.match(/负责领域(?:增加|新增|添加|补充|改为)?\s*[:：]?\s*([^，。；\n]+)/);
      const nextDomains = domainMatch ? splitTags(domainMatch[1]) : [];
      if (nextDomains.length) {
        nextProfilePatch.addDomains = nextDomains;
        changes.push(`负责领域将增加 ${nextDomains.join("、")}`);
      } else if (/负责领域/.test(normalized)) {
        changes.push("负责领域会同步到个人主页与推荐匹配");
      }
      const portraitMatch = question.match(/自画像(?:修改为|改为|更新为|补充为|写为|调整为)?\s*[:：]?\s*([^。；\n]+)/);
      const nextPortrait = portraitMatch?.[1]?.trim();
      if (nextPortrait && !/^我要修改我的自画像$/.test(nextPortrait)) {
        nextProfilePatch.selfPortrait = nextPortrait;
        changes.push("自画像将同步更新到个人主页与推荐匹配");
      } else if (/自画像/.test(normalized)) {
        changes.push("自画像内容会影响后续找人推荐");
      }
      return {
        type: "profile",
        title: "检测到资料维护需求",
        description: "我已识别到你要维护个人资料，可以直接确认更新或去个人中心手动编辑。",
        changes,
        nextProfilePatch
      };
    }
    if (/(我要评价|评价一下|补充评价)/.test(normalized)) {
      const person = matches[0]?.person || state.people.find((item) => item.id !== "p-lin");
      return {
        type: "review",
        title: "已生成一条待确认评价",
        description: "我先根据你的表述生成了一条评价草稿，你确认后会写入对方主页。",
        nextReview: {
          id: `review-${Date.now()}`,
          personId: person.id,
          reviewer: state.auth.name,
          date: getTodayText(),
          text: `${person.name}在${person.domains[0]}相关问题上响应及时，适合作为首问协同对象。`
        }
      };
    }
    if (/(我要发布|发布|发一篇|写一个|流程说明|常见问题)/.test(normalized)) {
      const focusDomain = analysis.domains.find((item) => item !== "待判断") || "平台培训";
      return {
        type: "content",
        title: "已整理内容发布草稿",
        description: "我根据你的问题整理了一篇待发布内容，你可以直接确认，也可以继续补充正文。",
        nextContent: {
          id: `c-${Date.now()}`,
          ownerId: "p-lin",
          type: /常见问题|faq/.test(normalized) ? "常见问题" : "流程说明",
          title: `${focusDomain}相关说明`,
          tags: [focusDomain, "首问责任平台"],
          summary: `围绕${focusDomain}整理办理步骤、常见卡点和咨询入口。`,
          body: `一、适用场景\n二、办理步骤\n三、常见问题与联系路径`,
          publishedAt: getTodayText(),
          pinned: false,
          weeklyQueryCount: 18,
          weeklyRecommendCount: 11
        }
      };
    }
    if (analysis.intent === "查询内容" && contentHits.length) {
      return {
        type: "contentQuery",
        title: "已命中相关内容",
        description: "下面先给你展示相关内容结果，你也可以进入内容检索页继续筛选。"
      };
    }
    return {
      type: "match",
      title: "已完成首问推荐",
      description: "我按照你当前问题匹配了相关负责人，建议优先联系首推对象。"
    };
  }

  function matchContent(analysis) {
    return state.content
      .map((item) => {
        const text = normalize(`${item.title} ${item.tags.join(" ")} ${item.summary} ${item.body || ""}`);
        let score = 0;
        analysis.domains.forEach((domain) => {
          if (domain !== "待判断" && item.tags.includes(domain)) score += 24;
          else if (domain !== "待判断" && text.includes(domain.toLowerCase())) score += 12;
        });
        analysis.tokens.forEach((token) => {
          if (text.includes(token.toLowerCase())) score += 5;
        });
        return { ...item, hitScore: score };
      })
      .filter((item) => item.hitScore > 0)
      .sort((left, right) => right.pinned - left.pinned || right.hitScore - left.hitScore || right.publishedAt.localeCompare(left.publishedAt));
  }

  function scorePerson(person, analysis, contentHits) {
    const personContent = state.content.filter((item) => item.ownerId === person.id);
    const haystack = normalize([
      person.name,
      person.department,
      person.role,
      person.domains.join(" "),
      person.selfPortrait,
      getPeerReviewText(person.id),
      personContent.map((item) => `${item.title} ${item.summary}`).join(" ")
    ].join(" "));
    let score = 24 + Math.round(person.recommendedCount / 12);
    const reasons = [];
    analysis.domains.forEach((domain) => {
      if (domain !== "待判断" && person.domains.includes(domain)) {
        score += 26;
        reasons.push(`负责领域包含“${domain}”`);
      } else if (domain !== "待判断" && haystack.includes(domain.toLowerCase())) {
        score += 12;
        reasons.push(`个人资料中命中“${domain}”`);
      }
    });
    analysis.tokens.forEach((token) => {
      if (haystack.includes(token.toLowerCase())) score += 4;
    });
    const related = contentHits.filter((item) => item.ownerId === person.id).slice(0, 2);
    if (related.length) reasons.push(`关联内容 ${related.map((item) => item.title).join("、")}`);
    return { person, score, reasons: reasons.slice(0, 3), related };
  }

  function renderConversation() {
    const shell = document.getElementById("chat-shell");
    const thread = document.getElementById("assistant-thread");
    const workspace = document.getElementById("ask-workspace");
    shell.classList.toggle("has-session", state.conversation.length > 0);
    shell.classList.remove("is-loading");
    workspace.classList.toggle("has-session", state.conversation.length > 0);
    if (!state.conversation.length) {
      thread.innerHTML = "";
      renderConversationHistory();
      return;
    }
    thread.innerHTML = state.conversation.map((turn, index) => renderConversationTurn(turn, index)).join("");
    scrollConversationToLatest();
    renderConversationSearchResults();
    renderDetailPanel();
  }

  function renderConversationTurn(turn, index) {
    const { result } = turn;
    const isLatest = index === state.conversation.length - 1;
    const primary = result.matches[0]?.person;
    const firstContent = result.contentHits[0];
    return `
      <article class="thread-turn" id="${turn.id}">
        <article class="thread-bubble user-bubble">
          <p>${escapeHtml(turn.question)}</p>
        </article>
        <article class="thread-bubble assistant-bubble">
          <span class="thread-role">首问助手</span>
          <p>${escapeHtml(getAssistantReply(result, primary, firstContent))}</p>
          <div class="thread-feedback-row">
            ${renderFeedbackButtons(`answer:${turn.id}`)}
          </div>
          ${result.action.type === "match" || result.action.type === "contentQuery" ? `<div class="thread-tags">${renderTags(result.analysis.tokens.slice(0, 6))}</div>` : ""}
        </article>
        ${renderInlinePrimaryCard(turn, isLatest)}
      </article>
    `;
  }

  function getAssistantReply(result, primary, firstContent) {
    if (result.action.type === "profile") return result.action.description;
    if (result.action.type === "review") return "好的，我为你整理了一条评价草稿，请确认。";
    if (result.action.type === "content") return result.action.description;
    if (result.action.type === "contentQuery") return firstContent ? "好的，我找到了相关内容，你可以先看下面这批内容卡片。" : "目前没有明确命中内容，建议补充关键词。";
    if (primary) return "好的，下面为你推荐相关负责人。";
    return "目前还没有找到足够明确的对象，建议补充系统名、流程名或材料名。";
  }

  function renderInlinePrimaryCard(turn, isLatest) {
    const result = turn.result;
    if (result.action.type === "match") return renderInlineRecommendationCards(turn.id, result.matches);
    if (result.action.type === "contentQuery") return renderInlineContentCards(result.contentHits);
    return renderInlineActionCard(result, isLatest);
  }

  function renderInlineActionCard(result, isLatest) {
    if (result.action.type === "profile") {
      const isConfirmed = Boolean(result.action.confirmed);
      return `
        <article class="thread-card action-card ${isLatest ? "is-pending" : ""} is-clickable" data-open-pending-action="profile" tabindex="0">
          <div class="thread-card-head">
            <span class="intent-pill">${escapeHtml(result.analysis.intent)}</span>
            <strong>${escapeHtml(result.action.title)}</strong>
          </div>
          <p>${escapeHtml(result.action.description)}</p>
          <div class="action-preview">
            ${(result.action.changes || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("") || "<span>未识别到明确字段，将引导进入个人中心编辑。</span>"}
          </div>
          <div class="thread-card-actions">
            ${isConfirmed
              ? `<button class="secondary-button small-button" data-open-mine type="button">继续编辑</button>`
              : `<button class="primary-button small-button" data-confirm-action="profile" type="button">确认更新主页</button>
            <button class="secondary-button small-button" data-open-mine type="button">手动编辑</button>`}
          </div>
        </article>
      `;
    }
    if (result.action.type === "review") {
      const person = state.people.find((item) => item.id === result.action.nextReview.personId);
      return `
        <article class="thread-card action-card ${isLatest ? "is-pending" : ""}">
          <div class="thread-card-head">
            <span class="intent-pill">${escapeHtml(result.analysis.intent)}</span>
            <strong>${escapeHtml(result.action.title)}</strong>
          </div>
          <p>${escapeHtml(result.action.description)}</p>
          <div class="publish-preview">
            <strong>${escapeHtml(person ? person.name : "待确认人员")}</strong>
            <span>${escapeHtml(result.action.nextReview.date)}</span>
            <p>${escapeHtml(result.action.nextReview.text)}</p>
          </div>
          <div class="thread-card-actions">
            <button class="primary-button small-button" data-confirm-action="review" type="button">确认保存评价</button>
            <button class="secondary-button small-button" data-open-review type="button">手动修改</button>
          </div>
        </article>
      `;
    }
    if (result.action.type === "content") {
      return `
        <article class="thread-card action-card ${isLatest ? "is-pending" : ""}">
          <div class="thread-card-head">
            <span class="intent-pill">${escapeHtml(result.analysis.intent)}</span>
            <strong>${escapeHtml(result.action.title)}</strong>
          </div>
          <p>${escapeHtml(result.action.description)}</p>
          <div class="publish-preview">
            <strong>${escapeHtml(result.action.nextContent.title)}</strong>
            <span>${escapeHtml(result.action.nextContent.type)} · ${escapeHtml(result.action.nextContent.tags.join("、"))}</span>
            <p>${escapeHtml(result.action.nextContent.summary)}</p>
          </div>
          <div class="thread-card-actions">
            <button class="primary-button small-button" data-confirm-action="content" type="button">确认发布</button>
            <button class="secondary-button small-button" data-open-publish type="button">手动补充</button>
          </div>
        </article>
      `;
    }
    return "";
  }

  function renderInlineRecommendationCards(turnId, matches) {
    if (!matches.length) return "";
    return `
      <div class="inline-card-group">
        <div class="inline-group-title">
          <span class="soft-count">${matches.length} 位推荐对象</span>
          <strong>推荐人员卡片</strong>
        </div>
        <div class="inline-card-rail">
          ${matches.map(({ person, score, reasons, related }, index) => `
            <article class="result-card thread-card result-inline is-clickable" data-profile-id="${person.id}" tabindex="0">
              <div class="person-head">
                <div>
                  <p class="person-name">${index === 0 ? "首推 " : ""}${escapeHtml(person.name)}</p>
                  <p class="person-meta">${escapeHtml(getDepartmentPathText(person))}</p>
                  <p class="person-meta">${escapeHtml(person.role)}</p>
                </div>
                <span class="score-pill">${escapeHtml(getRecommendationLabel(index, score))}</span>
              </div>
              <div class="field-row">${renderTags(person.domains)}</div>
              <ul class="reason-list">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
              <p class="person-meta">联系方式：${escapeHtml(person.contact)}</p>
              <div class="card-meta-line">
                ${renderFeedbackButtons(`person:${turnId}:${person.id}`)}
              </div>
              <div class="related-list">
                ${related.map((item) => `<button data-content-id="${item.id}">${escapeHtml(item.title)}</button>`).join("")}
              </div>
              <button class="secondary-button small-button" data-profile-id="${person.id}" type="button">查看主页</button>
            </article>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderInlineContentCards(contentHits) {
    if (!contentHits.length) return "";
    return `
      <div class="inline-card-group">
        <div class="inline-group-title">
          <span class="soft-count">${contentHits.length} 条内容</span>
          <strong>相关内容卡片</strong>
        </div>
        <div class="content-hit-list">
          ${contentHits.map((item) => renderContentCard(item, { context: "ask", showFeedback: true })).join("")}
        </div>
      </div>
    `;
  }

  function getRecommendationLabel(index) {
    if (index === 0) return "首推";
    if (index === 1) return "可协助";
    return "相关人员";
  }

  function renderConversationHistory() {
    const history = document.getElementById("conversation-history");
    if (!history) return;
    const sessions = getVisibleSessions();
    if (!sessions.length) {
      history.innerHTML = `<div class="empty-state compact">暂无可见会话，请新建对话。</div>`;
      return;
    }
    history.innerHTML = sessions.map((session) => `
      <article class="history-card ${session.id === state.activeSessionId ? "active" : ""}">
        <button class="history-card-main" data-session-id="${session.id}" type="button">
          <strong>${escapeHtml(session.title || "新对话")}</strong>
          <span>${session.conversation.length ? `${session.conversation.length} 轮对话` : "空白对话"}</span>
        </button>
        <div class="history-card-actions">
          <button class="history-more-button ${state.activeHistoryMenuId === session.id ? "active" : ""}" data-history-menu-trigger="${session.id}" type="button" aria-label="更多操作" aria-expanded="${state.activeHistoryMenuId === session.id ? "true" : "false"}">…</button>
          <div class="history-action-menu" ${state.activeHistoryMenuId === session.id ? "" : "hidden"}>
            <button data-edit-session-id="${session.id}" type="button">重命名</button>
            <button data-delete-session-id="${session.id}" type="button">删除</button>
          </div>
        </div>
      </article>
    `).join("");
  }

  function renderConversationSearchResults() {
    const container = document.getElementById("conversation-search-results");
    if (!container) return;
    const keyword = normalize(state.historySearch);
    const matches = getVisibleSessions().filter((session) => {
      if (!keyword) return true;
      const text = normalize([
        session.title,
        ...session.conversation.map((item) => `${item.question} ${item.result?.analysis?.intent || ""}`)
      ].join(" "));
      return text.includes(keyword);
    });
    if (!matches.length) {
      container.innerHTML = `<div class="empty-state compact">没有找到匹配的历史对话。</div>`;
      return;
    }
    container.innerHTML = matches.slice(0, 8).map((session) => `
      <button class="history-search-item ${session.id === state.activeSessionId ? "active" : ""}" data-search-session-id="${session.id}" type="button">
        <strong>${escapeHtml(session.title || "新对话")}</strong>
        <span>${session.conversation.length ? `${session.conversation.length} 轮对话` : "空白对话"}</span>
      </button>
    `).join("");
  }

  function selectConversationSession(sessionId) {
    loadSessionIntoState(sessionId);
    state.activeHistoryMenuId = null;
    renderConversation();
    renderConversationHistory();
    renderConversationSearchResults();
  }

  function editSessionTitle(sessionId) {
    const session = state.sessions.find((item) => item.id === sessionId);
    if (!session) return;
    const nextTitle = window.prompt("请输入新的历史对话标题", session.title || "新对话");
    if (!nextTitle) return;
    state.activeHistoryMenuId = null;
    session.title = nextTitle.trim().slice(0, 30) || session.title;
    saveSessions();
    renderConversationHistory();
    renderConversationSearchResults();
  }

  function softDeleteSession(sessionId) {
    const session = state.sessions.find((item) => item.id === sessionId);
    if (!session) return;
    state.activeHistoryMenuId = null;
    const visibleSessions = getVisibleSessions();
    if (visibleSessions.length <= 1) {
      startNewSession();
      state.sessions = state.sessions.filter((item) => item.id !== sessionId);
      saveSessions();
      renderConversationHistory();
      renderConversationSearchResults();
      return;
    }
    const remaining = state.sessions.filter((item) => item.id !== sessionId);
    state.sessions = remaining;
    saveSessions();
    if (sessionId === state.activeSessionId && remaining.length) selectConversationSession(remaining[0].id);
    renderConversationHistory();
    renderConversationSearchResults();
  }

  function toggleHistoryMenu(sessionId) {
    state.activeHistoryMenuId = state.activeHistoryMenuId === sessionId ? null : sessionId;
    renderConversationHistory();
  }

  function compactEmptySessions() {
    const seenEmpty = new Set();
    state.sessions = state.sessions.filter((session) => {
      const isEmpty = !session.conversation || session.conversation.length === 0;
      if (!isEmpty) return true;
      if (seenEmpty.size) return false;
      seenEmpty.add("empty");
      return true;
    });
  }

  function bindDirectory() {
    ["directory-search"].forEach((id) => {
      const element = document.getElementById(id);
      if (element) element.addEventListener("input", renderDirectory);
      if (element) element.addEventListener("change", renderDirectory);
    });
    const level1 = document.getElementById("department-level-1");
    const level2 = document.getElementById("department-level-2");
    const level3 = document.getElementById("department-level-3");
    if (level1) level1.addEventListener("change", () => {
      renderDepartmentFilters();
      renderDirectory();
    });
    if (level2) level2.addEventListener("change", () => {
      renderDepartmentFilters();
      renderDirectory();
    });
    if (level3) level3.addEventListener("change", renderDirectory);
    renderDepartmentFilters();
  }

  function renderDepartmentFilters() {
    const allPaths = state.people.map((person) => person.departmentPath);
    const level1Select = document.getElementById("department-level-1");
    const level2Select = document.getElementById("department-level-2");
    const level3Select = document.getElementById("department-level-3");
    if (!level1Select || !level2Select || !level3Select) return;

    const level1Value = level1Select.value || "全部一级部门";
    const level1Options = ["全部一级部门"].concat(uniqueValues(allPaths.map((path) => path[0])));
    level1Select.innerHTML = level1Options.map((item) => `<option ${item === level1Value ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");

    const pathsForLevel2 = allPaths.filter((path) => level1Select.value === "全部一级部门" || path[0] === level1Select.value);
    const level2Value = level2Select.value || "全部二级部门";
    const level2Options = ["全部二级部门"].concat(uniqueValues(pathsForLevel2.map((path) => path[1])));
    level2Select.innerHTML = level2Options.map((item) => `<option ${item === level2Value ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");

    const pathsForLevel3 = allPaths.filter((path) => {
      const level1Match = level1Select.value === "全部一级部门" || path[0] === level1Select.value;
      const level2Match = level2Select.value === "全部二级部门" || path[1] === level2Select.value;
      return level1Match && level2Match;
    });
    const level3Value = level3Select.value || "全部三级部门";
    const level3Options = ["全部三级部门"].concat(uniqueValues(pathsForLevel3.map((path) => path[2])));
    level3Select.innerHTML = level3Options.map((item) => `<option ${item === level3Value ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");
  }

  function renderDirectory() {
    const keyword = normalize(document.getElementById("directory-search").value);
    const level1 = document.getElementById("department-level-1").value;
    const level2 = document.getElementById("department-level-2").value;
    const level3 = document.getElementById("department-level-3").value;
    const people = state.people
      .filter((person) => {
        const text = normalize(`${person.name} ${person.department} ${person.role} ${person.domains.join(" ")} ${person.selfPortrait}`);
        const keywordMatch = !keyword || text.includes(keyword);
        const level1Match = level1 === "全部一级部门" || person.departmentPath[0] === level1;
        const level2Match = level2 === "全部二级部门" || person.departmentPath[1] === level2;
        const level3Match = level3 === "全部三级部门" || person.departmentPath[2] === level3;
        return keywordMatch && level1Match && level2Match && level3Match;
      })
      .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));

    const list = document.getElementById("directory-list");
    list.innerHTML = people.length ? people.map((person) => `
      <article class="person-card clickable-card" data-profile-id="${person.id}" tabindex="0" role="button" aria-label="查看${escapeHtml(person.name)}主页">
        <div>
          <p class="person-name">${escapeHtml(person.name)}</p>
          <p class="person-meta">${escapeHtml(getDepartmentPathText(person))}</p>
          <p class="person-meta">${escapeHtml(person.role)}</p>
        </div>
        <div class="field-row">${renderTags(person.domains)}</div>
        <p class="person-meta">${escapeHtml(person.selfPortrait)}</p>
        <p class="person-meta">联系方式：${escapeHtml(person.contact)}</p>
      </article>
    `).join("") : `<div class="empty-state">没有匹配到人员名片。</div>`;
  }

  function renderProfile(personId) {
    state.activePersonId = personId;
    const person = state.people.find((item) => item.id === personId) || state.people[0];
    const content = sortContentList(state.content.filter((item) => item.ownerId === person.id));
    document.getElementById("profile-detail").innerHTML = `
      <div class="content-detail-topbar">
        <button class="secondary-button" data-back-button type="button">返回</button>
      </div>
      <div class="profile-header">
        <div>
          <h2>${escapeHtml(person.name)}</h2>
          <p class="person-meta">${escapeHtml(getDepartmentPathText(person))}</p>
          <p class="person-meta">${escapeHtml(person.role)} · 联系方式：${escapeHtml(person.contact)}</p>
        </div>
      </div>
      <div class="field-row">${renderTags(person.domains)}</div>
      <div class="profile-blocks">
        <section class="profile-block">
          <h3>自画像</h3>
          <p>${escapeHtml(person.selfPortrait)}</p>
        </section>
        <section class="profile-block">
          <div class="profile-block-head">
            <h3>他画像</h3>
            <span class="person-meta">${getPeerReviews(person.id).length > 5 ? "仅展示最近 5 条" : "按时间倒序展示"}</span>
          </div>
          ${renderPeerReviewList(person.id)}
        </section>
      </div>
      <section>
        <h2>个人发布内容</h2>
        <div class="content-list">
          ${content.length ? content.map((item) => renderContentCard(item, { context: "profile" })).join("") : `<div class="empty-state">暂无发布内容。</div>`}
        </div>
      </section>
    `;
    document.querySelectorAll("#profile-detail [data-back-button]").forEach((button) => {
      button.addEventListener("click", () => {
        if (history.length > 1) history.back();
        else navigateTo("ask");
      });
    });
  }

  function bindMineForm() {
    document.getElementById("cancel-edit-profile").addEventListener("click", () => setProfileEditMode(false));
    document.getElementById("mine-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const nextProfile = normalizePersonRecord({
        id: "p-lin",
        name: String(form.get("name") || "").trim(),
        department: String(form.get("department") || "").trim(),
        role: String(form.get("role") || "").trim(),
        contact: String(form.get("contact") || "").trim(),
        domains: splitTags(form.get("domains")),
        selfPortrait: String(form.get("selfPortrait") || "").trim(),
        completeness: 96,
        departmentPath: parseDepartmentPath(form.get("department")),
        recommendedCount: (state.people.find((person) => person.id === "p-lin") || {}).recommendedCount || 64
      });
      localStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(nextProfile));
      const index = state.people.findIndex((person) => person.id === "p-lin");
      state.people.splice(index, 1, nextProfile);
      state.auth.name = nextProfile.name;
      saveAuth();
      document.getElementById("mine-save-status").textContent = "已保存，并同步到名片库与推荐逻辑";
      renderTopbarUser();
      renderMineSummary();
      setProfileEditMode(false);
      renderDirectory();
      renderProfile(nextProfile.id);
      renderAdmin();
    });
  }

  function hydrateMyProfile() {
    const saved = readJson(STORAGE_KEYS.profile);
    if (saved) {
      const index = state.people.findIndex((person) => person.id === saved.id);
      if (index >= 0) state.people.splice(index, 1, normalizePersonRecord(saved));
    }
    const profile = state.people.find((person) => person.id === "p-lin");
    const form = document.getElementById("mine-form");
    if (!profile || !form) return;
    form.elements.name.value = profile.name;
    form.elements.department.value = profile.departmentPath ? profile.departmentPath.join(" / ") : profile.department;
    form.elements.role.value = profile.role;
    form.elements.contact.value = profile.contact;
    form.elements.domains.value = profile.domains.join("、");
    form.elements.selfPortrait.value = profile.selfPortrait;
  }

  function renderMineSummary() {
    const profile = state.people.find((person) => person.id === "p-lin");
    document.getElementById("mine-summary").innerHTML = `
      <div class="profile-header">
        <div>
          <h2>${escapeHtml(profile.name)}</h2>
          <p class="person-meta">${escapeHtml(getDepartmentPathText(profile))}</p>
          <p class="person-meta">${escapeHtml(profile.role)} · 联系方式：${escapeHtml(profile.contact)}</p>
        </div>
        <div class="profile-actions">
          <button class="secondary-button" id="edit-profile" type="button">编辑</button>
          <button class="secondary-button" id="review-profile" type="button">为他人画像</button>
          <button class="primary-button" id="publish-content" type="button">发布</button>
        </div>
      </div>
      <div class="field-row">${renderTags(profile.domains)}</div>
      <div class="profile-blocks">
        <section class="profile-block">
          <h3>自画像</h3>
          <p>${escapeHtml(profile.selfPortrait)}</p>
        </section>
        <section class="profile-block">
          <div class="profile-block-head">
            <h3>他画像</h3>
            <span class="person-meta">${getPeerReviews(profile.id).length > 5 ? "仅展示最近 5 条" : "按时间倒序展示"}</span>
          </div>
          ${renderPeerReviewList(profile.id)}
        </section>
      </div>
      <section>
        <div class="content-section-head">
          <h2>我的发布</h2>
          <button class="secondary-button" id="open-content-search" type="button">${state.isMineContentSearchOpen ? "收起检索" : "内容检索"}</button>
        </div>
        ${state.isMineContentSearchOpen ? `
          <div class="mine-search-bar">
            <div class="search-field mine-search-field">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></svg>
              <input id="mine-content-search" type="search" placeholder="只搜索我的发布内容" value="${escapeHtml(state.mineContentSearch)}">
            </div>
          </div>
        ` : ""}
        <div id="mine-content-list" class="content-list">
          ${renderMineContentListMarkup(profile.id)}
        </div>
      </section>
    `;
    document.getElementById("edit-profile").addEventListener("click", () => setProfileEditMode(true));
    document.getElementById("review-profile").addEventListener("click", () => {
      resetPeerReviewForm();
      navigateTo("review");
    });
    document.getElementById("open-content-search").addEventListener("click", () => {
      state.isMineContentSearchOpen = !state.isMineContentSearchOpen;
      if (!state.isMineContentSearchOpen) state.mineContentSearch = "";
      renderMineSummary();
      if (state.isMineContentSearchOpen) {
        const searchInput = document.getElementById("mine-content-search");
        if (searchInput) searchInput.focus();
      }
    });
    const mineContentSearchInput = document.getElementById("mine-content-search");
    if (mineContentSearchInput) {
      mineContentSearchInput.addEventListener("input", (event) => {
        state.mineContentSearch = event.target.value;
        renderMineContentList();
      });
    }
    document.getElementById("publish-content").addEventListener("click", () => {
      document.getElementById("content-form").reset();
      clearContentFormState();
      document.getElementById("content-owner").value = "p-lin";
      document.getElementById("content-save-status").textContent = "";
      navigateTo("publish");
    });
  }

  function setProfileEditMode(isEditing) {
    document.getElementById("mine-form").hidden = !isEditing;
    document.getElementById("mine-summary").hidden = isEditing;
    if (isEditing) document.getElementById("mine-save-status").textContent = "";
  }

  function renderMineContentListMarkup(ownerId = "p-lin") {
    const keyword = normalize(state.mineContentSearch);
    const items = sortContentList(state.content.filter((item) => {
      if (item.ownerId !== ownerId) return false;
      if (!keyword) return true;
      const text = normalize(`${item.title} ${item.tags.join(" ")} ${item.summary} ${item.body || ""}`);
      return text.includes(keyword);
    }));
    return items.length
      ? items.map((item) => renderContentCard(item, { context: "mine", editable: true })).join("")
      : `<div class="empty-state">${keyword ? "没有匹配到你的发布内容。" : "暂无发布内容。"}</div>`;
  }

  function renderMineContentList() {
    const list = document.getElementById("mine-content-list");
    if (!list) return;
    list.innerHTML = renderMineContentListMarkup("p-lin");
  }

  function bindPeerReviewForm() {
    const personSelect = document.getElementById("review-person");
    personSelect.innerHTML = state.people
      .filter((person) => person.id !== "p-lin")
      .map((person) => `<option value="${person.id}">${escapeHtml(person.name)} · ${escapeHtml(person.department)}</option>`)
      .join("");
    document.getElementById("cancel-peer-review").addEventListener("click", () => navigateTo("mine"));
    document.getElementById("peer-review-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const nextReview = {
        id: `review-${Date.now()}`,
        personId: form.get("personId"),
        reviewer: state.auth.name,
        date: form.get("date"),
        text: String(form.get("text") || "").trim()
      };
      state.peerReviews.unshift(nextReview);
      savePeerReviews();
      document.getElementById("review-save-status").textContent = "已提交评价";
      renderMineSummary();
      renderSentReviewList();
      renderProfile(nextReview.personId);
      renderAdmin();
      navigateTo("profile", { personId: nextReview.personId });
    });
  }

  function resetPeerReviewForm() {
    const form = document.getElementById("peer-review-form");
    form.reset();
    document.getElementById("review-date").value = getTodayText();
    document.getElementById("review-save-status").textContent = "";
  }

  function renderPeerReviewList(personId) {
    const reviews = getPeerReviews(personId).slice(0, 5);
    if (!reviews.length) return `<div class="empty-state">暂无同事评价。</div>`;
    return `
      <ol class="peer-review-list">
        ${reviews.map((review) => `
          <li>
            <div class="peer-review-row">
              <div class="peer-review-content">
                <p>${escapeHtml(review.text)}</p>
              </div>
              <time datetime="${escapeHtml(review.date)}">${escapeHtml(review.date)}</time>
            </div>
            <span class="peer-reviewer">${escapeHtml(review.reviewer)} 评价</span>
          </li>
        `).join("")}
      </ol>
    `;
  }

  function getPeerReviews(personId) {
    return state.peerReviews
      .filter((review) => review.personId === personId && review.text)
      .sort((left, right) => right.date.localeCompare(left.date));
  }

  function getPeerReviewText(personId) {
    return getPeerReviews(personId).map((review) => review.text).join(" ");
  }

  function renderSentReviewList() {
    const container = document.getElementById("sent-review-list");
    if (!container) return;
    const reviews = state.peerReviews
      .filter((review) => review.reviewer === state.auth.name && review.text)
      .sort((left, right) => right.date.localeCompare(left.date));
    if (!reviews.length) {
      container.innerHTML = `<div class="empty-state">暂时还没有你发出的评价。</div>`;
      return;
    }
    container.innerHTML = reviews.map((review) => {
      const person = state.people.find((item) => item.id === review.personId);
      return `
        <article class="sent-review-item">
          <div class="sent-review-meta">
            <div>
              <h3>${escapeHtml(person ? person.name : "未知人员")}</h3>
              <p class="person-meta">${escapeHtml(person ? `${person.department} · ${person.role}` : "人员信息缺失")}</p>
            </div>
            <time datetime="${escapeHtml(review.date)}">${escapeHtml(review.date)}</time>
          </div>
          <p>${escapeHtml(review.text)}</p>
          <div class="thread-card-actions">
            <button class="secondary-button small-button" data-open-review-person="${escapeHtml(review.personId)}" type="button">继续评价</button>
            <button class="secondary-button small-button" data-delete-review-id="${escapeHtml(review.id)}" type="button">删除</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function deletePeerReview(reviewId) {
    const index = state.peerReviews.findIndex((review) => review.id === reviewId);
    if (index < 0) return;
    const [removed] = state.peerReviews.splice(index, 1);
    if (String(reviewId).endsWith("-seed")) {
      const deletedIds = readJson(STORAGE_KEYS.deletedPeerReviews) || [];
      if (!deletedIds.includes(reviewId)) {
        deletedIds.push(reviewId);
        localStorage.setItem(STORAGE_KEYS.deletedPeerReviews, JSON.stringify(deletedIds));
      }
    }
    savePeerReviews();
    renderSentReviewList();
    renderMineSummary();
    renderProfile(removed.personId);
    renderAdmin();
  }

  function bindContentForm() {
    const form = document.getElementById("content-form");
    const ownerSelect = document.getElementById("content-owner");
    ownerSelect.innerHTML = state.people.map((person) => `<option value="${person.id}">${escapeHtml(person.name)}</option>`).join("");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const editingId = form.dataset.editingId || "";
      const existing = state.content.find((item) => item.id === editingId);
      const nextContent = normalizeContentRecord({
        id: editingId || `c-${Date.now()}`,
        ownerId: data.get("ownerId"),
        type: existing?.type || "流程说明",
        title: String(data.get("title") || "").trim(),
        tags: splitTags(data.get("tags")),
        summary: String(data.get("summary") || "").trim(),
        body: String(data.get("body") || "").trim(),
        status: "已发布",
        publishedAt: existing?.publishedAt || getTodayText(),
        pinned: existing?.pinned || false,
        weeklyQueryCount: existing?.weeklyQueryCount || 16,
        weeklyRecommendCount: existing?.weeklyRecommendCount || 10
      });
      if (editingId) {
        const index = state.content.findIndex((item) => item.id === editingId);
        if (index >= 0) state.content.splice(index, 1, nextContent);
      } else {
        state.content.unshift(nextContent);
      }
      saveContent();
      form.reset();
      clearContentFormState();
      document.getElementById("content-save-status").textContent = editingId ? "已更新发布内容" : "已发布到内容列表";
      renderMineSummary();
      renderContentSearch();
      renderDirectory();
      renderAdmin();
    });
    document.getElementById("delete-content-button").addEventListener("click", () => {
      const editingId = form.dataset.editingId;
      if (editingId) deleteContentById(editingId);
    });
  }

  function fillContentForm(content) {
    const form = document.getElementById("content-form");
    const deleteButton = document.getElementById("delete-content-button");
    if (content.id) {
      form.dataset.editingId = content.id;
      deleteButton.hidden = false;
    } else {
      delete form.dataset.editingId;
      deleteButton.hidden = true;
    }
    form.elements.title.value = content.title || "";
    form.elements.tags.value = (content.tags || []).join("、");
    form.elements.ownerId.value = content.ownerId || "p-lin";
    form.elements.summary.value = content.summary || "";
    form.elements.body.value = content.body || "";
    document.getElementById("content-save-status").textContent = content.id ? "正在编辑已发布内容" : "已根据对话生成内容草稿";
  }

  function clearContentFormState() {
    const form = document.getElementById("content-form");
    const deleteButton = document.getElementById("delete-content-button");
    delete form.dataset.editingId;
    deleteButton.hidden = true;
  }

  function deleteContentById(contentId) {
    const index = state.content.findIndex((item) => item.id === contentId);
    if (index < 0) return;
    state.content.splice(index, 1);
    saveContent();
    const form = document.getElementById("content-form");
    if (form.dataset.editingId === contentId) {
      form.reset();
      clearContentFormState();
      document.getElementById("content-save-status").textContent = "已删除发布内容";
    }
    renderMineSummary();
    renderContentSearch();
    renderAdmin();
    navigateTo("mine");
  }

  function toggleContentPin(contentId) {
    const item = state.content.find((content) => content.id === contentId);
    if (!item) return;
    if (!isOwnedByCurrentUser(item)) return;
    item.pinned = !item.pinned;
    saveContent();
    renderMineSummary();
    renderContentSearch();
    if (state.currentView === "contentDetail") renderContentDetail(item);
  }

  function bindContentSearch() {
    ["content-search", "content-type-filter", "content-owner-filter", "content-pin-filter"].forEach((id) => {
      const element = document.getElementById(id);
      if (!element) return;
      element.addEventListener("input", renderContentSearch);
      element.addEventListener("change", renderContentSearch);
    });
  }

  function renderContentSearch() {
    const typeFilter = document.getElementById("content-type-filter");
    const ownerFilter = document.getElementById("content-owner-filter");
    if (typeFilter && !typeFilter.dataset.ready) {
      const types = ["全部类型"].concat(uniqueValues(state.content.map((item) => item.type)));
      typeFilter.innerHTML = types.map((item) => `<option>${escapeHtml(item)}</option>`).join("");
      typeFilter.dataset.ready = "true";
    }
    if (ownerFilter && !ownerFilter.dataset.ready) {
      ownerFilter.innerHTML = [`<option>全部发布人</option>`].concat(
        state.people.map((person) => `<option value="${person.id}">${escapeHtml(person.name)}</option>`)
      ).join("");
      ownerFilter.dataset.ready = "true";
    }
    const keyword = normalize(document.getElementById("content-search").value);
    const type = document.getElementById("content-type-filter").value;
    const ownerId = document.getElementById("content-owner-filter").value;
    const pin = document.getElementById("content-pin-filter").value;
    const items = sortContentList(state.content.filter((item) => {
      const text = normalize(`${item.title} ${item.tags.join(" ")} ${item.summary} ${item.body || ""}`);
      const keywordMatch = !keyword || text.includes(keyword);
      const typeMatch = type === "全部类型" || item.type === type;
      const ownerMatch = ownerId === "全部发布人" || item.ownerId === ownerId;
      const pinMatch = pin === "all" || (pin === "pinned" ? item.pinned : !item.pinned);
      return keywordMatch && typeMatch && ownerMatch && pinMatch;
    }));
    const list = document.getElementById("content-search-list");
    list.innerHTML = items.length ? items.map((item) => renderContentCard(item, { context: "search", showFeedback: true, showPinAction: true })).join("") : `<div class="empty-state">没有匹配到内容结果。</div>`;
  }

  function renderContentCard(item, options = {}) {
    const owner = state.people.find((person) => person.id === item.ownerId);
    const isOwnContent = isOwnedByCurrentUser(item);
    const pinAction = (options.showPinAction || options.editable) && isOwnContent
      ? `<button class="secondary-button small-button" data-pin-content-id="${item.id}" type="button">${item.pinned ? "取消置顶" : "置顶"}</button>`
      : "";
    const editActions = options.editable ? `
      <div class="content-item-actions">
        ${pinAction}
        <button class="secondary-button small-button" data-edit-content-id="${item.id}" type="button">编辑</button>
        <button class="secondary-button small-button" data-delete-content-id="${item.id}" type="button">删除</button>
      </div>
    ` : "";
    const feedback = options.showFeedback && isOwnContent ? renderFeedbackButtons(`content:${item.id}`) : "";
    const pinBadge = item.pinned ? `<span class="pin-badge">置顶</span>` : "";
    const ownerLine = `${owner ? owner.name : "未知发布人"} · ${item.type} · ${item.publishedAt}`;
    if (options.editable) {
      return `
        <article class="content-item content-item-manage">
          <div class="content-item-main">
            <div class="content-item-head">
              <h3>${escapeHtml(item.title)}</h3>
              ${pinBadge}
            </div>
            <p>${escapeHtml(ownerLine)}</p>
            <div class="field-row">${renderTags(item.tags)}</div>
            <p>${escapeHtml(item.summary)}</p>
          </div>
          ${editActions}
        </article>
      `;
    }
    return `
      <article class="content-item clickable-card" data-open-content-id="${item.id}" tabindex="0" role="button" aria-label="查看${escapeHtml(item.title)}">
        <div class="content-item-head">
          <h3>${escapeHtml(item.title)}</h3>
          ${pinBadge}
        </div>
        <p>${escapeHtml(ownerLine)}</p>
        <div class="field-row">${renderTags(item.tags)}</div>
        <p>${escapeHtml(item.summary)}</p>
        <div class="card-meta-line">
          <span>发布日期 ${item.publishedAt}</span>
          ${feedback}
        </div>
        ${pinAction ? `<div class="thread-card-actions">${pinAction}</div>` : ""}
      </article>
    `;
  }

  function bindContentDetail() {
    document.addEventListener("click", (event) => {
      const backButton = event.target.closest("#back-from-content");
      if (!backButton) return;
      if (history.length > 1) history.back();
      else navigateTo(state.previousView || "contentSearch");
    });
  }

  function openContentDetail(contentId, previousView) {
    const item = state.content.find((content) => content.id === contentId);
    if (!item) return;
    state.previousView = previousView || state.currentView || "contentSearch";
    navigateTo("contentDetail", { contentId, previousView: state.previousView });
  }

  function renderContentDetail(item) {
    const owner = state.people.find((person) => person.id === item.ownerId);
    const isOwnContent = isOwnedByCurrentUser(item);
    document.getElementById("content-detail").innerHTML = `
      <div class="content-detail-single">
        <div class="content-detail-topbar">
          <button class="secondary-button" id="back-from-content" type="button">返回</button>
        </div>
        <div class="content-detail-head content-detail-head-single">
          <div>
            <h2>${escapeHtml(item.title)}</h2>
            <p class="content-detail-owner">${escapeHtml(owner ? owner.name : "未知发布人")} · ${escapeHtml(item.type)} · 发布日期 ${escapeHtml(item.publishedAt)}</p>
          </div>
          ${item.pinned ? `<span class="pin-badge">置顶</span>` : ""}
        </div>
        <div class="field-row content-tag-row">${renderTags(item.tags)}</div>
        ${isOwnContent ? `
          <div class="thread-card-actions">
            <button class="secondary-button" data-pin-content-id="${item.id}" type="button">${item.pinned ? "取消置顶" : "设为置顶"}</button>
            ${renderFeedbackButtons(`content:${item.id}`)}
          </div>
        ` : ""}
        <section class="content-body content-body-plain content-body-merged">
          <h3>内容摘要</h3>
          <p>${escapeHtml(item.summary)}</p>
          <h3>发布内容</h3>
          <p>${escapeHtml(item.body || item.summary)}</p>
        </section>
      </div>
    `;
  }

  function renderAdmin() {
    const recommendRanking = state.people
      .map((person) => ({ person, value: person.recommendedCount }))
      .sort((left, right) => right.value - left.value)
      .slice(0, 6);
    const weekTrend = buildWeeklyActiveTrend(state.activeAdminWeek);
    const weeklyQueries = weekTrend.reduce((sum, item) => sum + item.value, 0);
    const weeklyRecommendations = recommendRanking.reduce((sum, item) => sum + item.value, 0);
    const domainCount = uniqueValues(state.people.flatMap((person) => person.domains)).length;

    document.getElementById("metric-people").textContent = `${state.people.length} 人`;
    document.getElementById("metric-content").textContent = `${state.content.length} 条`;
    document.getElementById("metric-weekly-queries").textContent = `${domainCount} 个`;
    document.getElementById("metric-weekly-recommendations").textContent = `${weeklyRecommendations} 次`;

    document.getElementById("recommend-rank-list").innerHTML = recommendRanking.map((item, index) => renderRankItem(index, item.person, item.value, "本周推荐")).join("");
    const weekLabel = document.getElementById("admin-week-label");
    if (weekLabel) weekLabel.textContent = state.activeAdminWeek === 0 ? "本周" : "上周";
    const prevWeekButton = document.querySelector('[data-admin-week="prev"]');
    const nextWeekButton = document.querySelector('[data-admin-week="next"]');
    if (prevWeekButton) prevWeekButton.hidden = state.activeAdminWeek !== 0;
    if (nextWeekButton) nextWeekButton.hidden = state.activeAdminWeek !== 1;
    const maxTrend = Math.max(...weekTrend.map((item) => item.value), 1);
    document.getElementById("query-trend-panel").innerHTML = `
      <div class="activity-summary">
        <span>${state.activeAdminWeek === 0 ? "本周峰值" : "上周峰值"}</span>
        <strong>${maxTrend}</strong>
      </div>
      <div class="activity-chart" aria-label="周日活数">
        ${weekTrend.map((item) => `
          <div class="activity-bar activity-bar-wide">
            <span style="height: ${Math.max(18, Math.round(item.value / maxTrend * 100))}%"></span>
            <strong>${item.value}</strong>
            <em>${item.label}</em>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderRankItem(index, person, value, label) {
    return `
      <article class="rank-item">
        <span class="rank-no">${index + 1}</span>
        <div>
          <h3>${escapeHtml(person.name)}</h3>
          <p>${escapeHtml(person.department)} · ${escapeHtml(person.role)}</p>
        </div>
        <strong>${value} 次</strong>
      </article>
    `;
  }

  function buildWeeklyActiveTrend(weekOffset) {
    const baseWeeks = [
      [
        ["周一", 128], ["周二", 156], ["周三", 142], ["周四", 184], ["周五", 211], ["周六", 96], ["周日", 118]
      ],
      [
        ["周一", 121], ["周二", 144], ["周三", 138], ["周四", 162], ["周五", 198], ["周六", 91], ["周日", 112]
      ]
    ];
    const selected = baseWeeks[weekOffset] || baseWeeks[0];
    return selected.map(([label, value]) => ({ label, value }));
  }

  function renderManualPage() {
    const list = document.getElementById("manual-list");
    if (!list) return;
    list.innerHTML = manualSections.map((item) => `
      <article class="manual-card">
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.body)}</p>
      </article>
    `).join("");
  }

  function openDetailPanel(detail) {
    state.activeDetail = detail;
    state.isDetailSidebarVisible = true;
    renderDetailPanel();
  }

  function renderDetailPanel() {
    const workspace = document.getElementById("ask-workspace");
    const panel = document.getElementById("detail-panel");
    const toggle = document.getElementById("detail-sidebar-toggle");
    if (!workspace || !panel) return;
    workspace.classList.toggle("has-detail", state.currentView === "ask" && state.isDetailSidebarVisible);
    workspace.classList.toggle("detail-collapsed", state.currentView !== "ask" || !state.isDetailSidebarVisible);
    if (toggle) toggle.setAttribute("aria-expanded", state.currentView === "ask" && state.isDetailSidebarVisible ? "true" : "false");
    if (state.currentView !== "ask" || !state.isDetailSidebarVisible || state.activeDetail.type === "empty") {
      panel.innerHTML = `
        <div class="detail-empty">
          <div class="detail-panel-top">
            <div class="detail-panel-label">详情面板</div>
            <button class="detail-close-button" data-close-detail type="button" aria-label="收起详情面板">
              <span>收起</span>
              <strong>×</strong>
            </button>
          </div>
          <div class="detail-empty-copy">
            <h2>右侧详情</h2>
            <p>点击问答里的人员卡片或内容卡片，就可以在这里展开查看。</p>
          </div>
        </div>
      `;
      return;
    }
    if (state.activeDetail.type === "person") {
      const person = state.people.find((item) => item.id === state.activeDetail.personId);
      if (!person) return;
      const relatedContent = sortContentList(state.content.filter((item) => item.ownerId === person.id)).slice(0, 4);
      panel.innerHTML = `
        <div class="detail-section">
          <div class="detail-panel-top">
            <div class="detail-panel-label">人员详情</div>
            <button class="detail-close-button" data-close-detail type="button">
              <span>收起</span>
              <strong>×</strong>
            </button>
          </div>
          <div class="detail-card">
            <div class="detail-title">
              <div>
                <strong>${escapeHtml(person.name)}</strong>
                <p>${escapeHtml(getDepartmentPathText(person))}</p>
                <p>${escapeHtml(person.role)} · 联系方式：${escapeHtml(person.contact)}</p>
              </div>
            </div>
            <div class="field-row">${renderTags(person.domains)}</div>
            <p>${escapeHtml(person.selfPortrait)}</p>
            <div class="thread-card-actions">
              <button class="secondary-button small-button" data-detail-open-profile="${person.id}" type="button">查看主页</button>
            </div>
          </div>
          <div class="detail-card">
            <h3>相关发布</h3>
            <div class="content-list">
              ${relatedContent.length ? relatedContent.map((item) => renderContentCard(item, { context: "ask-detail" })).join("") : `<div class="empty-state compact">暂无相关内容。</div>`}
            </div>
          </div>
        </div>
      `;
      return;
    }
    if (state.activeDetail.type === "profileAction") {
      const profile = state.people.find((person) => person.id === "p-lin");
      const changes = state.pendingAction?.changes || [];
      const isConfirmed = Boolean(state.pendingAction?.confirmed);
      panel.innerHTML = `
        <div class="detail-section">
          <div class="detail-panel-top">
            <div class="detail-panel-label">资料维护</div>
            <button class="detail-close-button" data-close-detail type="button">
              <span>收起</span>
              <strong>×</strong>
            </button>
          </div>
          <div class="detail-card">
            <div class="detail-title">
              <div>
                <strong>${escapeHtml(state.pendingAction?.title || "检测到资料维护需求")}</strong>
                <p>${escapeHtml(profile ? profile.name : state.auth.name)}</p>
                <p>${escapeHtml(state.pendingAction?.description || "你可以直接确认更新，或前往个人中心手动编辑。")}</p>
              </div>
            </div>
            <div class="field-row">${renderTags(profile?.domains || [])}</div>
            <div class="action-preview">
              ${changes.length ? changes.map((item) => `<span>${escapeHtml(item)}</span>`).join("") : "<span>未识别到明确字段，将引导进入个人中心编辑。</span>"}
            </div>
            <div class="thread-card-actions">
              ${isConfirmed
                ? `<button class="secondary-button small-button" data-open-mine type="button">继续编辑</button>`
                : `<button class="primary-button small-button" data-confirm-action="profile" type="button">确认更新主页</button>
              <button class="secondary-button small-button" data-open-mine type="button">手动编辑</button>`}
            </div>
          </div>
        </div>
      `;
      return;
    }
    if (state.activeDetail.type === "content") {
      const item = state.content.find((content) => content.id === state.activeDetail.contentId);
      if (!item) return;
      const owner = state.people.find((person) => person.id === item.ownerId);
      panel.innerHTML = `
        <div class="detail-section">
          <div class="detail-panel-top">
            <div class="detail-panel-label">内容详情</div>
            <button class="detail-close-button" data-close-detail type="button">
              <span>收起</span>
              <strong>×</strong>
            </button>
          </div>
          <div class="detail-card">
            <div class="detail-title">
              <div>
                <strong>${escapeHtml(item.title)}</strong>
                <p>${escapeHtml(owner ? owner.name : "未知发布人")} · ${escapeHtml(item.type)}</p>
                <p>发布日期：${escapeHtml(item.publishedAt)}</p>
              </div>
              ${item.pinned ? `<span class="pin-badge">置顶</span>` : ""}
            </div>
            <div class="field-row">${renderTags(item.tags)}</div>
            <p>${escapeHtml(item.summary)}</p>
            <div class="thread-card-actions">
              <button class="secondary-button small-button" data-open-content-id="${item.id}" type="button">查看详情页</button>
            </div>
          </div>
        </div>
      `;
    }
  }

  function bindGlobalDelegation() {
    document.addEventListener("click", (event) => {
      const profileTrigger = event.target.closest("[data-profile-id]");
      if (profileTrigger) {
        const personId = profileTrigger.dataset.profileId;
        if (state.currentView === "ask") openDetailPanel({ type: "person", personId });
        else navigateTo("profile", { personId });
        return;
      }

      const contentTrigger = event.target.closest("[data-content-id]");
      if (contentTrigger) {
        const contentId = contentTrigger.dataset.contentId;
        if (state.currentView === "ask") openDetailPanel({ type: "content", contentId });
        else openContentDetail(contentId, state.currentView);
        return;
      }

      const openContentId = event.target.closest("[data-open-content-id]");
      if (openContentId) {
        openContentDetail(openContentId.dataset.openContentId, state.currentView);
        return;
      }

      const sessionButton = event.target.closest("[data-session-id]");
      if (sessionButton) {
        selectConversationSession(sessionButton.dataset.sessionId);
        return;
      }

      const historyMenuTrigger = event.target.closest("[data-history-menu-trigger]");
      if (historyMenuTrigger) {
        toggleHistoryMenu(historyMenuTrigger.dataset.historyMenuTrigger);
        return;
      }

      const searchSessionButton = event.target.closest("[data-search-session-id]");
      if (searchSessionButton) {
        selectConversationSession(searchSessionButton.dataset.searchSessionId);
        closeConversationSearch();
        return;
      }

      const editSessionButton = event.target.closest("[data-edit-session-id]");
      if (editSessionButton) {
        editSessionTitle(editSessionButton.dataset.editSessionId);
        return;
      }

      const deleteSessionButton = event.target.closest("[data-delete-session-id]");
      if (deleteSessionButton) {
        softDeleteSession(deleteSessionButton.dataset.deleteSessionId);
        return;
      }

      const deleteReviewButton = event.target.closest("[data-delete-review-id]");
      if (deleteReviewButton) {
        deletePeerReview(deleteReviewButton.dataset.deleteReviewId);
        return;
      }

      const openReviewPerson = event.target.closest("[data-open-review-person]");
      if (openReviewPerson) {
        navigateTo("review");
        document.getElementById("review-person").value = openReviewPerson.dataset.openReviewPerson;
        return;
      }

      const confirmAction = event.target.closest("[data-confirm-action]");
      if (confirmAction) {
        confirmAssistantAction(confirmAction.dataset.confirmAction);
        return;
      }

      const pendingActionTrigger = event.target.closest("[data-open-pending-action]");
      if (pendingActionTrigger) {
        if (pendingActionTrigger.dataset.openPendingAction === "profile" && state.pendingAction?.type === "profile") {
          openDetailPanel({ type: "profileAction" });
        }
        return;
      }

      if (event.target.closest("[data-open-mine]")) {
        navigateTo("mine", { editing: true });
        return;
      }

      if (event.target.closest("[data-open-review]")) {
        navigateTo("review");
        return;
      }

      if (event.target.closest("[data-open-publish]")) {
        if (state.pendingAction?.nextContent) fillContentForm(state.pendingAction.nextContent);
        navigateTo("publish");
        return;
      }

      const editContentButton = event.target.closest("[data-edit-content-id]");
      if (editContentButton) {
        const item = state.content.find((content) => content.id === editContentButton.dataset.editContentId);
        if (item) navigateTo("publish", { draftContent: item });
        return;
      }

      const deleteContentButton = event.target.closest("[data-delete-content-id]");
      if (deleteContentButton) {
        deleteContentById(deleteContentButton.dataset.deleteContentId);
        return;
      }

      const pinContentButton = event.target.closest("[data-pin-content-id]");
      if (pinContentButton) {
        toggleContentPin(pinContentButton.dataset.pinContentId);
        return;
      }

      const adminWeekButton = event.target.closest("[data-admin-week]");
      if (adminWeekButton) {
        state.activeAdminWeek = adminWeekButton.dataset.adminWeek === "prev" ? 1 : 0;
        renderAdmin();
        return;
      }

      const detailProfileButton = event.target.closest("[data-detail-open-profile]");
      if (detailProfileButton) {
        navigateTo("profile", { personId: detailProfileButton.dataset.detailOpenProfile });
        return;
      }

      const feedbackButton = event.target.closest("[data-feedback-target]");
      if (feedbackButton) {
        toggleFeedback(feedbackButton.dataset.feedbackTarget, feedbackButton.dataset.feedbackValue);
        return;
      }

      if (event.target.closest("[data-close-detail]")) {
        state.isDetailSidebarVisible = false;
        renderDetailPanel();
        return;
      }

      if (state.activeHistoryMenuId && !event.target.closest(".history-card-actions")) {
        state.activeHistoryMenuId = null;
        renderConversationHistory();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const clickable = event.target.closest("[data-open-content-id], [data-profile-id], [data-open-pending-action]");
      if (!clickable) return;
      event.preventDefault();
      clickable.click();
    });
  }

  function confirmAssistantAction(type) {
    if (type === "profile") {
      confirmProfileActionInPlace();
      return;
    }
    if (type === "review" && state.pendingAction?.nextReview) {
      state.peerReviews.unshift(state.pendingAction.nextReview);
      savePeerReviews();
      renderSentReviewList();
      renderProfile(state.pendingAction.nextReview.personId);
      renderMineSummary();
      state.pendingAction = null;
      syncStateToActiveSession();
      renderConversation();
      return;
    }
    if (type === "content" && state.pendingAction?.nextContent) {
      state.content.unshift(state.pendingAction.nextContent);
      saveContent();
      state.pendingAction = null;
      syncStateToActiveSession();
      renderConversation();
      renderMineSummary();
      renderContentSearch();
      renderAdmin();
    }
  }

  function confirmProfileActionInPlace() {
    if (state.pendingAction?.type !== "profile") return;
    const current = state.people.find((person) => person.id === "p-lin");
    if (!current) return;
    const patch = state.pendingAction.nextProfilePatch || {};
    const nextDomains = uniqueValues((current.domains || []).concat(patch.addDomains || []));
    const hasAutoUpdate = Boolean(patch.contact || (patch.addDomains || []).length || patch.selfPortrait);
    const nextProfile = normalizePersonRecord({
      ...current,
      contact: patch.contact || current.contact,
      domains: nextDomains,
      selfPortrait: patch.selfPortrait || current.selfPortrait
    });
    if (hasAutoUpdate) {
      const index = state.people.findIndex((person) => person.id === current.id);
      state.people.splice(index, 1, nextProfile);
      localStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(nextProfile));
      renderTopbarUser();
      renderMineSummary();
      renderDirectory();
      renderProfile(nextProfile.id);
      renderAdmin();
      hydrateMyProfile();
    }
    const changes = [];
    if (patch.contact) changes.push(`联系方式已更新为 ${patch.contact}`);
    if ((patch.addDomains || []).length) changes.push(`负责领域已增加 ${patch.addDomains.join("、")}`);
    if (patch.selfPortrait) changes.push("自画像已更新");
    const requiresManualEdit = /自画像/.test(state.pendingAction.description + state.pendingAction.changes.join("")) && !patch.selfPortrait;
    state.pendingAction = {
      ...state.pendingAction,
      title: hasAutoUpdate ? "资料已更新" : "待补充资料内容",
      description: hasAutoUpdate
        ? "已在当前页面完成更新，并同步到名片库与推荐逻辑。"
        : "已保留在当前页面。当前未识别到可自动提交的完整内容，你可以继续手动编辑补充。",
      changes: changes.length ? changes : [requiresManualEdit ? "自画像暂未提供新内容，请手动补充后保存。" : "本次没有识别到可自动提交的字段。"],
      confirmed: true
    };
    const latestTurn = state.conversation[state.conversation.length - 1];
    if (latestTurn?.result?.action?.type === "profile") {
      latestTurn.result.action = { ...state.pendingAction };
    }
    syncStateToActiveSession();
    renderConversation();
    renderDetailPanel();
  }

  function renderFeedbackButtons(targetKey) {
    const current = state.feedback[targetKey] || "";
    return `
      <div class="feedback-group" role="group" aria-label="反馈">
        <button class="feedback-button ${current === "up" ? "active" : ""}" data-feedback-target="${escapeHtml(targetKey)}" data-feedback-value="up" type="button">赞</button>
        <button class="feedback-button ${current === "down" ? "active" : ""}" data-feedback-target="${escapeHtml(targetKey)}" data-feedback-value="down" type="button">踩</button>
      </div>
    `;
  }

  function toggleFeedback(targetKey, nextValue) {
    state.feedback[targetKey] = state.feedback[targetKey] === nextValue ? "" : nextValue;
    saveFeedback();
    renderConversation();
    renderContentSearch();
    if (state.currentView === "profile") renderProfile(state.activePersonId);
    if (state.currentView === "mine") renderMineSummary();
    if (state.currentView === "contentDetail") {
      const item = state.content.find((content) => content.id === targetKey.replace("content:", ""));
      if (item) renderContentDetail(item);
    }
  }

  function loadContent() {
    const saved = readJson(STORAGE_KEYS.content);
    if (!Array.isArray(saved)) return seedContent.map(normalizeContentRecord);
    const savedIds = new Set(saved.map((item) => item.id));
    return saved
      .concat(seedContent.filter((item) => !savedIds.has(item.id)))
      .map(normalizeContentRecord);
  }

  function saveContent() {
    localStorage.setItem(STORAGE_KEYS.content, JSON.stringify(state.content));
  }

  function loadPeerReviews() {
    const saved = readJson(STORAGE_KEYS.peerReviews);
    const deletedIds = new Set(readJson(STORAGE_KEYS.deletedPeerReviews) || []);
    const availableSeeds = seedPeerReviews.filter((item) => !deletedIds.has(item.id));
    if (!Array.isArray(saved)) return availableSeeds.slice();
    const savedIds = new Set(saved.map((item) => item.id));
    return saved.concat(availableSeeds.filter((item) => !savedIds.has(item.id)));
  }

  function savePeerReviews() {
    const userReviews = state.peerReviews.filter((review) => !String(review.id).endsWith("-seed"));
    localStorage.setItem(STORAGE_KEYS.peerReviews, JSON.stringify(userReviews));
  }

  function loadSessions() {
    const saved = readJson(STORAGE_KEYS.sessions);
    return Array.isArray(saved) ? saved : [];
  }

  function saveSessions() {
    localStorage.setItem(STORAGE_KEYS.sessions, JSON.stringify(state.sessions));
  }

  function loadAuth() {
    const saved = readJson(STORAGE_KEYS.auth);
    return {
      isLoggedIn: saved?.isLoggedIn !== false,
      userId: "p-lin",
      name: saved?.name || "林知夏",
      account: saved?.account || "linzhixia",
      phone: "13800001206",
      password: saved?.password || "123456"
    };
  }

  function saveAuth() {
    localStorage.setItem(STORAGE_KEYS.auth, JSON.stringify(state.auth));
  }

  function loadFeedback() {
    return readJson(STORAGE_KEYS.feedback) || {};
  }

  function saveFeedback() {
    localStorage.setItem(STORAGE_KEYS.feedback, JSON.stringify(state.feedback));
  }

  function sortContentList(items) {
    return items
      .map(normalizeContentRecord)
      .slice()
      .sort((left, right) => Number(right.pinned) - Number(left.pinned) || String(right.publishedAt || "").localeCompare(String(left.publishedAt || "")));
  }

  function parseDepartmentPath(value) {
    const pieces = String(value || "")
      .split(/[\/／]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (pieces.length >= 3) return pieces.slice(0, 3);
    if (pieces.length === 2) return [pieces[0], pieces[1], pieces[1]];
    if (pieces.length === 1) return [pieces[0], pieces[0], pieces[0]];
    return ["综合管理部", "协同服务处", "综合协同办公室"];
  }

  function uniqueValues(list) {
    return Array.from(new Set(list.filter(Boolean)));
  }

  function getDepartmentPathText(person) {
    if (Array.isArray(person?.departmentPath) && person.departmentPath.length) {
      return person.departmentPath.join(" / ");
    }
    return person?.department || "未分组";
  }

  function isOwnedByCurrentUser(item) {
    return item?.ownerId === state.auth.userId;
  }

  function getTodayText() {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function wait(duration) {
    return new Promise((resolve) => window.setTimeout(resolve, duration));
  }

  function readJson(key) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function normalize(value) {
    return String(value || "").trim().toLowerCase();
  }

  function splitTags(value) {
    return String(value || "")
      .split(/[、,，\s]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function renderTags(tags) {
    return (tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  }

  function scrollConversationToLatest() {
    const panel = document.querySelector(".chat-thread-panel");
    const latestTurn = state.conversation.length ? document.getElementById(state.conversation[state.conversation.length - 1].id) : null;
    if (panel && latestTurn) latestTurn.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
