<template>
  <aside v-if="visible" class="detail-sidebar">
    <DetailPanel v-bind="$attrs" />
  </aside>
</template>

<script setup>
import DetailPanel from "../DetailPanel.vue";

defineProps({ visible: Boolean });
</script>
