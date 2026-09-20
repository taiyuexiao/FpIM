<!-- 知识沉淀(管理端):待确认候选 + 问题闭环总览 -->
<template>
  <div class="knowledge-panel">
    <!-- ── 待确认候选:人工确认后才写入知识库 ── -->
    <div class="admin-section-head">
      <div>
        <h2>知识沉淀候选</h2>
        <p>问答被标记「已解决」后自动进入候选池。确认后成为知识库标准答案，问答时可直接命中。</p>
      </div>
      <el-button class="secondary-button small-button" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <p v-if="loading" class="empty-state">加载中…</p>
    <template v-else>
      <article v-for="item in candidates" :key="item.id" class="candidate-card">
        <div class="candidate-head">
          <h3>{{ item.question }}</h3>
          <span class="candidate-score">沉淀分 {{ item.score }}</span>
        </div>
        <p class="candidate-answer">{{ item.answer }}</p>
        <p class="candidate-meta">
          <span v-if="item.signals?.resolved">已被标记解决</span>
          <span v-if="item.signals?.related_global > 1">相近问题 {{ item.signals.related_global }} 条</span>
          <span v-if="item.sourceIssueIds?.length">来源问题 #{{ item.sourceIssueIds.join('、#') }}</span>
        </p>
        <div class="candidate-actions">
          <el-button class="primary-button small-button" type="primary" :loading="busyId === item.id" @click="approve(item, 'faq')">写成知识条目</el-button>
          <el-button class="secondary-button small-button" :loading="busyId === item.id" @click="approve(item, 'article')">转成文章草稿</el-button>
          <el-button class="secondary-button small-button" :loading="busyId === item.id" @click="reject(item)">忽略</el-button>
        </div>
      </article>
      <p v-if="!candidates.length" class="empty-state">暂无待确认候选。用户在「我的问题」里标记「已解决」后，这里会出现候选。</p>
    </template>

    <!-- ── 问题闭环总览 ── -->
    <div class="admin-section-head overview-head">
      <div>
        <h2>问题闭环总览</h2>
        <p>提问是否真的被解决——首问负责的落实情况。</p>
      </div>
    </div>
    <div v-if="overview" class="overview-grid">
      <MetricCard label="归档问题" :value="overview.total" primary />
      <MetricCard label="解决率" :value="`${Math.round((overview.resolutionRate || 0) * 100)}%`" />
      <MetricCard label="平均解决时长(h)" :value="overview.avgResolveHours" />
      <MetricCard label="待跟进" :value="(overview.counts?.not_contacted || 0) + (overview.counts?.processing || 0) + (overview.counts?.unresolved || 0)" />
    </div>
    <div v-if="overview?.byAssignee?.length" class="overview-table">
      <table>
        <thead><tr><th>责任人</th><th>问题数</th><th>已解决</th><th>解决率</th></tr></thead>
        <tbody>
          <tr v-for="row in overview.byAssignee" :key="row.personId">
            <td>{{ row.name }}</td>
            <td>{{ row.total }}</td>
            <td>{{ row.resolved }}</td>
            <td>{{ row.total ? Math.round((row.resolved / row.total) * 100) : 0 }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="overview && !overview.total" class="empty-state">还没有归档的问题。</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import MetricCard from "./MetricCard.vue";
import {
  approveCandidate,
  fetchIssuesOverview,
  fetchKnowledgeCandidates,
  rejectCandidate,
} from "../../services/api/issues.js";
import { isServerMode } from "../../services/mode.js";

const candidates = ref([]);
const overview = ref(null);
const loading = ref(false);
const busyId = ref(null);

async function loadAll() {
  if (!isServerMode()) return;
  loading.value = true;
  try {
    const [cands, ov] = await Promise.all([fetchKnowledgeCandidates(), fetchIssuesOverview()]);
    candidates.value = cands.items || [];
    overview.value = ov;
  } catch (error) {
    ElMessage.error(error?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function approve(item, mode) {
  busyId.value = item.id;
  try {
    const result = await approveCandidate(item.id, { mode });
    ElMessage.success(mode === "article"
      ? `已生成文章草稿（${result.contentId}），可在发布页继续编辑`
      : `已写入知识库（FAQ #${result.faqId}），问答可直接命中`);
    await loadAll();
  } catch (error) {
    ElMessage.error(error?.message || "操作失败");
  } finally {
    busyId.value = null;
  }
}

async function reject(item) {
  busyId.value = item.id;
  try {
    await rejectCandidate(item.id);
    ElMessage.success("已忽略该候选");
    await loadAll();
  } catch (error) {
    ElMessage.error(error?.message || "操作失败");
  } finally {
    busyId.value = null;
  }
}

onMounted(loadAll);
</script>

<style scoped>
.candidate-card {
  border: 1px solid var(--border-color, #eef2f7);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: #fff;
}
.candidate-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.candidate-head h3 { margin: 0; font-size: 15px; color: #303133; }
.candidate-score {
  flex: 0 0 auto; padding: 2px 10px; border-radius: 10px; background: #eef3ff;
  color: #4a7dff; font-size: 12px; line-height: 1.8;
}
.candidate-answer {
  margin: 8px 0; padding: 8px 10px; border-radius: 6px; background: #f7f9fc;
  color: #303133; font-size: 13px; line-height: 1.7; white-space: pre-wrap;
}
.candidate-meta { display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 10px; color: #909399; font-size: 12px; }
.candidate-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.overview-head { margin-top: 22px; }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.overview-table { margin-top: 14px; overflow-x: auto; }
.overview-table table { width: 100%; border-collapse: collapse; font-size: 13px; }
.overview-table th, .overview-table td { padding: 8px 10px; border-bottom: 1px solid #eef2f7; text-align: left; }
.overview-table th { color: #909399; font-weight: 500; }
</style>
