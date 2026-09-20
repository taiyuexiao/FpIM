<template>
  <div class="activity-panel trend-panel">
    <div class="activity-summary">
      <strong>{{ total }} {{ unit }}</strong>
      <span class="soft-count">近 7 天</span>
    </div>
    <div class="activity-chart">
      <div v-for="item in items" :key="item.day" class="activity-bar activity-bar-wide">
        <strong>{{ item.value }}</strong>
        <span :style="{ height: `${item.percent}%` }"></span>
        <em>{{ item.day }}</em>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, required: true },
  total: { type: Number, required: true },
  unit: { type: String, default: "次访问" },
});
</script>
