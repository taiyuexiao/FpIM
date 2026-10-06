<template>
  <article class="person-card clickable-card" @click="$emit('open', person.id)">
    <div class="person-head">
      <div>
        <p class="person-name">{{ person.name }}</p>
        <p class="person-meta">{{ departmentText }}</p>
        <p class="person-meta">{{ person.role }}</p>
      </div>
    </div>
    <div class="field-row">
      <span v-for="tag in person.domains" :key="tag" class="tag">{{ tag }}</span>
    </div>
    <p>{{ person.selfPortrait }}</p>
    <p class="person-meta">联系方式：{{ person.contact || person.phone || "未填写" }}</p>
  </article>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ person: { type: Object, required: true } });
defineEmits(["open"]);
const departmentText = computed(() => props.person.departmentPath?.join(" / ") || props.person.department);
</script>
