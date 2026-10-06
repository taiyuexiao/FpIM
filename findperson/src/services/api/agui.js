import http from "./http.js";

export const createAguiSession = (payload) => http.post("/agui/sessions", payload);
export const sendAguiMessage = (sessionId, payload) => http.post(`/agui/sessions/${sessionId}/messages`, payload);
export const reportAguiEvent = (payload) => http.post("/agui/events", payload);
export const fetchAguiState = (sessionId) => http.get(`/agui/sessions/${sessionId}/state`);
