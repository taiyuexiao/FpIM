<template>
  <div class="governance-list">
    <article v-for="(item, index) in items" :key="item.person.id" class="rank-item">
      <span class="rank-no">{{ index + 1 }}</span>
      <div>
        <strong>{{ item.person.name }}</strong>
        <p class="person-meta">{{ item.person.department }} · {{ item.person.role }}</p>
      </div>
      <span class="score-pill">本周推荐 {{ item.value }}</span>
    </article>
  </div>
</template>

<script setup>
defineProps({ items: { type: Array, required: true } });
</script>
