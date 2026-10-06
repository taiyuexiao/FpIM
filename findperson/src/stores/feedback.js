import { defineStore } from "pinia";
import { loadJson, saveJson, STORAGE_KEYS } from "../state.js";
import { reportInteractionEvent } from "../services/agui/reporter.js";
import { useAuthStore } from "./auth.js";

export const useFeedbackStore = defineStore("feedback", {
  state: () => ({
    feedbackMap: loadJson(STORAGE_KEYS.feedback, {}),
  }),
  actions: {
    persist() {
      saveJson(STORAGE_KEYS.feedback, this.feedbackMap);
    },
    toggle(targetKey, value, meta = {}) {
      this.feedbackMap[targetKey] = this.feedbackMap[targetKey] === value ? "" : value;
      this.persist();
      // 服务端 record_vote 语义:重复同值=取消/异值=改值,所以始终上报本次点击的值(up/down)
      reportInteractionEvent({
        eventType: "feedback_toggle",
        targetType: meta.targetType || "answer",
        targetId: meta.messageId || targetKey,
        value,
        reason: meta.reason || "",
        traceId: meta.traceId || "",
        sessionId: meta.sessionId || "",
        messageId: meta.messageId || "",
        // 验收:反馈连同用户问题与推荐人选一起入库,供后台可视化与推荐优化
        context: { question: meta.question || "", candidates: meta.candidates || [], userId: useAuthStore().userId },
      });
    },
  },
});
