import http from "./http.js";

export const fetchAdminMetrics = () => http.get("/admin/metrics");
export const fetchRecommendRanking = () => http.get("/admin/rankings/recommend");
export const fetchActivityTrend = (params) => http.get("/admin/trends/activity", { params });
export const fetchAgentTraces = (params) => http.get("/admin/traces", { params });
export const fetchAgentTraceDetail = (traceId) => http.get(`/admin/traces/${traceId}`);
export const fetchFeedbackSummary = () => http.get("/admin/feedback/summary");
export const fetchFeedbackRecent = (params) => http.get("/admin/feedback/recent", { params });

/** 问题评价列表（管理员） */
export const fetchIssueReviews = (limit = 50) =>
  http.get("/admin/issue-reviews", { params: { limit } });

/** 产品意见反馈列表（管理员） */
export const fetchProductFeedback = (limit = 50) =>
  http.get("/admin/product-feedback", { params: { limit } });
