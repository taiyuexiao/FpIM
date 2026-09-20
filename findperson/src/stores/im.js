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
  postMessage,
  revokeMessage,
  uploadFile,
} from "../services/api/im.js";
import { createImSocket, newClientMsgId } from "../services/im/socket.js";

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
      // 会话内 seq 去重：WS 广播与增量补齐可能重叠
      this.messages[msg.conversationId] ||= [];
      const list = this.messages[msg.conversationId];
      if (list.some((m) => m.seq === msg.seq || (m.id && m.id === msg.id))) return false;
      list.push(msg);
      list.sort((a, b) => a.seq - b.seq);
      return true;
    },

    receiveMessage(msg) {
      const added = this.appendMessage(msg);
      const conv = this.conversations.find((c) => c.id === msg.conversationId);
      if (conv) {
        conv.lastMessage = msg;
        conv.lastSeq = Math.max(conv.lastSeq || 0, msg.seq);
        conv.lastMessageAt = msg.createdAt;
        if (this.activeId !== msg.conversationId) {
          conv.unreadCount = (conv.unreadCount || 0) + (added ? 1 : 0);
        }
      } else {
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
      const conv = this.conversations.find((c) => c.id === frame.conversationId);
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
    async sendText(text, { issueId = null } = {}) {
      const cid = this.activeId;
      const body = (text || "").trim();
      if (!cid || !body) return;

      const clientMsgId = newClientMsgId();
      const optimistic = {
        id: `tmp-${clientMsgId}`,
        conversationId: cid,
        seq: Number.MAX_SAFE_INTEGER,   // 临时排到末尾，ack 后按真实 seq 复位
        senderId: "me",
        msgType: "text",
        content: { text: body },
        clientMsgId,
        issueId,
        createdAt: new Date().toISOString(),
        pending: true,
      };
      this.messages[cid] ||= [];
      this.messages[cid].push(optimistic);
      this.draft[cid] = "";

      const viaWs = this.socket?.sendMessage({
        conversationId: cid, text: body, issueId, clientMsgId,
      });
      if (viaWs) return;
      // WS 不可用 → HTTP 兜底（同样幂等）
      const res = await postMessage(cid, { text: body, clientMsgId, issueId });
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

    notifyTyping() {
      if (this.activeId) this.socket?.sendTyping(this.activeId);
    },
  },
});
