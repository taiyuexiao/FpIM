import { defineStore } from "pinia";
import { ElMessage } from "element-plus";
import { loadJson, normalizeContentRecord, saveJson, STORAGE_KEYS } from "../state.js";
import { connectAguiStream, fetchAguiSessionState } from "../services/agui/transport.js";
import { createMockAguiStream } from "../services/agui/mockStream.js";
import { reportInteractionEvent } from "../services/agui/reporter.js";
import { useAuthStore } from "./auth.js";
import { useContentStore } from "./content.js";
import { useDirectoryStore } from "./directory.js";
import { useReviewsStore } from "./reviews.js";
import { useSessionsStore } from "./sessions.js";

// 原始错误(英文异常/堆栈)只进 console,用户气泡只显示友好文案(§验收:无 BodyStreamBuffer 类原始错误)
function friendlyAguiError(raw) {
  const msg = String(raw || "");
  if (/abort/i.test(msg)) return "响应超时或已取消，请重试";
  if (/timeout|超时/i.test(msg)) return "响应超时，请重试";
  if (/failed to fetch|networkerror|load failed|request failed: 5\d\d/i.test(msg)) return "服务暂时不可用，请稍后重试";
  if (/request failed: 4\d\d/i.test(msg)) return "请求未被接受，请换个说法重试";
  if (!msg) return "AGUI 响应异常";
  return "回答生成失败，请换个说法重试";
}

