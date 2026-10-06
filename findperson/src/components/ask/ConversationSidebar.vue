<template>
  <aside class="conversation-sidebar">
    <div class="panel-header">
      <div><h2>历史对话</h2></div>
      <div class="history-actions">
        <el-button class="secondary-button small-button icon-button" @click="$emit('toggle-search')">
          <el-icon><Search /></el-icon>
        </el-button>
        <el-button class="secondary-button small-button" @click="$emit('new-chat')">新对话</el-button>
      </div>
    </div>

    <ConversationSearchPopover
      :visible="isSearchOpen"
      :search="search"
      :sessions="searchedSessions"
      :active-session-id="activeSessionId"
      @update:search="$emit('update:search', $event)"
      @close="$emit('close-search')"
      @select="$emit('select', $event)"
    />
    <ConversationHistoryList :sessions="sessions" :active-session-id="activeSessionId" @select="$emit('select', $event)" @command="(...args) => $emit('command', ...args)" />
  </aside>
</template>

<script setup>
import { Search } from "@element-plus/icons-vue";
import ConversationHistoryList from "./ConversationHistoryList.vue";
import ConversationSearchPopover from "./ConversationSearchPopover.vue";

defineProps({
  sessions: { type: Array, required: true },
  searchedSessions: { type: Array, required: true },
  activeSessionId: { type: String, default: "" },
  search: { type: String, default: "" },
  isSearchOpen: Boolean,
});
defineEmits(["toggle-search", "close-search", "update:search", "new-chat", "select", "command"]);
</script>
