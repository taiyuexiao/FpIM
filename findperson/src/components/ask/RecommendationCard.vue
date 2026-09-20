<template>
  <article class="result-card thread-card result-inline is-clickable" tabindex="0"
           title="单击查看详情，双击进入主页"
           @click="onClick" @dblclick="onDblClick" @keydown.enter="onClick">
    <div class="person-head">
      <div>
        <p class="person-name">{{ person.name }}</p>
        <p class="person-meta">{{ departmentText }}</p>
        <p class="person-meta">{{ person.role }}</p>
        <p class="person-meta" v-if="supervisorText">上级：{{ supervisorText }}</p>
        <p class="person-meta">联系方式：{{ person.contact || person.phone || '-' }}</p>
      </div>
    </div>
    <div class="field-row" v-if="person.domains?.length">
      <span v-for="tag in person.domains" :key="tag" class="tag">{{ tag }}</span>
    </div>
    <p class="person-meta person-portrait" v-if="person.selfPortrait">{{ person.selfPortrait }}</p>
  </article>
</template>

<script setup>
import { computed } from "vue";
import { useDirectoryStore } from "../../stores/directory.js";

const props = defineProps({
  card: { type: Object, required: true },
});

// 名片字段以名录 store 中的完整人员数据为准(含上级/负责领域/自我介绍),服务端卡片只做索引
const directory = useDirectoryStore();
const person = computed(() => directory.getPerson(props.card.personId) || props.card.person || {});
const departmentText = computed(() => person.value.departmentPath?.join(" / ") || person.value.department || "");
const supervisorText = computed(() => {
  const supervisor = directory.getPersonSupervisor(props.card.personId);
  return supervisor?.person?.name || "";
});

const emit = defineEmits(["profile", "detail"]);

// 单击=右侧详情侧栏,双击=进主页;250ms 窗口区分单击/双击,避免双击时侧栏先闪
let clickTimer = null;
function onClick() {
  if (clickTimer) return;
  clickTimer = setTimeout(() => {
    clickTimer = null;
    emit("detail", props.card.personId);
  }, 250);
}
function onDblClick() {
  if (clickTimer) {
    clearTimeout(clickTimer);
    clickTimer = null;
  }
  emit("profile", props.card.personId);
}
</script>
