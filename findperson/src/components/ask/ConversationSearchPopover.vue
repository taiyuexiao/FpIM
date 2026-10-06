<template>
  <div v-if="visible" class="history-search-popover">
    <div class="history-search-panel">
      <div class="history-search-input-wrap">
        <el-icon><Search /></el-icon>
        <el-input :model-value="search" clearable @update:model-value="$emit('update:search', $event)" />
        <button class="history-search-close" type="button" @click="$emit('close')">Esc</button>
      </div>
      <div class="history-search-results">
        <button
          v-for="session in sessions"
          :key="session.id"
          class="history-search-item"
          :class="{ active: session.id === activeSessionId }"
          type="button"
          @click="$emit('select', session.id)"
        >
          <strong>{{ session.title || '新对话' }}</strong>
          <span>{{ session.turnCount ? `${session.turnCount} 轮对话` : '空白对话' }}</span>
        </button>
        <div v-if="!sessions.length" class="empty-state compact">没有找到匹配的历史对话。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Search } from "@element-plus/icons-vue";

defineProps({
  visible: Boolean,
  search: { type: String, default: "" },
  sessions: { type: Array, required: true },
  activeSessionId: { type: String, default: "" },
});
defineEmits(["update:search", "close", "select"]);
</script>
