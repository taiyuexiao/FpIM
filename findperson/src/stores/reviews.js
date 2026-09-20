import { defineStore } from "pinia";
import {
  getActiveUserId,
  getTodayText,
} from "../state.js";
import {
  approveReview,
  createReview as createServerReview,
  deleteReview as deleteServerReview,
  fetchPendingReviews,
  fetchPersonReviewHistory,
  fetchSentReviews,
  ignoreReview,
} from "../services/api/reviews.js";
import { getMockReviews, saveMockReviews } from "../services/mock/mockApi.js";
import { isServerMode } from "../services/mode.js";
import { useAuthStore } from "./auth.js";

export const useReviewsStore = defineStore("reviews", {
  state: () => ({
    reviews: getMockReviews(),
    loaded: false,
    pendingTags: [],  // 我收到的待放行他人标签(信任分级通知)
  }),
  getters: {
    sentReviews() {
      const auth = useAuthStore();
      return this.reviews.filter((item) => item.reviewer === auth.displayName && !item.id.endsWith("-seed"));
    },
    receivedReviews() {
      return this.reviewsForPerson(getActiveUserId());
    },
  },
  actions: {
    persist() {
      if (!isServerMode()) saveMockReviews(this.reviews);
    },
    async loadReviews() {
      // 已加载过就直接复用(含 server 模式),避免每次导航重拉
      if (this.loaded) return;
      this.reviews = isServerMode() ? await fetchSentReviews() : getMockReviews();
      this.loaded = true;
    },
    async loadPendingTags() {
      if (!isServerMode()) { this.pendingTags = []; return; }
      this.pendingTags = await fetchPendingReviews();
    },
    /** 拉取某人收到的全部评价并合入本地列表(他画像数据源:谁看谁都能看到,不再只是"我发出的") */
    async loadPersonReviews(personId) {
      if (!isServerMode() || !personId) return;
      const result = await fetchPersonReviewHistory(personId);
      const items = (Array.isArray(result) ? result : (result?.items || [])).map((r) => ({
        id: r.id, personId: r.personId, reviewer: r.reviewer, tag: r.tag, date: r.date,
        status: r.status || "approved",  // 信任分级:待放行标签也要在他画像展示(标注)
      }));
      // 该人的记录整体替换为服务端最新,其他人的不动
      this.reviews = [...this.reviews.filter((r) => r.personId !== personId), ...items];
    },
    async approveTag(reviewId) {
      await approveReview(reviewId);
      this.pendingTags = this.pendingTags.filter((item) => item.id !== reviewId);
      // 放行后本人负责领域已变化,刷新名录缓存
      const { useDirectoryStore } = await import("./directory.js");
      const directory = useDirectoryStore();
      directory.loaded = false;
      await directory.loadPeople();
    },
    async ignoreTag(reviewId) {
      await ignoreReview(reviewId);
      this.pendingTags = this.pendingTags.filter((item) => item.id !== reviewId);
    },
    reviewsForPerson(personId) {
      return this.reviews
        .filter((item) => item.personId === personId)
        .sort((left, right) => String(right.date).localeCompare(String(left.date)));
    },
    tagFor(review) {
      return String(review.tag || review.text || "").trim();
    },
    tagsForPerson(personId) {
      const tags = new Map();
      this.reviewsForPerson(personId).forEach((review) => {
        const tag = this.tagFor(review);
        if (!tag) return;
        const entry = tags.get(tag) || { tag, reviewers: new Set(), latestDate: review.date };
        entry.reviewers.add(review.reviewer);
        if (String(review.date) > String(entry.latestDate)) entry.latestDate = review.date;
        tags.set(tag, entry);
      });
      return [...tags.values()]
        .map((entry) => ({ tag: entry.tag, count: entry.reviewers.size, latestDate: entry.latestDate }))
        .sort((left, right) => right.count - left.count || String(right.latestDate).localeCompare(String(left.latestDate)));
    },
    async saveReview(payload) {
      if (payload.personId === getActiveUserId()) return { ok: false, message: "不能为自己补充他画像" };
      const tag = String(payload.tag || payload.text || "").trim();
      if (!tag) return { ok: false, message: "请选择或填写事项" };
      if (tag.length > 20) return { ok: false, message: "事项不能超过 20 个字符" };
      if (!payload.date) return { ok: false, message: "请选择日期" };
      const auth = useAuthStore();
      const existing = this.reviews.find((item) =>
        item.personId === payload.personId &&
        item.reviewer === auth.displayName &&
        this.tagFor(item) === tag
      );
      const record = {
        id: payload.id || existing?.id || `review-${Date.now()}`,
        personId: payload.personId,
        reviewer: auth.displayName,
        date: payload.date,
        tag,
      };
      const saved = isServerMode() ? await createServerReview(record) : record;
      this.reviews = [saved || record, ...this.reviews.filter((item) => item.id !== record.id)];
      this.persist();
      return { ok: true, record };
    },
    async deleteReview(reviewId) {
      if (isServerMode()) await deleteServerReview(reviewId);
      this.reviews = this.reviews.filter((item) => item.id !== reviewId);
      if (reviewId.endsWith("-seed")) {
        const deleted = JSON.parse(localStorage.getItem("firstResponsibilityDemo.deletedPeerReviews") || "[]");
        localStorage.setItem("firstResponsibilityDemo.deletedPeerReviews", JSON.stringify(Array.from(new Set(deleted.concat(reviewId)))));
      } else {
        this.persist();
      }
    },
  },
});
