<template>
  <div class="empty-state" :class="{ compact }">
    <slot>{{ text }}</slot>
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, default: "暂无数据。" },
  compact: Boolean,
});
</script>
