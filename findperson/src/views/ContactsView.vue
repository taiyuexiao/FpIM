<template>
  <!-- 通讯录（一期）：飞书式「部门树 + 人员列表」，取代消息页「+」里藏联系人的反直觉入口 -->
  <div class="fpim contacts">
    <aside class="fpim-list contacts-aside">
      <div class="fpim-list-head">
        <span class="fpim-list-title">通讯录</span>
      </div>
      <div class="fpim-list-search">
        <input v-model="directory.keyword" type="text" placeholder="搜索姓名 / 拼音 / 部门" />
      </div>
      <div class="fpim-list-scroll contacts-tree-wrap">
        <button
          class="contacts-node"
          :class="{ active: !directory.selectedDepartmentId }"
          type="button"
          @click="resetDepartment"
        >
          全部部门
        </button>
        <el-tree
          ref="treeRef"
          :data="directory.departmentTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="directory.selectedDepartmentId"
          highlight-current
          expand-on-click-node
          @node-click="selectDepartment"
        />
      </div>
    </aside>

    <section class="fpim-main contacts-main">
      <header class="fpim-main-head">
        <div>
          <div class="fpim-main-title">{{ currentDepartmentName }}</div>
          <div class="fpim-main-sub">共 {{ people.length }} 人 · 免加好友，点「发消息」直达会话</div>
        </div>
      </header>

      <div class="contacts-list">
        <div v-if="!people.length" class="fpim-empty">没有匹配的人员</div>
        <div v-for="p in people" :key="p.id" class="contacts-row">
          <div class="fpim-avatar" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
          <div class="contacts-main-cell">
            <div class="contacts-name-row">
              <button class="contacts-name" type="button" @click="openProfile(p.id)">{{ p.name }}</button>
              <span class="contacts-role">{{ p.role || "" }}</span>
            </div>
            <div class="contacts-meta">
              <span>{{ directory.departmentText(p) }}</span>
              <span v-if="supervisorOf(p)">· 直属上级：
                <button class="contacts-link" type="button" @click="openProfile(supervisorOf(p).id)">
                  {{ supervisorOf(p).name }}
                </button>
              </span>
            </div>
          </div>
          <button class="fpim-btn prim" @click="startChat(p.id)">发消息</button>
          <button class="fpim-btn ghost" @click="openProfile(p.id)">个人主页</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { avatarColor, avatarText } from "../services/im/format.js";
import { useAuthStore } from "../stores/auth.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useImStore } from "../stores/im.js";

const router = useRouter();
const directory = useDirectoryStore();
const im = useImStore();
const auth = useAuthStore();
const treeRef = ref(null);

// 搜索时忽略部门过滤，直接全量匹配（与名片库一致：keyword 命中姓名/部门/职责）
const people = computed(() =>
  directory.filteredPeople.filter((p) => p.id !== auth.userId && p.active !== false));

const currentDepartmentName = computed(() => {
  const dept = directory.getDepartment(directory.selectedDepartmentId);
  return dept?.name || "全部人员";
});

function supervisorOf(person) {
  return directory.getPersonSupervisor(person.id)?.person || null;
}

function selectDepartment(department) {
  directory.setDepartmentFilterFromNode(department);
}

function resetDepartment() {
  directory.resetDepartmentFilters();
  treeRef.value?.setCurrentKey(null);
}

async function startChat(personId) {
  try {
    await im.openWith(personId);
    router.push({ name: "im-chat" });
  } catch (err) {
    ElMessage.error(err.message || "发起会话失败");
  }
}

function openProfile(personId) {
  router.push({ name: "profile", params: { id: personId } });
}
</script>

<style scoped>
.contacts-aside {
  width: 280px;
  flex: 0 0 280px;
}
.contacts-tree-wrap {
  padding: 4px 12px 12px;
}
.contacts-tree-wrap :deep(.el-tree) {
  background: transparent;
  --el-tree-node-hover-bg-color: var(--im-hover);
}
.contacts-node {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  padding: 7px 10px;
  margin-bottom: 2px;
  border-radius: var(--im-radius);
  font-size: 13px;
  font-family: inherit;
  color: var(--im-text-1);
  cursor: pointer;
}
.contacts-node:hover {
  background: var(--im-hover);
}
.contacts-node.active {
  background: var(--im-primary-weak);
  color: var(--im-primary);
  font-weight: 500;
}

.contacts-main-head {
  padding: 16px 20px 10px;
  border-bottom: 0.5px solid var(--im-line);
}
.contacts-list {
  flex: 1;
  overflow-y: auto;
}
.contacts-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  border-bottom: 0.5px solid var(--im-line);
}
.contacts-row:hover {
  background: var(--im-hover);
}
.contacts-main-cell {
  flex: 1;
  min-width: 0;
}
.contacts-name-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.contacts-name {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  color: var(--im-text-1);
  cursor: pointer;
}
.contacts-name:hover {
  color: var(--im-primary);
}
.contacts-role {
  font-size: 12px;
  color: var(--im-text-3);
}
.contacts-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--im-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contacts-link {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  color: var(--im-primary);
  cursor: pointer;
}
</style>
