import http from "./http.js";

/** 新增知识（可授权分享给群） */
export const createKnowledge = (payload) => http.post("/agent/knowledge", payload);

/** 我的知识列表 */
export const listKnowledge = () => http.get("/agent/knowledge");

/** 更新知识（含分享范围） */
export const updateKnowledge = (id, payload) => http.put(`/agent/knowledge/${id}`, payload);

/** 撤销知识 */
export const revokeKnowledge = (id) => http.delete(`/agent/knowledge/${id}`);
