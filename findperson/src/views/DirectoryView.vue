<template>
  <section class="view active">
    <div class="page-heading"><div><h1>名片库</h1></div></div>
    <div class="toolbar">
      <div class="search-field">
        <el-icon><Search /></el-icon>
        <el-input v-model="directory.keyword" placeholder="搜索关键词、人员、职责" clearable />
      </div>
      <el-popover placement="bottom-end" :width="360" trigger="click" popper-class="directory-filter-popper">
        <template #reference><el-button class="secondary-button filter-trigger" circle aria-label="打开部门筛选" title="部门筛选"><el-icon><Filter /></el-icon></el-button></template>
        <section class="directory-filter-panel">
          <div class="directory-filter-head"><div><strong>部门筛选</strong><p>点击部门查看该部门及下级成员</p></div></div>
          <button class="filter-all-node" :class="{ active: !directory.selectedDepartmentId }" type="button" @click="resetFilters">全部部门</button>
          <el-tree ref="deptTreeRef" :data="directory.departmentTree" node-key="id" :props="treeProps" :current-node-key="directory.selectedDepartmentId" highlight-current expand-on-click-node @node-click="selectDepartment" />
          <div class="directory-filter-footer"><el-tooltip content="重置筛选" placement="top"><el-button class="filter-reset-button" circle aria-label="重置筛选" @click="resetFilters"><el-icon><RefreshRight /></el-icon></el-button></el-tooltip></div>
        </section>
      </el-popover>
    </div>
    <div class="card-grid">
      <PersonCard v-for="person in directory.filteredPeople" :key="person.id" :person="person" @open="openProfile" />
      <div v-if="!directory.filteredPeople.length" class="empty-state">没有匹配到人员名片。</div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { Filter, RefreshRight, Search } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";
import PersonCard from "../components/directory/PersonCard.vue";
import { useDirectoryStore } from "../stores/directory.js";

const router = useRouter();
const route = useRoute();
const directory = useDirectoryStore();
const treeProps = { label: "name", children: "children" };

function openProfile(id) {
  router.push({ name: "profile", params: { id }, query: { redirect: route.fullPath } });
}

function selectDepartment(department) {
  directory.setDepartmentFilterFromNode(department);
}

const deptTreeRef = ref(null);

function resetFilters() {
  directory.keyword = "";
  directory.resetDepartmentFilters();
  // current-node-key 非响应式,需手动清掉树内的持续高亮
  deptTreeRef.value?.setCurrentKey(null);
}
</script>
