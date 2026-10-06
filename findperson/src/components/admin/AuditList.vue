<template><div v-if="items.length" class="audit-list"><article v-for="item in items" :key="item.id" class="audit-item" @click="openDetail(item)"><div><div class="content-section-head"><h3>{{ item.title }}</h3><span class="status-chip" :class="statusClass(item.status)">{{ item.status }}</span></div><p class="person-meta">提交日期：{{ item.submittedAt }} · 第 {{ item.version }} 版</p><p>{{ item.summary }}</p><div class="field-row"><span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span></div><p v-if="latestAudit(item)" class="audit-note">{{ latestAudit(item) }}</p></div><div v-if="canAudit" class="audit-actions" @click.stop><el-button type="primary" @click="$emit('audit', { id: item.id, approved: true })">通过</el-button><el-button @click="$emit('audit', { id: item.id, approved: false })">驳回</el-button></div></article></div><div v-else class="empty-state">暂无内容。</div></template>
<script setup>
import { useRoute, useRouter } from "vue-router";
defineProps({ items: { type: Array, default: () => [] }, canAudit: Boolean }); defineEmits(["audit"]);
const router = useRouter(); const route = useRoute();
function openDetail(item) { router.push({ name: "contentDetail", params: { id: item.id }, query: { redirect: `${route.path}?tab=audit` } }); }
function statusClass(status) { return status === "已发布" ? "status-published" : status === "待审核" ? "status-pending" : "status-rejected"; }
function latestAudit(item) { const audit = item.auditTrail?.at(-1); return audit?.reason ? `驳回原因：${audit.reason}` : audit ? `审核人：${audit.reviewer} · ${audit.auditedAt}` : ""; }
</script>
