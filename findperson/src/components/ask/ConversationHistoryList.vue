<template>
  <div class="conversation-history">
    <article v-for="session in sessions" :key="session.id" class="history-card" :class="{ active: session.id === activeSessionId }">
      <button class="history-card-main" type="button" @click="$emit('select', session.id)">
        <strong>{{ session.title || '新对话' }}</strong>
        <span>{{ session.turnCount ? `${session.turnCount} 轮对话` : '空白对话' }}</span>
      </button>
      <div class="history-card-actions">
        <el-dropdown trigger="click" @command="$emit('command', $event, session.id)">
          <button class="history-more-button" type="button" aria-label="更多操作">…</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="rename">重命名</el-dropdown-item>
              <el-dropdown-item command="delete">删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </article>
  </div>
</template>

<script setup>
defineProps({
  sessions: { type: Array, required: true },
  activeSessionId: { type: String, default: "" },
});
defineEmits(["select", "command"]);
</script>
