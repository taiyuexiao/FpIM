<template>
  <aside class="fpim-list">
    <div class="fpim-list-head">
      <span class="fpim-list-title">消息</span>
      <button class="fpim-iconbtn" title="发起新会话" @click="$emit('compose')">＋</button>
    </div>

    <div class="fpim-list-search">
      <input v-model="keyword" type="text" placeholder="搜索会话或联系人" />
    </div>

    <div class="fpim-list-scroll">
      <div v-if="!filtered.length" class="fpim-empty">
        {{ keyword ? "没有匹配的会话" : "还没有会话，从名片库发起一个" }}
      </div>

      <div
        v-for="conv in filtered"
        :key="conv.id"
        class="fpim-conv"
        :class="{ 'is-active': conv.id === store.activeId }"
        @click="store.selectConversation(conv.id)"
      >
        <div
          class="fpim-avatar"
          :style="{ background: avatarColor(conv.peer?.id || conv.title) }"
        >{{ avatarText(displayName(conv)) }}</div>

        <div class="fpim-conv-main">
          <div class="fpim-conv-row1">
            <span class="fpim-conv-name">{{ displayName(conv) }}</span>
            <span class="fpim-conv-time">{{ shortTime(conv.lastMessageAt) }}</span>
          </div>
          <div class="fpim-conv-row2">
            <span class="fpim-conv-preview">{{ previewOf(conv.lastMessage) }}</span>
            <!-- 状态标签必须带文字：只靠颜色会被读成"系统在给我亮红牌" -->
            <span v-if="statusMeta(conv)" class="fpim-chip" :class="statusMeta(conv).cls">
              {{ statusMeta(conv).label }}
            </span>
            <span v-if="conv.unreadCount" class="fpim-badge">{{ conv.unreadCount > 99 ? '99+' : conv.unreadCount }}</span>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";

import { avatarColor, avatarText, issueStatusMeta, previewOf, shortTime } from "../../services/im/format.js";
import { useImStore } from "../../stores/im.js";

defineEmits(["compose"]);

const store = useImStore();
const keyword = ref("");

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return store.conversations;
  return store.conversations.filter((c) =>
    `${displayName(c)} ${c.lastMessage?.content?.text || ""}`.toLowerCase().includes(kw));
});

function displayName(conv) {
  return conv.title || conv.peer?.name || "会话";
}

/** 会话的第二行状态标签：仅当会话挂着一个"还在进行"的问题时才显示 */
function statusMeta(conv) {
  if (!conv.issueId) return null;
  const issue = store.issues.find((i) => i.id === conv.issueId);
  if (!issue) return null;
  return issueStatusMeta(issue.status);
}
</script>
