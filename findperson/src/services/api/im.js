import http from "./http.js";

/** 我的会话列表 */
export const fetchConversations = (params) => http.get("/im/conversations", { params });

/** 取或建单聊（免加好友，任何人可直接对话） */
export const openDirect = (peerId, issueId = null) =>
  http.post("/im/conversations/direct", { peerId, issueId });

/** 建群（单群上限 100 人） */
export const createGroup = (title, memberIds, issueId = null) =>
  http.post("/im/conversations/group", { title, memberIds, issueId });

/** 会话详情（含成员） */
export const fetchConversation = (cid) => http.get(`/im/conversations/${cid}`);

/** 群聊拉人 */
export const addMembers = (cid, memberIds) =>
  http.post(`/im/conversations/${cid}/members`, { memberIds });

/** 历史 / 增量消息：afterSeq 增量补齐，beforeSeq 向上翻页 */
export const fetchMessages = (cid, { beforeSeq, afterSeq, limit = 30 } = {}) =>
  http.get(`/im/conversations/${cid}/messages`, {
    params: { beforeSeq, afterSeq, limit },
  });

/** HTTP 兜底发消息（WS 不可用时） */
export const postMessage = (cid, payload) =>
  http.post(`/im/conversations/${cid}/messages`, payload);

/** 推进已读游标；带 issueId 时同时写问题级首次已读留痕 */
export const markRead = (cid, seq, issueId = null) =>
  http.post(`/im/conversations/${cid}/read`, { seq, issueId });

/** 撤回（2 分钟内） */
export const revokeMessage = (mid) => http.delete(`/im/messages/${mid}`);

/** 会话关联的问题 + 各自时间线 */
export const fetchConversationIssues = (cid) => http.get(`/im/conversations/${cid}/issues`);

/** 在会话内立项：单聊可不带责任人（默认对方），群聊必须指定 */
export const createConversationIssue = (cid, payload) =>
  http.post(`/im/conversations/${cid}/issues`, payload);

/** 上传附件（内容寻址，同内容秒传） */
export const uploadFile = (file) => {
  const form = new FormData();
  form.append("file", file, file.name);
  return http.post("/im/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
};
