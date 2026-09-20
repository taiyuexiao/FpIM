import { defineStore } from "pinia";
import { createSession, normalize } from "../state.js";
import {
  createSession as createServerSession,
  deleteSession as deleteServerSession,
  fetchSessions,
  updateSession,
} from "../services/api/sessions.js";
import { getMockSessions, saveMockSessions } from "../services/mock/mockApi.js";
import { isServerMode } from "../services/mode.js";

function normalizeSession(session) {
  return {
    id: session.id,
    title: session.title || "新对话",
    turnCount: session.turnCount ?? session.conversation?.length ?? 0,
    summary: session.summary || "",
    updatedAt: session.updatedAt || "",
  };
}

export const useSessionsStore = defineStore("sessions", {
  state: () => ({
    activeSessionId: "",
    sessions: [],
    loaded: false,
  }),
  getters: {
    activeSession(state) {
      return state.sessions.find((item) => item.id === state.activeSessionId) || state.sessions[0];
    },
  },
  actions: {
    init() {
      if (this.sessions.length) return;
      const stored = getMockSessions().map(normalizeSession);
      this.sessions = stored.length ? stored : [normalizeSession(createSession())];
      this.activeSessionId = this.sessions[0].id;
      this.persist();
    },
    async loadSessions() {
      // 已加载过就直接复用(含 server 模式):路由守卫每次导航都会调用
      if (this.loaded) return;
      const loaded = isServerMode() ? await fetchSessions() : getMockSessions();
      this.sessions = (loaded.length ? loaded : [createSession()]).map(normalizeSession);
      if (!this.sessions.some((item) => item.id === this.activeSessionId)) this.activeSessionId = this.sessions[0].id;
      this.loaded = true;
      this.persist();
    },
    persist() {
      if (!isServerMode()) saveMockSessions(this.sessions);
    },
    ensureActiveSession() {
      this.init();
      if (!this.activeSessionId) this.activeSessionId = this.sessions[0].id;
      return this.activeSession;
    },
    createOrReuseBlankSession() {
      this.init();
      // 仅当前激活会话本身是空白时才复用;否则总是新建全新会话。
      // (server 模式下历史可能遗留 0 轮空白会话,直接 find 会跳到旧会话,验收:新对话必须是全新的)
      const active = this.activeSession;
      if (active && !active.turnCount) {
        this.activeSessionId = active.id;
        return active;
      }
      const session = normalizeSession(createSession());
      this.sessions.unshift(session);
      this.activeSessionId = session.id;
      this.persist();
      if (isServerMode()) createServerSession(session).catch(console.warn);
      return session;
    },
    selectSession(sessionId) {
      this.init();
      if (this.sessions.some((item) => item.id === sessionId)) this.activeSessionId = sessionId;
    },
    renameSession(sessionId, title) {
      const session = this.sessions.find((item) => item.id === sessionId);
      if (session) {
        session.title = title || "新对话";
        this.persist();
        if (isServerMode()) updateSession(sessionId, { title: session.title }).catch(console.warn);
      }
    },
    deleteSession(sessionId) {
      this.sessions = this.sessions.filter((item) => item.id !== sessionId);
      if (!this.sessions.length) this.sessions = [normalizeSession(createSession())];
      if (this.activeSessionId === sessionId) this.activeSessionId = this.sessions[0].id;
      this.persist();
      if (isServerMode()) deleteServerSession(sessionId).catch(console.warn);
    },
    patchSession(sessionId, patch) {
      const session = this.sessions.find((item) => item.id === sessionId);
      if (!session) return;
      Object.assign(session, patch, { updatedAt: new Date().toISOString() });
      this.persist();
      if (isServerMode()) updateSession(sessionId, patch).catch(console.warn);
    },
    searchSessions(keyword) {
      const key = normalize(keyword);
      return this.sessions
        .filter((session) => {
          if (!key) return true;
          return normalize(`${session.title} ${session.summary}`).includes(key);
        })
        .slice(0, 8);
    },
  },
});
