<template>
  <section class="view active">
    <div class="page-heading admin-heading"><div><h1>后台管理</h1></div></div>
    <el-tabs v-model="activeTab" class="admin-tabs">
      <el-tab-pane label="数据看板" name="dashboard">
        <div class="admin-grid">
          <MetricCard label="参与人员数量" :value="admin.metrics.peopleCount" primary />
          <MetricCard label="已发布内容" :value="content.publishedContents.length" />
          <MetricCard label="待审核内容" :value="content.pendingContents.length" />
          <MetricCard label="本周推荐量" :value="admin.metrics.weeklyRecommendationTotal" />
        </div>
        <div class="admin-layout">
          <div><div class="module-title"><div><h2>本周推荐热度排行</h2></div></div><RankingList :items="admin.ranking" /></div>
          <div><div class="module-title"><div><h2>周日活数</h2></div><div class="week-switcher"><button v-if="admin.activeWeek === 0" class="week-arrow" type="button" @click="admin.activeWeek = 1">‹</button><span class="week-label">{{ admin.activeWeek ? '上周' : '本周' }}</span><button v-if="admin.activeWeek === 1" class="week-arrow" type="button" @click="admin.activeWeek = 0">›</button></div></div><ActivityTrend :items="admin.trend" :total="admin.trendTotal" /></div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="成员管理" name="members">
        <div class="admin-section-head"><div><h2>成员</h2><p>维护成员所属部门、职务、负责人关系和系统角色。</p></div><el-button class="primary-button" type="primary" @click="addMember">新增成员</el-button></div>
        <div class="admin-table-wrap"><el-table :data="directory.people" stripe><el-table-column prop="name" label="成员" min-width="100" /><el-table-column label="部门" min-width="220"><template #default="{ row }">{{ row.departmentPath?.join(' / ') || row.department }}</template></el-table-column><el-table-column prop="role" label="职务" min-width="100" /><el-table-column label="负责人" min-width="100"><template #default="{ row }">{{ directory.isDepartmentLeader(row.id, row.department) ? '是' : '-' }}</template></el-table-column><el-table-column prop="systemRole" label="系统角色" min-width="100" /><el-table-column label="状态" min-width="80"><template #default="{ row }"><span class="status-chip" :class="row.active ? 'status-published' : 'status-rejected'">{{ row.active ? '启用' : '停用' }}</span></template></el-table-column><el-table-column label="操作" width="88" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="editMember(row)">编辑</el-button></template></el-table-column></el-table></div>
      </el-tab-pane>

      <el-tab-pane label="内容审核" name="audit"><ContentAudit /></el-tab-pane>

      <!-- 知识沉淀模块:按要求暂时隐藏(恢复时取消注释) -->
      <!--
      <el-tab-pane label="知识沉淀" name="knowledge">
        <KnowledgePanel v-if="activeTab === 'knowledge'" />
      </el-tab-pane>
      -->

      <!-- 反馈分析仅对师沛琳(P0004)开放,其他管理员不显示该模块 -->
      <el-tab-pane v-if="canViewFeedback" label="反馈分析" name="feedback">
        <!-- v-if 保证每次切入该页签都重新挂载拉数,反馈数据实时刷新 -->
        <FeedbackPanel v-if="activeTab === 'feedback'" />
      </el-tab-pane>

      <el-tab-pane label="Agent可观测" name="observability">
        <!-- v-if 保证每次切入该页签都重新挂载拉数,观测数据实时反映最新链路 -->
        <AgentObservability v-if="activeTab === 'observability'" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showMemberDialog" title="维护成员" width="520px">
      <el-form v-if="memberForm" label-position="top">
        <el-form-item label="姓名"><el-input v-model="memberForm.name" /></el-form-item>
        <el-form-item label="部门"><div class="department-picker"><el-select v-model="memberForm.department" filterable class="full-width"><el-option v-for="department in directory.departments" :key="department.id" :label="department.path.join(' / ')" :value="department.name" /></el-select><el-button @click="openDepartmentDialog">新增部门</el-button></div></el-form-item>
        <el-form-item label="职务"><el-select v-model="memberForm.role" filterable allow-create default-first-option class="full-width"><el-option v-for="role in directory.roles" :key="role" :label="role" :value="role" /></el-select></el-form-item>
        <el-form-item><el-checkbox v-model="memberForm.isLeader">设为所选部门负责人</el-checkbox></el-form-item>
        <el-form-item label="系统角色"><el-radio-group v-model="memberForm.systemRole"><el-radio value="普通成员">普通成员</el-radio><el-radio value="管理员">管理员</el-radio></el-radio-group></el-form-item>
        <el-form-item label="账号状态"><el-switch v-model="memberForm.active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showMemberDialog = false">取消</el-button><el-button type="primary" @click="saveMember">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="showDepartmentDialog" title="新增部门" width="520px">
      <el-form label-position="top"><el-form-item label="上级部门"><el-select v-model="departmentForm.parentId" clearable class="full-width" placeholder="不选则新增顶级部门"><el-option v-for="department in directory.departments" :key="department.id" :label="department.path.join(' / ')" :value="department.id" /></el-select></el-form-item><el-form-item label="部门名称"><el-input v-model="departmentForm.name" placeholder="请输入部门名称" /></el-form-item><el-form-item label="部门职责"><el-input v-model="departmentForm.responsibility" type="textarea" :rows="4" /></el-form-item></el-form>
      <template #footer><el-button @click="showDepartmentDialog = false">取消</el-button><el-button type="primary" @click="saveDepartment">新增并选用</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute } from "vue-router";
