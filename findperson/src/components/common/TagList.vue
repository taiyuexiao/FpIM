<template>
  <div class="field-row">
    <span v-for="tag in tags" :key="tag" class="tag">{{ tag }}</span>
  </div>
</template>

<script setup>
defineProps({ tags: { type: Array, default: () => [] } });
</script>
