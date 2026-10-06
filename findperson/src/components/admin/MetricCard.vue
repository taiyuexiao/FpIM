<template>
  <div class="metric-card" :class="{ 'primary-metric': primary }">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  primary: Boolean,
});
</script>