import { useAdminStore } from "../stores/admin.js";
import { useAuthStore } from "../stores/auth.js";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import ActivityTrend from "../components/admin/ActivityTrend.vue";
import AgentObservability from "../components/admin/AgentObservability.vue";
import ContentAudit from "../components/admin/ContentAudit.vue";
import FeedbackPanel from "../components/admin/FeedbackPanel.vue";
// import KnowledgePanel from "../components/admin/KnowledgePanel.vue";  // 知识沉淀模块暂时隐藏
import MetricCard from "../components/admin/MetricCard.vue";
import RankingList from "../components/admin/RankingList.vue";

const admin = useAdminStore(); const content = useContentStore(); const directory = useDirectoryStore();
const auth = useAuthStore();
const route = useRoute();
/** 反馈分析模块仅师沛琳(P0004)可见 */
const canViewFeedback = computed(() => auth.userId === "P0004");
const activeTab = ref(route.query.tab === "audit" ? "audit" : "dashboard"); const showMemberDialog = ref(false); const showDepartmentDialog = ref(false); const memberForm = ref(null);
const departmentForm = reactive({ name: "", parentId: "", responsibility: "" });
onMounted(() => { admin.loadAdminData(); directory.loadPeople(); }); watch(() => admin.activeWeek, () => admin.loadAdminData());
function editMember(person) { memberForm.value = { ...person, isLeader: directory.isDepartmentLeader(person.id, person.department) }; showMemberDialog.value = true; }
function addMember() { memberForm.value = { id: "", name: "", department: directory.departments[0]?.name || "", role: "专员", systemRole: "普通成员", active: true, isLeader: false }; showMemberDialog.value = true; }
function openDepartmentDialog() { Object.assign(departmentForm, { name: "", parentId: "", responsibility: "" }); showDepartmentDialog.value = true; }
async function saveDepartment() {
  if (!departmentForm.name.trim()) return ElMessage.warning("请输入部门名称");
  try {
    const department = await directory.addDepartment(departmentForm);
    if (!department) return ElMessage.warning("同级部门名称不能重复");
    memberForm.value.department = department.name;
    showDepartmentDialog.value = false;
  } catch (error) {
    ElMessage.error(error.message || "部门创建失败");
  }
}
async function saveMember() {
  if (!memberForm.value.name?.trim()) return ElMessage.warning("请输入成员姓名");
  if (!memberForm.value.department) return ElMessage.warning("请选择所属部门");
  if (!memberForm.value.role?.trim()) return ElMessage.warning("请选择或填写职务");
  const { id, isLeader, ...patch } = memberForm.value;
  const existing = id ? directory.getPerson(id) : null;
  const oldDepartment = existing?.department;
  const wasLeader = existing && directory.isDepartmentLeader(existing.id, oldDepartment);
  try {
    const person = await directory.savePerson(id, patch);
    if (!person) return;
    directory.addRole(patch.role);
    if (wasLeader && (!isLeader || oldDepartment !== patch.department)) await directory.assignDepartmentLeader(directory.getDepartment(oldDepartment)?.id, "");
    if (isLeader) await directory.assignDepartmentLeader(directory.getDepartment(patch.department)?.id, person.id);
    showMemberDialog.value = false;
    ElMessage.success(id ? "成员信息已更新" : "成员已新增");
  } catch (error) {
    ElMessage.error(error.message || "成员保存失败");
  }
}
</script>
