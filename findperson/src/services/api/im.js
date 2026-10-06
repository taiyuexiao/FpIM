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

/** 会话内消息搜索（正文/文件名模糊匹配） */
export const searchMessages = (cid, q, limit = 50) =>
  http.get(`/im/conversations/${cid}/messages/search`, { params: { q, limit } });

/** 全局消息搜索（跨我参与的会话） */
export const searchMessagesGlobal = (q, limit = 50) =>
  http.get("/im/messages/search", { params: { q, limit } });

/** 推进已读游标；带 issueId 时同时写问题级首次已读留痕 */
export const markRead = (cid, seq, issueId = null) =>
  http.post(`/im/conversations/${cid}/read`, { seq, issueId });

/** 撤回（2 分钟内） */
export const revokeMessage = (mid) => http.delete(`/im/messages/${mid}`);

/** 仅自己删除消息（留痕数据保留） */
export const hideMessage = (mid) => http.post(`/im/messages/${mid}/hide`);

/** 编辑群信息（仅群主）：群名称 / 群公告 */
export const updateGroup = (cid, patch) => http.patch(`/im/conversations/${cid}`, patch);

/** 移出成员 / 退群（群主移他人；任何人退自己） */
export const removeMember = (cid, targetId) =>
  http.delete(`/im/conversations/${cid}/members/${encodeURIComponent(targetId)}`);

/** 读取私聊代理设置（二期 R2） */
export const getDelegation = (cid) => http.get(`/im/conversations/${cid}/delegation`);

/** 设置私聊代理：off | draft | auto */
export const setDelegation = (cid, mode) =>
  http.put(`/im/conversations/${cid}/delegation`, { mode });

/** 会话偏好：置顶 / 消息免打扰（只影响自己） */
export const setConversationPrefs = (cid, patch) =>
  http.patch(`/im/conversations/${cid}/prefs`, patch);

/** 标为未读（仅自己的提醒标记） */
export const markConversationUnread = (cid) =>
  http.post(`/im/conversations/${cid}/mark-unread`);

/** 清空聊天记录（仅清自己的视图，留痕数据保留） */
export const clearConversationHistory = (cid) =>
  http.post(`/im/conversations/${cid}/clear`);

/** 编辑消息（本人、24h 内、≤20 次、仅文本） */
export const editMessage = (mid, text) => http.patch(`/im/messages/${mid}`, { text });

/** 转发消息到目标会话 */
export const forwardMessage = (mid, targetConversationId, note = "") =>
  http.post(`/im/messages/${mid}/forward`, { targetConversationId, note });

/** 转让群主（仅现任群主） */
export const transferOwner = (cid, newOwnerId) =>
  http.post(`/im/conversations/${cid}/transfer-owner`, { newOwnerId });

/** 置顶消息（每会话一条）；messageId 缺省即取消 */
export const pinMessage = (cid, messageId = null) =>
  http.post(`/im/conversations/${cid}/pin`, { messageId });

/** 取消置顶消息 */
export const unpinMessage = (cid) => http.delete(`/im/conversations/${cid}/pin`);

/** 合并转发：多条消息打包成一条 composite 卡片 */
export const forwardCombined = (messageIds, targetConversationId, note = "") =>
  http.post("/im/messages/forward-combined", { messageIds, targetConversationId, note });

/** 表情回应开关：没发过就加，再点撤回 */
export const toggleReaction = (mid, emoji) =>
  http.post(`/im/messages/${mid}/reactions/${encodeURIComponent(emoji)}`);

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
