<template>
  <div class="answer-feedback-bar">
    <FeedbackButtons :target-key="targetKey" :feedback="feedback.feedbackMap" @toggle="handleToggle" />
    <el-dialog v-model="showReasons" title="请告诉我们没帮助的原因" width="420px" append-to-body>
      <el-radio-group v-model="reason" class="reason-group">
        <el-radio v-for="item in reasons" :key="item.code" :value="item.label" class="reason-option">{{ item.label }}</el-radio>
      </el-radio-group>
      <el-input
        v-if="reason === '其他'"
        v-model="otherText"
        type="textarea"
        :rows="3"
        placeholder="补充说明(可选)"
        class="reason-other-input"
      />
      <template #footer>
        <el-button @click="showReasons = false">取消</el-button>
        <el-button type="primary" :disabled="!reason" @click="submitDown">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import http from "../../services/api/http.js";
import FeedbackButtons from "../FeedbackButtons.vue";
import { useFeedbackStore } from "../../stores/feedback.js";

// 点踩原因配置(实施方案v3 §3.2;经 backend 代理到 agent-service /agent/feedback/reasons)
const DEFAULT_REASONS = [
  { code: "wrong_person", label: "推荐人选不对" },
  { code: "stale_info", label: "职责/联系方式已过期" },
  { code: "missing_scope", label: "没有覆盖我问的范围" },
  { code: "incomplete", label: "回答不完整" },
  { code: "other", label: "其他" },
];

const props = defineProps({
  message: { type: Object, required: true },   // 助手消息(id/traceId)
  question: { type: String, default: "" },      // 本轮用户问题
  candidates: { type: Array, default: () => [] }, // 推荐人选姓名列表
  sessionId: { type: String, default: "" },
});

const feedback = useFeedbackStore();
const targetKey = computed(() => `answer:${props.message.id}`);
const showReasons = ref(false);
const reason = ref("");
const otherText = ref("");
const reasons = ref(DEFAULT_REASONS);
let reasonsLoaded = false;

async function ensureReasons() {
  if (reasonsLoaded) return;
  reasonsLoaded = true;
  try {
    const data = await http.get("/agui/feedback/reasons");
    if (Array.isArray(data?.reasons) && data.reasons.length) reasons.value = data.reasons;
  } catch {
    // 拉取失败用内置默认配置
  }
}

function buildMeta(extra = {}) {
  return {
    targetType: "answer",
    sessionId: props.sessionId,
    messageId: props.message.id,
    traceId: props.message.traceId || "",
    question: props.question,
    candidates: props.candidates,
    ...extra,
  };
}

function handleToggle(key, value) {
  if (value === "down" && feedback.feedbackMap[targetKey.value] !== "down") {
    // 新点踩:先弹原因选择(v4 §四/实施方案v3 §3.2)
    reason.value = "";
    otherText.value = "";
    showReasons.value = true;
    ensureReasons();
    return;
  }
  feedback.toggle(targetKey.value, value, buildMeta());
}

function submitDown() {
  if (!reason.value) return;
  const text = reason.value === "其他" && otherText.value.trim()
    ? `其他:${otherText.value.trim()}`
    : reason.value;
  feedback.toggle(targetKey.value, "down", buildMeta({ reason: text }));
  showReasons.value = false;
}
</script>
