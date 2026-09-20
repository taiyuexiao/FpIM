<template>
  <div ref="scroller" class="fpim-msg-scroll" @scroll="onScroll">
    <div v-if="store.hasMore[store.activeId]" class="fpim-msg-sep" style="cursor: pointer" @click="store.loadMore(store.activeId)">
      {{ store.loadingMessages ? "加载中…" : "查看更早的消息" }}
    </div>

    <template v-for="(msg, i) in messages" :key="msg.id || msg.clientMsgId">
      <div v-if="needTimeDivider(messages[i - 1], msg)" class="fpim-msg-sep">
        {{ fullTime(msg.createdAt) }}
      </div>

      <!-- 系统消息：居中灰底，不占气泡 -->
      <div v-if="isSystem(msg)" class="fpim-sys"><span>{{ msg.content.text }}</span></div>

      <div v-else class="fpim-msg" :class="{ mine: isMine(msg), 'is-pending': msg.pending }">
        <div class="fpim-avatar sm" :style="{ background: avatarColor(msg.senderId) }">
          {{ avatarText(nameOf(msg.senderId)) }}
        </div>

        <div class="fpim-msg-body">
          <div class="fpim-msg-meta">
            <span>{{ isMine(msg) ? "我" : nameOf(msg.senderId) }}</span>
            <span>{{ shortTime(msg.createdAt) }}</span>
            <span v-if="msg.pending">· 发送中</span>
          </div>

          <!-- 问题卡：会话里承载闭环的核心消息类型 -->
          <div v-if="msg.msgType === 'issue_card'" class="fpim-issuecard">
            <h4>{{ msg.content.summary || msg.content.question }}</h4>
            <div class="meta">
              <span v-if="msg.content.assigneeName">责任人：{{ msg.content.assigneeName }}</span>
              <span v-if="msg.content.askerName">提问人：{{ msg.content.askerName }}</span>
              <span>状态：{{ issueStatusMeta(msg.content.status).label }}</span>
            </div>
            <div v-if="!isMine(msg) && msg.content.status !== 'resolved'" class="actions">
              <button class="fpim-btn prim" @click="$emit('resolve', msg)">标记已解决</button>
              <button class="fpim-btn" @click="$emit('focus-issue', msg.issueId)">查看过程</button>
            </div>
          </div>

          <!-- 图片 -->
          <a
            v-else-if="msg.msgType === 'image'"
            :href="fileUrl(msg)" target="_blank" rel="noopener"
          >
            <img class="fpim-img" :src="fileUrl(msg)" :alt="msg.content.name || '图片'" />
          </a>

          <!-- 文件 -->
          <a
            v-else-if="msg.msgType === 'file'"
            class="fpim-attach" :href="fileUrl(msg)" target="_blank" rel="noopener"
          >
            <span class="ext">{{ fileExt(msg.content.name) }}</span>
            <span>
              <span class="nm">{{ msg.content.name }}</span>
              <span class="sz">{{ msg.content.sizeHuman || humanSize(msg.content.size) }}</span>
            </span>
          </a>

          <!-- 文本（含撤回态） -->
          <div v-else-if="msg.revoked" class="fpim-bubble" style="color: var(--im-text-3); font-style: italic">
            消息已撤回
          </div>
          <div v-else class="fpim-bubble">{{ msg.content.text }}</div>
        </div>
      </div>
    </template>

    <div v-if="!messages.length" class="fpim-empty">
      还没有消息。说点什么，或者把问题写清楚发过去。
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";

import {
  avatarColor, avatarText, fileExt, fullTime, humanSize, issueStatusMeta,
  needTimeDivider, shortTime,
} from "../../services/im/format.js";
import { useAuthStore } from "../../stores/auth.js";
import { useImStore } from "../../stores/im.js";

defineEmits(["resolve", "focus-issue"]);

const store = useImStore();
const auth = useAuthStore();
const scroller = ref(null);

const messages = computed(() => store.activeMessages);

const SYSTEM_TYPES = new Set(["system", "resolve_confirm", "report_card"]);
// 系统消息：后端用 sender_id="system" 发送（sender_id 列 NOT NULL，不能真空）
const isSystem = (msg) => SYSTEM_TYPES.has(msg.msgType) && (!msg.senderId || msg.senderId === "system");

function isMine(msg) {
  return msg.senderId === auth.userId || msg.senderId === "me";
}

/** 从会话成员里查姓名；查不到就回落 id，不编造 */
function nameOf(userId) {
  const conv = store.active;
  const hit = conv?.members?.find((m) => m.id === userId);
  if (hit?.name) return hit.name;
  if (conv?.peer?.id === userId && conv.peer.name) return conv.peer.name;
  return userId;
}

function fileUrl(msg) {
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return `${base}${msg.content.url}`;
}

/** 新消息或切换会话后滚到底部 */
async function scrollToBottom() {
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

watch(() => store.activeId, () => scrollToBottom());
watch(() => messages.value.length, (n, o) => {
  // 只在贴近底部时自动滚动，避免用户翻历史时被拽走
  const el = scroller.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 220;
  if (nearBottom || n > o) scrollToBottom();
});
watch(() => messages.value[messages.value.length - 1]?.seq, scrollToBottom);

/** 滚动到顶自动加载更早的消息 */
let loadingMore = false;
async function onScroll() {
  const el = scroller.value;
  if (!el || loadingMore) return;
  if (el.scrollTop > 60 || !store.hasMore[store.activeId]) return;
  loadingMore = true;
  const before = el.scrollHeight;
  try {
    await store.loadMore(store.activeId);
    await nextTick();
    el.scrollTop = el.scrollHeight - before;   // 维持视觉位置不跳动
  } finally {
    loadingMore = false;
  }
}
</script>