export const useAguiStore = defineStore("agui", {
  state: () => ({
    activeRunId: "",
    streamStatus: "idle",
    cancelled: false, // 手动取消标记:取消导致的 AbortError 不当作错误展示
    messagesBySession: loadJson(STORAGE_KEYS.agui, {}).messagesBySession || {},
    cardsByMessage: loadJson(STORAGE_KEYS.agui, {}).cardsByMessage || {},
    pendingConfirmations: loadJson(STORAGE_KEYS.agui, {}).pendingConfirmations || {},
    // 输入框草稿(按会话):切页/刷新不丢
    composerDrafts: loadJson(STORAGE_KEYS.agui, {}).composerDrafts || {},
    activeDetail: { type: "empty" },
    isDetailSidebarVisible: false,
    lastError: "",
    abortController: null,
    timeoutHandle: null,
  }),
  getters: {
    activeMessages() {
      const session = useSessionsStore().activeSession;
      return session ? (this.messagesBySession[session.id] || []) : [];
    },
    isStreaming: (state) => state.streamStatus === "streaming",
  },
  actions: {
    persist() {
      saveJson(STORAGE_KEYS.agui, {
        messagesBySession: this.messagesBySession,
        cardsByMessage: this.cardsByMessage,
        pendingConfirmations: this.pendingConfirmations,
        composerDrafts: this.composerDrafts,
      });
    },
    setComposerDraft(sessionId, text) {
      if (!sessionId) return;
      if (text) this.composerDrafts[sessionId] = text;
      else delete this.composerDrafts[sessionId];
      this.persist();
    },
    ensureSession(sessionId) {
      if (!this.messagesBySession[sessionId]) this.messagesBySession[sessionId] = [];
    },
    // 会话历史回拉:本地无缓存时从 agent-service 恢复消息与卡片(切页/刷新后对话不丢)
    async loadSessionHistory(sessionId) {
      if (!sessionId || import.meta.env.VITE_AGUI_MODE !== "server") return;
      if ((this.messagesBySession[sessionId] || []).length) return;
      let state;
      try {
        state = await fetchAguiSessionState(sessionId);
      } catch (error) {
        console.warn("会话历史回拉失败", error);
        return;
      }
      if (!state) {
        this.ensureSession(sessionId);
        return;
      }
      const messages = [];
      for (const m of state.messages || []) {
        if (m.role === "user") {
          messages.push({ id: m.id, role: "user", text: m.text || "", createdAt: "" });
        } else if (m.role === "assistant") {
          messages.push({ id: m.id, role: "assistant", text: m.text || "", streaming: false, analysis: m.analysis || null, createdAt: "" });
          const cards = Array.isArray(m.cards) ? m.cards : [];
          if (cards.length) {
            this.cardsByMessage[m.id] = cards;
            for (const card of cards) {
              // 未确认的确认卡恢复为待确认,切页/刷新后仍可继续操作
              if (card.kind === "confirmation" && card.status !== "confirmed") {
                this.pendingConfirmations[card.id] = card;
              }
            }
          }
        }
      }
      // 回拉期间用户可能已发新消息,有内容则不覆盖
      if (!(this.messagesBySession[sessionId] || []).length) {
        this.messagesBySession[sessionId] = messages;
      }
      this.persist();
    },
    async sendMessage(sessionId, text) {
      if (!text?.trim() || this.isStreaming) return;
      const sessions = useSessionsStore();
      const directory = useDirectoryStore();
      const content = useContentStore();
      const reviews = useReviewsStore();
      const auth = useAuthStore();
      const runId = `run-${Date.now()}`;
      const userMessageId = `msg-u-${Date.now()}`;
      const assistantMessageId = `msg-a-${Date.now()}`;
      this.activeRunId = runId;
      this.cancelled = false;
      this.abortController = new AbortController();
      this.timeoutHandle = window.setTimeout(() => this.abortController?.abort(), 30000);
      this.streamStatus = "streaming";
      this.lastError = "";
      this.ensureSession(sessionId);
      this.messagesBySession[sessionId].push({
        id: userMessageId,
        role: "user",
        text: text.trim(),
        createdAt: new Date().toISOString(),
      });
      this.messagesBySession[sessionId].push({
        id: assistantMessageId,
        role: "assistant",
        text: "",
        streaming: true,
        analysis: null,
        createdAt: new Date().toISOString(),
      });
      sessions.patchSession(sessionId, {
        title: sessions.activeSession.title === "新对话" ? text.trim().slice(0, 28) : sessions.activeSession.title,
      });
      this.persist();

      const payload = {
        message: { id: userMessageId, role: "user", text: text.trim() },
        // assistantMessageId:服务端事件必须以此 ID 归属,否则前端无法匹配到助手气泡(server 模式契约)
        context: { userId: auth.userId, page: "ask", clientTraceId: runId, assistantMessageId },
      };
      const source = import.meta.env.VITE_AGUI_MODE === "server"
        ? connectAguiStream({ sessionId, payload, signal: this.abortController.signal, timeoutMs: 30000, retry: 1 })
        : createMockAguiStream({
            sessionId,
            runId,
            messageId: assistantMessageId,
            question: text.trim(),
            people: directory.activePeople,
            content: content.contents,
            reviewsForPerson: (personId) => reviews.reviewsForPerson(personId),
            currentUserId: auth.userId,
            authName: auth.displayName,
          });
      try {
        for await (const event of source) this.applyEvent(event);
      } catch (error) {
        if (error?.name === "AbortError" && this.cancelled) {
          // 用户手动取消:静默收尾,不覆盖气泡、不报错
          this.applyEvent({ type: "run_finished", sessionId, runId, messageId: assistantMessageId });
        } else {
          console.warn("AGUI 原始错误:", error);
          this.applyEvent({ type: "run_error", sessionId, runId, messageId: assistantMessageId, message: error.message });
        }
      }
    },
    applyEvent(event) {
      this.ensureSession(event.sessionId);
      if (event.type === "run_started") {
        const message = this.messagesBySession[event.sessionId].find((item) => item.id === event.messageId);
        if (message) {
          message.traceId = event.traceId || message.traceId;  // 反馈入库需 traceId 关联推荐日志
          if (event.result?.analysis) {
            message.analysis = event.result.analysis;
            message.result = event.result;
          }
        }
      }
      if (event.type === "text_delta") {
        const message = this.messagesBySession[event.sessionId].find((item) => item.id === event.messageId);
        if (message) message.text += event.delta || "";
      }
      if (event.type === "text_finished") {
        const message = this.messagesBySession[event.sessionId].find((item) => item.id === event.messageId);
        if (message) message.streaming = false;
      }
      if (event.type === "recommendation_cards") {
        this.cardsByMessage[event.messageId] = event.cards || [];
      }
      if (event.type === "confirmation_card") {
        this.cardsByMessage[event.messageId] = [event.card];
        this.pendingConfirmations[event.card.id] = event.card;
        if (event.card.action?.type === "profile") this.openProfileActionDetail(event.card.id);
      }
      if (event.type === "state_delta") {
        const sessions = useSessionsStore();
        const session = sessions.sessions.find((item) => item.id === event.sessionId);
        sessions.patchSession(event.sessionId, {
          title: session?.title === "新对话" ? event.patch?.title : session?.title,
          summary: [session?.summary, event.patch?.summary].filter(Boolean).join(" "),
          turnCount: (session?.turnCount || 0) + (event.patch?.turnCountIncrement || 0),
        });
      }
      if (event.type === "run_error") {
        this.lastError = friendlyAguiError(event.message);
        this.streamStatus = "error";
        if (this.timeoutHandle) window.clearTimeout(this.timeoutHandle);
        this.timeoutHandle = null;
        this.abortController = null;
        const message = this.messagesBySession[event.sessionId].find((item) => item.id === event.messageId);
        if (message) {
          message.text = this.lastError;
          message.streaming = false;
        }
      }
      if (event.type === "run_finished") {
        this.streamStatus = "idle";
        this.activeRunId = "";
        if (this.timeoutHandle) window.clearTimeout(this.timeoutHandle);
        this.timeoutHandle = null;
        this.abortController = null;
        // 取消/异常收尾时气泡可能还停在 streaming 状态,统一复位
        const doneMessage = (this.messagesBySession[event.sessionId] || []).find((item) => item.id === event.messageId);
        if (doneMessage) doneMessage.streaming = false;
      }
      this.persist();
    },
    openPersonDetail(personId, context = {}) {
      // question:该次推荐所回答的问题(邮件草稿的上下文,AskView 点击推荐卡时传入)
      this.activeDetail = { type: "person", personId, question: context.question || "" };
      this.isDetailSidebarVisible = true;
      reportInteractionEvent({ eventType: "person_detail_open", targetType: "person", targetId: personId, context });
    },
    openContentDetail(contentId, context = {}) {
      this.activeDetail = { type: "content", contentId };
      this.isDetailSidebarVisible = true;
      reportInteractionEvent({ eventType: "content_detail_open", targetType: "content", targetId: contentId, context });
    },
    openProfileActionDetail(cardId) {
      const card = this.pendingConfirmations[cardId];
      this.activeDetail = { type: "profileAction", action: card?.action, cardId };
      this.isDetailSidebarVisible = true;
    },
    openActionDetail(card) {
      const confirmed = card.status === "confirmed" || !!card.action?.confirmed;
      if (card.action?.type === "content") this.activeDetail = { type: "contentDraft", draft: card.action.nextContent, cardId: card.id, confirmed };
      else if (card.action?.type === "review") this.activeDetail = { type: "reviewAction", action: card.action, cardId: card.id, confirmed };
      else this.activeDetail = { type: "profileAction", action: card.action, cardId: card.id };
      this.isDetailSidebarVisible = true;
    },
    closeDetailSidebar() {
      this.isDetailSidebarVisible = false;
    },
    async confirmCard(cardId) {
      const card = this.pendingConfirmations[cardId];
      if (!card || card.status === "confirmed") return;
      const action = card.action;
      if (action.type === "profile") {
        const result = await useAuthStore().updateProfile(action.nextProfilePatch || {});
        if (result?.ok === false) {
          ElMessage.error(result.message || "资料更新失败");
          return;
        }
        ElMessage.success("个人主页已更新");
      }
      if (action.type === "review") {
        const result = await useReviewsStore().saveReview(action.nextReview);
        if (result?.ok === false) {
          ElMessage.error(result.message || "评价保存失败");
          return;
        }
        ElMessage.success("评价已保存");
      }
      if (action.type === "content") {
        const saved = await useContentStore().saveContent(normalizeContentRecord(action.nextContent));
        // 回填真实内容 ID,确认后「查看内容」才能跳转详情
        if (saved?.id) action.nextContent = { ...action.nextContent, id: saved.id };
        ElMessage.success("内容已提交审核");
      }
      action.confirmed = true;
      card.status = "confirmed";
      await reportInteractionEvent({ eventType: `confirm_${action.type}`, targetType: "confirmation_card", targetId: cardId });
      this.persist();
    },
    confirmProfileUpdate(cardId) {
      return this.confirmCard(cardId);
    },
    confirmContentPublish(cardId) {
      return this.confirmCard(cardId);
    },
    confirmReviewSave(cardId) {
      return this.confirmCard(cardId);
    },
    toggleFeedback(target) {
      return reportInteractionEvent({
        eventType: "feedback_toggle",
        targetType: target.targetType,
        targetId: target.targetId,
        value: target.value,
        context: target.context || {},
      });
    },
    cancelCurrentRun() {
      this.cancelled = true;
      if (this.abortController) this.abortController.abort();
      if (this.timeoutHandle) window.clearTimeout(this.timeoutHandle);
      this.streamStatus = "idle";
      this.activeRunId = "";
      this.abortController = null;
      this.timeoutHandle = null;
      reportInteractionEvent({ eventType: "run_cancelled", targetType: "run" });
    },
    resetSessionState(sessionId) {
      delete this.messagesBySession[sessionId];
      Object.keys(this.cardsByMessage).forEach((messageId) => {
        if (messageId.includes(sessionId)) delete this.cardsByMessage[messageId];
      });
      this.activeDetail = { type: "empty" };
      this.isDetailSidebarVisible = false;
      this.persist();
    },
  },
});
