<template>
  <div class="admin-section-head"><div><h2>内容审核</h2><p>仅审核通过的内容会展示在公开主页并参与推荐。</p></div></div>
  <el-tabs v-model="tab" class="audit-tabs"><el-tab-pane :label="`待审核 (${content.pendingContents.length})`" name="pending"><AuditList :items="content.pendingContents" :can-audit="true" @audit="audit" /></el-tab-pane><el-tab-pane :label="`已发布 (${content.publishedContents.length})`" name="published"><AuditList :items="content.publishedContents" /></el-tab-pane><el-tab-pane label="已驳回" name="rejected"><AuditList :items="rejected" /></el-tab-pane></el-tabs>
  <el-dialog v-model="showReject" title="驳回内容" width="460px"><el-input v-model="reason" type="textarea" :rows="4" placeholder="请填写驳回原因" /><template #footer><el-button @click="showReject = false">取消</el-button><el-button type="danger" @click="confirmReject">确认驳回</el-button></template></el-dialog>
</template>
<script setup>
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAuthStore } from "../../stores/auth.js";
import { useContentStore } from "../../stores/content.js";
import AuditList from "./AuditList.vue";
const content = useContentStore(); const auth = useAuthStore(); const tab = ref("pending"); const showReject = ref(false); const reason = ref(""); const targetId = ref(""); const rejected = computed(() => content.contents.filter((item) => item.status === "已驳回"));
async function audit({ id, approved }) { if (!approved) { targetId.value = id; reason.value = ""; showReject.value = true; return; } try { await ElMessageBox.confirm("审核通过后内容将公开展示并参与推荐，确认通过？", "审核内容", { type: "warning" }); await content.auditContent(id, true, auth.displayName); ElMessage.success("内容已发布"); } catch { return; } }
async function confirmReject() { if (!reason.value.trim()) return ElMessage.warning("请填写驳回原因"); await content.auditContent(targetId.value, false, auth.displayName, reason.value.trim()); showReject.value = false; ElMessage.success("内容已驳回"); }
</script>
