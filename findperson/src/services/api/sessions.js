import http from "./http.js";

// GET /sessions 返回 PaginatedResponse{items,...}(snake_case),这里统一解包并映射为前端会话结构
export const fetchSessions = async () => {
  const result = await http.get("/sessions", { params: { page_size: 100 } });
  const items = Array.isArray(result) ? result : (result?.items || []);
  return items.map((s) => ({
    id: s.id,
    title: s.title || "新对话",
    summary: s.summary || "",
    turnCount: s.turnCount ?? s.turn_count ?? 0,
    updatedAt: s.updatedAt || s.updated_at || "",
  }));
};
export const createSession = (payload) => http.post("/sessions", payload);
export const updateSession = (id, payload) => http.patch(`/sessions/${id}`, payload);
export const deleteSession = (id) => http.delete(`/sessions/${id}`);
export const fetchSessionMessages = (id) => http.get(`/sessions/${id}/messages`);
