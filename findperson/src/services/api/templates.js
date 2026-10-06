import http from "./http.js";

/** 由已解决问题沉淀模板（question+solution+责任人） */
export const promoteTemplate = (issueId, payload) =>
  http.post(`/issues/${issueId}/promote-template`, payload);

/** 模板列表（public + 我的 private） */
export const listTemplates = (params) => http.get("/templates", { params });

/** 模板匹配（首问检索联动：模板 + 责任人） */
export const matchTemplates = (q, limit = 5) =>
  http.get("/templates/match", { params: { q, limit } });

/** 发送模板卡片到会话（同库留痕） */
export const sendTemplate = (templateId, payload) =>
  http.post(`/templates/${templateId}/send`, payload);
