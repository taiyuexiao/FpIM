import { defineStore } from "pinia";
import {
  currentUserId,
  getActiveUserId,
  getTodayText,
  normalize,
  normalizeContentRecord,
  splitTags,
} from "../state.js";
import {
  createContent as createServerContent,
  deleteContent as deleteServerContent,
  fetchContents,
  toggleContentPin as toggleServerContentPin,
  updateContent,
} from "../services/api/content.js";
import { getMockContent, saveMockContent } from "../services/mock/mockApi.js";
import { isServerMode } from "../services/mode.js";

function sortContent(left, right) {
  return Number(right.pinned) - Number(left.pinned) || String(right.publishedAt).localeCompare(String(left.publishedAt));
}

export const useContentStore = defineStore("content", {
  state: () => ({
    contents: getMockContent(),
    activeContentId: "",
    loaded: false,
  }),
  getters: {
    sortedContents: (state) => state.contents.slice().sort(sortContent),
    myContent() {
      return this.contents.filter((item) => item.ownerId === getActiveUserId()).sort(sortContent);
    },
    publishedContents: (state) => state.contents.filter((item) => item.status === "已发布").sort(sortContent),
    publicContentRecords: (state) => state.contents
      .flatMap((item) => item.status === "已发布" ? [item] : (item.publishedSnapshot ? [item.publishedSnapshot] : []))
      .sort(sortContent),
    pendingContents: (state) => state.contents.filter((item) => item.status === "待审核").sort(sortContent),
  },
  actions: {
    persist() {
      if (!isServerMode()) saveMockContent(this.contents);
    },
    async loadContents() {
      // 已加载过就直接复用(含 server 模式),避免每次导航全量重拉
      if (this.loaded) return;
      // server 模式默认分页只有 20 条,名片/问答详情需要全量(数据集 620 条,一次拉取)
      this.contents = isServerMode() ? await fetchContents({ page_size: 500 }) : getMockContent();
      this.loaded = true;
    },
    getContent(id) {
      return this.contents.find((item) => item.id === id);
    },
    canViewContent(item, userId = getActiveUserId(), isAdmin = false) {
      return Boolean(this.visibleContent(item, userId, isAdmin));
    },
    visibleContent(item, userId = getActiveUserId(), isAdmin = false) {
      if (!item) return null;
      if (item.status === "已发布" || item.ownerId === userId || isAdmin) return item;
      return item.publishedSnapshot || null;
    },
    contentByOwner(ownerId) {
      return this.publicContentRecords.filter((item) => item.ownerId === ownerId);
    },
    filteredMyContent(keyword) {
      const key = normalize(keyword);
      if (!key) return this.myContent;
      return this.myContent.filter((item) =>
        normalize(`${item.title} ${item.tags.join(" ")} ${item.summary} ${item.body}`).includes(key)
      );
    },
    isOwnContent(item) {
      return item?.ownerId === getActiveUserId();
    },
    async saveContent(payload, mode = "submit") {
      const editingId = payload.editingId || payload.id || "";
      const existing = this.getContent(editingId);
      const record = normalizeContentRecord({
        id: editingId || `c-${Date.now()}`,
        ownerId: getActiveUserId(),
        title: payload.title,
        tags: splitTags(payload.tagsText ?? payload.tags),
        summary: payload.summary,
        body: payload.body,
        publishedAt: existing?.publishedAt || getTodayText(),
        pinned: existing?.pinned || false,
        weeklyQueryCount: existing?.weeklyQueryCount || payload.weeklyQueryCount || 12,
        weeklyRecommendCount: existing?.weeklyRecommendCount || payload.weeklyRecommendCount || 8,
        status: mode === "draft" ? "草稿" : "待审核",
        submittedAt: mode === "draft" ? existing?.submittedAt || "" : getTodayText(),
        updatedAt: getTodayText(),
        version: (existing?.version || 0) + 1,
        auditTrail: existing?.auditTrail || [],
        publishedSnapshot: existing?.status === "已发布" ? { ...existing, publishedSnapshot: null } : existing?.publishedSnapshot || null,
      });
      if (isServerMode()) {
        const saved = editingId ? await updateContent(editingId, record) : await createServerContent(record);
        const normalized = normalizeContentRecord(saved || record);
        if (editingId) this.contents = this.contents.map((item) => (item.id === editingId ? normalized : item));
        else this.contents.unshift(normalized);
        this.activeContentId = normalized.id;
        return normalized;
      }
      if (editingId) this.contents = this.contents.map((item) => (item.id === editingId ? record : item));
      else this.contents.unshift(record);
      this.activeContentId = record.id;
      this.persist();
      return record;
    },
    async auditContent(id, approved, reviewerName, reason = "") {
      const item = this.getContent(id);
      if (!item || item.status !== "待审核") return false;
      const status = approved ? "已发布" : "已驳回";
      const auditRecord = {
        version: item.version,
        status,
        reviewer: reviewerName,
        auditedAt: getTodayText(),
        reason: approved ? "" : reason,
      };
      const updated = normalizeContentRecord({
        ...item,
        status,
        publishedAt: approved ? getTodayText() : item.publishedAt,
        auditTrail: [...(item.auditTrail || []), auditRecord],
      });
      if (isServerMode()) await updateContent(id, updated);
      this.contents = this.contents.map((record) => (record.id === id ? updated : record));
      this.persist();
      return true;
    },
    async deleteContent(id) {
      const item = this.getContent(id);
      if (!this.isOwnContent(item)) return false;
      if (isServerMode()) await deleteServerContent(id);
      this.contents = this.contents.filter((record) => record.id !== id);
      if (this.activeContentId === id) this.activeContentId = "";
      this.persist();
      return true;
    },
    async toggleContentPin(id) {
      const item = this.getContent(id);
      if (!this.isOwnContent(item) || item.status !== "已发布") return false;
      if (isServerMode()) await toggleServerContentPin(id, { pinned: !item.pinned });
      item.pinned = !item.pinned;
      this.persist();
      return true;
    },
  },
});
