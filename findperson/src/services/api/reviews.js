import http from "./http.js";

export const createReview = (payload) => http.post("/reviews", payload);
export const fetchSentReviews = () => http.get("/reviews/sent");
export const fetchPersonReviews = (personId) => http.get(`/people/${personId}/reviews`);
export const fetchPersonReviewHistory = (personId) => http.get(`/reviews/person/${personId}/history`, { params: { page_size: 100 } });
export const deleteReview = (id) => http.delete(`/reviews/${id}`);
// 信任分级:我收到的待放行标签 + 放行/忽略
export const fetchPendingReviews = () => http.get("/reviews/pending");
export const approveReview = (id) => http.post(`/reviews/${id}/approve`);
export const ignoreReview = (id) => http.post(`/reviews/${id}/ignore`);
