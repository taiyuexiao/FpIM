import http from "./http.js";

export const fetchContents = (params) => http.get("/contents", { params });
export const createContent = (payload) => http.post("/contents", payload);
export const fetchContent = (id) => http.get(`/contents/${id}`);
export const updateContent = (id, payload) => http.put(`/contents/${id}`, payload);
export const deleteContent = (id) => http.delete(`/contents/${id}`);
export const toggleContentPin = (id, payload) => http.post(`/contents/${id}/pin`, payload);
