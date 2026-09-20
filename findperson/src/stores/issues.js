import { defineStore } from "pinia";
import { fetchAssignedIssues, fetchIssues, fetchIssueDetail, syncIssues, updateIssue } from "../services/api/issues.js";
import { isServerMode } from "../services/mode.js";

/** 问题状态文案(与后端 issues.status 对应) */
export const ISSUE_STATUS = {
  not_contacted: "未联系",
  processing: "处理中",
  resolved: "已解决",
  unresolved: "未解决",
};

export const ISSUE_TABS = [
  { value: "", label: "全部" },
  { value: "not_contacted", label: "未联系" },
  { value: "processing", label: "处理中" },
  { value: "resolved", label: "已解决" },
  { value: "unresolved", label: "未解决" },
];

export const useIssuesStore = defineStore("issues", {
  state: () => ({
    items: [],
    counts: { not_contacted: 0, processing: 0, resolved: 0, unresolved: 0 },
    filter: "",
    loading: false,
    syncing: false,
    details: {}, // issueId -> { issue, events, mails }
    // 待我处理（我作为责任人）
    assignedItems: [],
    assignedCounts: { not_contacted: 0, processing: 0, resolved: 0, unresolved: 0 },
  }),
  getters: {
    total: (state) => Object.values(state.counts).reduce((sum, n) => sum + n, 0),
    statusText: () => (status) => ISSUE_STATUS[status] || status,
    /** 侧栏「待办」红点：我名下未完结的问题数（未联系 + 处理中） */
    assignedOpen: (state) => (state.assignedCounts.not_contacted || 0) + (state.assignedCounts.processing || 0),
  },
  actions: {
    async load(status = this.filter) {
      if (!isServerMode()) return;
      this.loading = true;
      try {
        const data = await fetchIssues(status);
        this.items = data.items || [];
        this.counts = { ...this.counts, ...(data.counts || {}) };
      } finally {
        this.loading = false;
      }
    },
    /** 待我处理（我作为责任人）；status=null 拉全部 */
    async loadAssigned(status = "") {
      if (!isServerMode()) return;
      try {
        const data = await fetchAssignedIssues(status || null);
        this.assignedItems = data.items || [];
        this.assignedCounts = { ...this.assignedCounts, ...(data.counts || {}) };
      } catch (err) {
        console.warn("[issues] 待办加载失败", err);
      }
    },
    async setFilter(status) {
      this.filter = status;
      await this.load(status);
    },
    /** 从问答记录同步(返回 created/merged/invalid,便于提示用户) */
    async sync(limit = 30) {
      this.syncing = true;
      try {
        const result = await syncIssues(limit);
        await this.load();
        return result;
      } finally {
        this.syncing = false;
      }
    },
    async setStatus(id, status, extra = {}) {
      const updated = await updateIssue(id, { status, ...extra });
      const idx = this.items.findIndex((item) => item.id === id);
      if (idx >= 0) this.items[idx] = { ...this.items[idx], ...updated };
      await this.load();
      if (this.details[id]) await this.loadDetail(id, true);
      return updated;
    },
    async addNote(id, note) {
      await updateIssue(id, { note });
      await this.loadDetail(id, true);
      await this.load();
    },
    async loadDetail(id, force = false) {
      if (!force && this.details[id]) return this.details[id];
      const detail = await fetchIssueDetail(id);
      this.details[id] = detail;
      return detail;
    },
  },
});
