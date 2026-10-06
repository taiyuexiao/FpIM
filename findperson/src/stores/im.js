/** IM 状态：会话列表 / 消息流 / 已读 / 在线态 / 问题关联。
 *
 * 分层：本 store 只处理业务状态；通道层的重连与心跳在 services/im/socket.js。
 * 发送路径：乐观上屏（pending）→ WS（失败则 HTTP 兜底）→ ack 用 clientMsgId 对齐替换。
 */
import { defineStore } from "pinia";

import {
  addMembers,
  createConversationIssue,
  createGroup,
  fetchConversation,
  fetchConversationIssues,
  fetchConversations,
  fetchMessages,
  markRead as apiMarkRead,
  openDirect,
  setConversationPrefs,
  updateGroup,
  removeMember,
  getDelegation,
  setDelegation as apiSetDelegation,
  clearConversationHistory,
  markConversationUnread,
  toggleReaction as apiToggleReaction,
  editMessage as apiEditMessage,
  hideMessage as apiHideMessage,
  forwardMessage as apiForwardMessage,
  transferOwner as apiTransferOwner,
  pinMessage as apiPinMessage,
  forwardCombined as apiForwardCombined,
  postMessage,
  revokeMessage,
  searchMessages as apiSearchMessages,
  searchMessagesGlobal as apiSearchMessagesGlobal,
  uploadFile,
} from "../services/api/im.js";
import { createImSocket, newClientMsgId } from "../services/im/socket.js";
import { useAuthStore } from "./auth.js";

