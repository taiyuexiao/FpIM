<!-- 反馈按钮：有帮助 / 没帮助，切换选中状态 -->
<template>
  <span class="feedback-group">
    <button
      :class="['feedback-button', feedback?.[targetKey] === 'up' ? 'active' : '']"
      type="button"
      @click="$emit('toggle', targetKey, 'up')"
    >
      有帮助
    </button>
    <button
      :class="['feedback-button', feedback?.[targetKey] === 'down' ? 'active' : '']"
      type="button"
      @click="$emit('toggle', targetKey, 'down')"
    >
      没帮助
    </button>
  </span>
</template>

<script setup>
defineProps({
  /** 反馈记录的键名，如 "answer:turn-123" 或 "person:turn-123:p-chen" */
  targetKey: String,
  /** 全局反馈数据对象，用于判断选中状态 */
  feedback: Object,
});
defineEmits(['toggle']);
</script>
