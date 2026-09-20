import http from "./http.js";

/** 我的问题列表(可按状态筛选) */
export const fetchIssues = (status) => http.get("/issues", { params: status ? { status } : {} });

/** 待我处理：我作为责任人的问题（按状态筛选） */
export const fetchAssignedIssues = (status) =>
  http.get("/issues/assigned", { params: status ? { status } : {} });

/** 帮助榜（全员可见的正向榜） */
export const fetchLeaderboard = (limit = 20) =>
  http.get("/issues/leaderboard", { params: { limit } });

/** 知识缺口地图（未结问题按部门聚合） */
export const fetchGapMap = () => http.get("/issues/gap-map");

/** 问题详情(时间线 + 邮件往来) */
export const fetchIssueDetail = (id) => http.get(`/issues/${id}`);

/** 从问答记录同步问题(后端 LLM 判定有效问题/判重) */
export const syncIssues = (limit = 30) => http.post("/issues/sync", { limit });

/** 改状态/责任人/备注(标记已解决会自动进知识沉淀候选) */
export const updateIssue = (id, payload) => http.patch(`/issues/${id}`, payload);

/** 知识沉淀候选(管理员) */
export const fetchKnowledgeCandidates = (status = "pending") =>
  http.get("/knowledge/candidates", { params: { status } });
export const approveCandidate = (id, payload) => http.post(`/knowledge/candidates/${id}/approve`, payload);
export const rejectCandidate = (id) => http.post(`/knowledge/candidates/${id}/reject`);

/** 知识条目(FAQ) */
export const fetchFaqs = () => http.get("/faqs");

/** 问题闭环总览(管理员):解决率/平均时长/按责任人分布 */
export const fetchIssuesOverview = () => http.get("/admin/issues/overview");