export const useImStore = defineStore("im", {
  state: () => ({
    /** 会话列表（服务端返回，按最后消息倒序） */
    conversations: [],
    /** 当前打开的会话 id */
    activeId: null,
    /** { [conversationId]: Message[] } */
    messages: {},
    /** 每个会话是否还有更早的历史可翻 */
    hasMore: {},
    loadingMessages: false,
    /** 通道状态：idle | connecting | open | reconnecting | error | closed */
    connection: "idle",
    online: {},          // { [userId]: boolean }
    typing: {},          // { [conversationId]: { [userId]: true } }
    /** 当前会话关联的问题（含时间线） */
    issues: [],
    initialized: false,
    socket: null,
    draft: {},           // { [conversationId]: string } 输入框草稿
    quote: {},           // { [conversationId]: Message|null } 引用回复的目标消息
  }),

  getters: {
    active(state) {
      return state.conversations.find((c) => c.id === state.activeId) || null;
    },
    activeMessages(state) {
      return state.messages[state.activeId] || [];
    },
    totalUnread(state) {
      return state.conversations.reduce((sum, c) => sum + (c.unreadCount || 0), 0);
    },
    /** 会话展示名：群聊用群名，单聊用对方姓名 */
    titleOf() {
      return (conv) => conv?.title || conv?.peer?.name || "会话";
    },
    peerOf() {
      return (conv) => conv?.peer || null;
    },
  },

  actions: {
    // ── 初始化 ────────────────────────────────────────────────
    async init() {
      if (this.initialized) return;
      this.initialized = true;
      await this.loadConversations();
      this.connect();
    },

    async loadConversations() {
      const res = await fetchConversations();
      this.conversations = res.items || [];
    },

    connect() {
      if (this.socket) return;
      this.socket = createImSocket({
        getToken: () => localStorage.getItem("firstResponsibilityDemo.token"),
        handlers: {
          status: (s) => {
            this.connection = s.state;
            // 重连成功 → 增量补齐所有会话（不漏离线消息）
            if (s.state === "open") this.resyncAll();
          },
          message: (msg) => this.receiveMessage(msg),
          ack: (frame) => this.receiveAck(frame),
          read: (frame) => this.receiveRead(frame),
          typing: (frame) => this.receiveTyping(frame),
          reaction: (frame) => this.receiveReaction(frame),
          presence: (frame) => {
            this.online = { ...this.online, [frame.userId]: frame.online };
          },
          error: (frame) => console.warn("[im] 服务端错误", frame),
        },
      });
      this.socket.connect();
    },

    teardown() {
      if (this.socket) this.socket.close();
      this.socket = null;
      this.connection = "idle";
      this.initialized = false;
    },

    /** 重连后按各会话的 lastSeq 增量拉取，补齐离线期间的消息 */
    async resyncAll() {
      await this.loadConversations();
      const tasks = this.conversations.map(async (conv) => {
        const known = this.messages[conv.id];
        if (!known || !known.length) return;
        const lastSeq = known[known.length - 1].seq || 0;
        try {
          const res = await fetchMessages(conv.id, { afterSeq: lastSeq, limit: 100 });
          for (const msg of res.items || []) this.appendMessage(msg);
        } catch (err) {
          console.warn("[im] 增量补齐失败", conv.id, err);
        }
      });
      await Promise.allSettled(tasks);
    },

    // ── 会话 ──────────────────────────────────────────────────
    /** 从名片/问答结果发起会话：取或建单聊，然后跳进去 */
    async openWith(peerId, issueId = null) {
      const conv = await openDirect(peerId, issueId);
      await this.loadConversations();
      await this.selectConversation(conv.id);
      return conv;
    },

    async newGroup(title, memberIds, issueId = null) {
      const conv = await createGroup(title, memberIds, issueId);
      await this.loadConversations();
      await this.selectConversation(conv.id);
      return conv;
    },

    async invite(cid, memberIds) {
      await addMembers(cid, memberIds);
      const detail = await fetchConversation(cid);
      const idx = this.conversations.findIndex((c) => c.id === cid);
      if (idx >= 0) this.conversations[idx] = { ...this.conversations[idx], ...detail };
      return detail;
    },

    async selectConversation(cid) {
      this.activeId = cid;
      this.issues = [];
      const conv = this.conversations.find((c) => c.id === cid);
      // 会话详情（成员/群主/群公告）合并进列表项：群聊 UI 与责任人候选都依赖它
      try {
        const detail = await fetchConversation(cid);
        if (detail && conv) Object.assign(conv, detail);
      } catch {
        /* 详情失败不阻塞消息加载 */
      }
      if (!this.messages[cid]) {
        this.messages[cid] = [];
        await this.loadMessages(cid);
      }
      // 打开即已读（红点消失）；问题级"首次已读"留痕由后端只认责任人
      const msgs = this.messages[cid] || [];
      const lastSeq = msgs.length ? msgs[msgs.length - 1].seq : conv?.lastSeq || 0;
      if (lastSeq) await this.markRead(lastSeq);
      await this.loadIssues(cid);
    },

    async loadMessages(cid, beforeSeq = null) {
      this.loadingMessages = true;
      try {
        const res = await fetchMessages(cid, { beforeSeq, limit: 30 });
        const items = res.items || [];
        if (beforeSeq) {
          this.messages[cid] = [...items, ...(this.messages[cid] || [])];
        } else {
          this.messages[cid] = items;
        }
        // 返回条数不足一页 → 说明到头了
        this.hasMore[cid] = items.length >= 30;
      } finally {
        this.loadingMessages = false;
      }
    },

    loadMore(cid) {
      const msgs = this.messages[cid] || [];
      const firstSeq = msgs.length ? msgs[0].seq : null;
      if (!firstSeq || this.hasMore[cid] === false) return Promise.resolve();
      return this.loadMessages(cid, firstSeq);
    },

    async loadIssues(cid) {
      try {
        const res = await fetchConversationIssues(cid);
        this.issues = res.items || [];
      } catch (err) {
        console.warn("[im] 拉取会话问题失败", err);
      }
    },

    /** 在会话内立项：建问题 + 挂锚点；成功后立即把立项卡插进消息流并刷新问题面板 */
    async createIssue(cid, payload) {
      const res = await createConversationIssue(cid, payload);
      if (res.message) this.appendMessage(res.message);
      await this.loadIssues(cid);
      return res.issue;
    },

    // ── 消息接收 ──────────────────────────────────────────────
    appendMessage(msg) {
      // 会话内 seq 去重：WS 广播与增量补齐可能重叠；
      // 同 id 已存在 → 视为「更新」（编辑广播复用 message 帧），替换原文不计未读
      this.messages[msg.conversationId] ||= [];
      const list = this.messages[msg.conversationId];
      const idx = list.findIndex((m) => (m.id && m.id === msg.id) || (m.seq && m.seq === msg.seq));
      if (idx >= 0) {
        if (msg.id && list[idx].id === msg.id) {
          list.splice(idx, 1, msg);
          return "updated";
        }
        return false;
      }
      list.push(msg);
      list.sort((a, b) => a.seq - b.seq);
      return "added";
    },

    receiveMessage(msg) {
      const outcome = this.appendMessage(msg);
      const added = outcome === "added";
      const conv = this.conversations.find((c) => c.id === msg.conversationId);
      if (conv && outcome !== "updated") {
        conv.lastMessage = msg;
        conv.lastSeq = Math.max(conv.lastSeq || 0, msg.seq);
        conv.lastMessageAt = msg.createdAt;
        if (this.activeId !== msg.conversationId) {
          conv.unreadCount = (conv.unreadCount || 0) + (added ? 1 : 0);
        }
      } else if (!conv) {
        this.loadConversations();
      }
      // 问题类消息会改变问题状态 → 同步刷新右侧问题面板
      if (["issue_card", "resolve_confirm"].includes(msg.msgType) &&
          msg.conversationId === this.activeId) {
        this.loadIssues(msg.conversationId);
      }
      // 打开中的会话收到新消息 → 立即推进已读游标（带 issueId，供问题级首次已读留痕）
      if (this.activeId === msg.conversationId && this.socket) {
        const issueId = conv?.issueId || this.issues[0]?.id || null;
        this.socket.sendRead({ conversationId: msg.conversationId, seq: msg.seq, issueId });
        if (conv) conv.unreadCount = 0;
      }
    },

    receiveAck(frame) {
      const list = this.messages[frame.message.conversationId];
      if (!list) return;
      const idx = list.findIndex((m) => m.clientMsgId && m.clientMsgId === frame.clientMsgId);
      if (idx >= 0) list.splice(idx, 1, { ...frame.message, pending: false });
      else this.appendMessage(frame.message);
    },

    receiveRead(frame) {
      if (frame.result) {
        this.peerReadSeq = { ...(this.peerReadSeq || {}),
          [frame.conversationId]: frame.seq };
      }
      // 推进会话详情里该成员的已读游标（单聊已读回执标记实时更新）
      const conv = this.conversations.find((c) => c.id === frame.conversationId);
      const member = conv?.members?.find((m) => m.id === frame.userId);
      if (member) member.lastReadSeq = Math.max(member.lastReadSeq || 0, frame.seq || 0);
      if (conv && frame.userId !== conv.peer?.id) return;
    },

    receiveTyping(frame) {
      this.typing[frame.conversationId] ||= {};
      this.typing[frame.conversationId][frame.userId] = true;
      setTimeout(() => {
        if (this.typing[frame.conversationId]) {
          delete this.typing[frame.conversationId][frame.userId];
        }
      }, 3000);
    },

    // ── 发送 ──────────────────────────────────────────────────
    async sendText(text, { issueId = null, replyToId = null, mentions = [], clientMsgId = null } = {}) {
      const cid = this.activeId;
      const body = (text || "").trim();
      if (!cid || !body) return;

      clientMsgId = clientMsgId || newClientMsgId();
      const content = mentions.length ? { text: body, mentions } : { text: body };
      const optimistic = {
        id: `tmp-${clientMsgId}`,
        conversationId: cid,
        seq: Number.MAX_SAFE_INTEGER,   // 临时排到末尾，ack 后按真实 seq 复位
        senderId: "me",
        msgType: "text",
        content,
        clientMsgId,
        issueId,
        replyToId,
        createdAt: new Date().toISOString(),
        pending: true,
      };
      this.messages[cid] ||= [];
      this.messages[cid].push(optimistic);
      this.draft[cid] = "";
      this._armUnknownTimer(cid, clientMsgId);

      const viaWs = this.socket?.sendMessage({
        conversationId: cid, text: body, content, issueId, clientMsgId, replyToId,
      });
      if (viaWs) return;
      // WS 不可用 → HTTP 兜底（同样幂等）
      const res = await postMessage(cid, { text: body, content, clientMsgId, issueId, replyToId });
      const idx = this.messages[cid].findIndex((m) => m.clientMsgId === clientMsgId);
      if (idx >= 0) this.messages[cid].splice(idx, 1, { ...res.message, pending: false });
    },

    async sendFile(file, { issueId = null } = {}) {
      const cid = this.activeId;
      if (!cid || !file) return;
      const meta = await uploadFile(file);
      const content = {
        url: meta.url,
        name: meta.name,
        size: meta.size,
        sizeHuman: meta.sizeHuman,
        mime: meta.mime,
        sha256: meta.sha256,
      };
      const isImage = (meta.mime || "").startsWith("image/");
      const msgType = isImage ? "image" : "file";
      const clientMsgId = newClientMsgId();

      const viaWs = this.socket?.sendMessage({
        conversationId: cid, msgType, content, issueId, clientMsgId,
      });
      if (!viaWs) {
        const res = await postMessage(cid, { msgType, content, clientMsgId, issueId });
        this.appendMessage(res.message);
      }
      return meta;
    },

    async markRead(seq) {
      const cid = this.activeId;
      if (!cid || !seq) return;
      const conv = this.conversations.find((c) => c.id === cid);
      const issueId = conv?.issueId || this.issues[0]?.id || null;
      if (this.socket?.isOpen()) {
        this.socket.sendRead({ conversationId: cid, seq, issueId });
      } else {
        await apiMarkRead(cid, seq, issueId);
      }
      if (conv) conv.unreadCount = 0;
    },

    async revoke(mid) {
      await revokeMessage(mid);
      const list = this.messages[this.activeId] || [];
      const msg = list.find((m) => m.id === mid);
      if (msg) {
        msg.revoked = true;
        msg.content = {};
      }
    },

    // ── 引用回复 / 搜索 ───────────────────────────────────────
    setQuote(msg) {
      if (this.activeId) this.quote[this.activeId] = msg || null;
    },
    clearQuote() {
      if (this.activeId) this.quote[this.activeId] = null;
    },

    /** 会话内消息搜索（正文/文件名模糊匹配） */
    async searchMessages(q) {
      if (!this.activeId) return [];
      const res = await apiSearchMessages(this.activeId, q);
      return res.items || [];
    },

    /** 全局消息搜索（跨会话） */
    async searchMessagesGlobal(q) {
      const res = await apiSearchMessagesGlobal(q);
      return res.items || [];
    },

    /** 从搜索结果跳转：把目标消息附近的窗口装进消息流（目标高亮由 MessageList 处理） */
    async jumpToMessage(msg) {
      const cid = this.activeId;
      if (!cid || !msg?.seq) return;
      const res = await fetchMessages(cid, { beforeSeq: msg.seq + 1, limit: 31 });
      this.messages[cid] = res.items || [];
      this.hasMore[cid] = true;
    },

    notifyTyping() {
      if (this.activeId) this.socket?.sendTyping(this.activeId);
    },

    // ── 会话偏好 / 清空 / 表情回应 ──────────────────────────────
    /** 私聊代理（二期 R2）：off | draft | auto */
    async setDelegationMode(mode) {
      const cid = this.activeId;
      if (!cid) return;
      return (await apiSetDelegation(cid, mode)).item;
    },

    async loadDelegation() {
      const cid = this.activeId;
      if (!cid) return null;
      return (await getDelegation(cid)).item || null;
    },

    /** 群信息编辑（仅群主）：群名 / 群公告 */
    async updateGroupInfo(patch) {
      const cid = this.activeId;
      if (!cid) return;
      const res = await updateGroup(cid, patch);
      const conv = this.conversations.find((c) => c.id === cid);
      if (conv && res.title) conv.title = res.title;
      // 系统消息经服务层写入后，重拉消息流展示留痕
      await this.loadMessages(cid);
      await this.loadConversations();
      return res;
    },

    /** 移出成员 / 退群；自己退群后关掉当前会话 */
    async removeMember(targetId) {
      const cid = this.activeId;
      if (!cid) return;
      await removeMember(cid, targetId);
      if (targetId === useAuthStore().userId) {
        this.activeId = null;   // 自己退群：关掉会话
      } else {
        const conv = this.conversations.find((c) => c.id === cid);
        if (conv?.members) conv.members = conv.members.filter((m) => m.id !== targetId);
        await this.loadMessages(cid);
      }
      await this.loadConversations();
    },

    async setPrefs(patch) {
      const cid = this.activeId;
      if (!cid) return;
      const res = await setConversationPrefs(cid, patch);
      const conv = this.conversations.find((c) => c.id === cid);
      if (conv) Object.assign(conv, res);
    },

    /** 标为未读（仅自己的提醒标记） */
    async markUnread() {
      const cid = this.activeId;
      if (!cid) return;
      const res = await markConversationUnread(cid);
      const conv = this.conversations.find((c) => c.id === cid);
      if (conv) Object.assign(conv, res);
    },

    /** 清空聊天记录（仅清自己的视图；留痕数据保留） */
    async clearHistory() {
      const cid = this.activeId;
      if (!cid) return;
      await clearConversationHistory(cid);
      this.messages[cid] = [];
      this.hasMore[cid] = true;
    },

    /** 仅自己删除：本地移除（其他成员不受影响） */
    async hideMessage(mid) {
      await apiHideMessage(mid);
      const list = this.messages[this.activeId] || [];
      const idx = list.findIndex((m) => m.id === mid);
      if (idx >= 0) list.splice(idx, 1);
    },

    /** 发送人员名片卡（share_user） */
    async sendShareUser(person) {
      const cid = this.activeId;
      if (!cid || !person?.id) return;
      const content = {
        personId: person.id,
        name: person.name,
        department: person.department || "",
        role: person.role || "",
      };
      const clientMsgId = newClientMsgId();
      const viaWs = this.socket?.sendMessage({
        conversationId: cid, msgType: "share_user", content, clientMsgId,
      });
      if (!viaWs) {
        const res = await postMessage(cid, { msgType: "share_user", content, clientMsgId });
        this.appendMessage(res.message);
      }
    },

    /** 10s 未 ack → 「状态待核实」（04-方案 §3.5 发送状态机） */
    _armUnknownTimer(cid, clientMsgId) {
      setTimeout(() => {
        const list = this.messages[cid] || [];
        const msg = list.find((m) => m.clientMsgId === clientMsgId);
        if (msg && msg.pending) {
          msg.pending = false;
          msg.status = "unknown";
        }
      }, 10000);
    },

    /** 重发：同一 clientMsgId（幂等键不变，服务端去重兜底） */
    async resend(msg) {
      const cid = this.activeId;
      if (!cid || !msg) return;
      const list = this.messages[cid] || [];
      const idx = list.findIndex((m) => m.clientMsgId === msg.clientMsgId);
      if (idx >= 0) list.splice(idx, 1);
      await this.sendText(msg.content?.text || "", {
        issueId: msg.issueId || null,
        replyToId: msg.replyToId || null,
        clientMsgId: msg.clientMsgId,
      });
    },

    /** 编辑消息：本地替换 + 广播帧负责多端同步 */
    async editMessage(mid, text) {
      const res = await apiEditMessage(mid, text);
      const msg = res.message;
      const list = this.messages[msg.conversationId] || [];
      const idx = list.findIndex((m) => m.id === mid);
      if (idx >= 0) list.splice(idx, 1, msg);
      return msg;
    },

    /** 转让群主 */
    async transferOwner(newOwnerId) {
      const cid = this.activeId;
      if (!cid) return;
      await apiTransferOwner(cid, newOwnerId);
      const conv = this.conversations.find((c) => c.id === cid);
      if (conv) conv.ownerId = newOwnerId;
      await this.loadMessages(cid);
    },

    /** 置顶/取消置顶消息（null=取消） */
    async setPinnedMessage(messageId) {
      const cid = this.activeId;
      if (!cid) return;
      const detail = await apiPinMessage(cid, messageId);
      const conv = this.conversations.find((c) => c.id === cid);
      if (conv) Object.assign(conv, detail);
      return detail;
    },

    /** 合并转发 */
    async forwardCombined(messageIds, targetConversationId, note = "") {
      const res = await apiForwardCombined(messageIds, targetConversationId, note);
      if (targetConversationId === this.activeId) this.appendMessage(res.message);
      return res.message;
    },

    /** 单条转发到目标会话 */
    async forwardMessage(mid, targetConversationId, note = "") {
      const res = await apiForwardMessage(mid, targetConversationId, note);
      if (targetConversationId === this.activeId) this.appendMessage(res.message);
      return res.message;
    },

    /** 表情回应开关：本地先更新，广播帧负责多端同步 */
    async toggleReaction(mid, emoji) {
      const res = await apiToggleReaction(mid, emoji);
      this._applyReactions(this.activeId, mid, res.reactions);
    },

    receiveReaction(frame) {
      if (!frame?.messageId) return;
      this._applyReactions(frame.conversationId, frame.messageId, frame.reactions || []);
    },

    _applyReactions(cid, mid, reactions) {
      const list = this.messages[cid] || [];
      const msg = list.find((m) => m.id === mid);
      if (msg) msg.reactions = reactions;
    },
  },
});
