<template>
  <section class="profile-block profile-header-block">
    <div class="profile-name-row">
      <h2>{{ person.name }}</h2>
      <div class="profile-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="profile-info-chain">
      <span class="chain-item">{{ departmentText }}</span>
      <span class="chain-dot"></span>
      <span class="chain-item">{{ person.role }}</span>
      <button v-if="supervisor" class="supervisor-tag" type="button" @click="$emit('supervisor', supervisor.person.id)">上级：{{ supervisorText }}</button>
      <span v-else class="supervisor-tag">上级：{{ supervisorText }}</span>
    </div>
    <p class="person-meta">联系方式：{{ person.contact || person.phone || "未填写" }}</p>
    <div class="field-row">
      <span v-for="tag in person.domains" :key="tag" class="tag">{{ tag }}</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ person: { type: Object, required: true }, supervisor: { type: Object, default: null } });
defineEmits(["supervisor"]);
const departmentText = computed(() => props.person.departmentPath?.join(" / ") || props.person.department);
const supervisorText = computed(() => props.supervisor
  ? `${props.supervisor.department.name} · ${props.supervisor.person.name}`
  : "暂未设置"
);
</script>
