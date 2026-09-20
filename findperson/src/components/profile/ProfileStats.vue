<template>
  <!-- 数据画像：个人主页 / 个人中心共用（PRD F2）。数据来自 /people/{id}/profile-stats -->
  <section class="profile-block profile-stats-block">
    <div class="stats-head">
      <h2>数据画像</h2>
      <span v-if="stats" class="stats-period">{{ stats.period.label }}</span>
    </div>

    <p v-if="loading" class="empty-state">统计加载中…</p>
    <p v-else-if="!stats" class="empty-state">暂无统计数据。</p>

    <div v-else class="stats-grid">
      <div class="stat-item">
        <div class="stat-value">{{ stats.askedCount }}</div>
        <div class="stat-label">被问次数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.resolvedCount }}</div>
        <div class="stat-label">解决数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">
          {{ stats.helpRank ? `#${stats.helpRank}` : "—" }}
          <span v-if="stats.helpRank" class="stat-sub">/ {{ stats.helpRankTotal }}</span>
        </div>
        <div class="stat-label">帮助榜排名</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.faqCount }}</div>
        <div class="stat-label">知识沉淀</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">
          {{ stats.avgFirstResponseHours != null ? stats.avgFirstResponseHours : "—" }}
          <span v-if="stats.avgFirstResponseHours != null" class="stat-sub">小时</span>
        </div>
        <div class="stat-label">平均首响</div>
      </div>
    </div>

    <p v-if="stats" class="stats-footnote">
      近 30 天：被问 {{ stats.last30d.askedCount }} · 解决 {{ stats.last30d.resolvedCount }}
      <template v-if="stats.resolveRate != null"> · 累计解决率 {{ Math.round(stats.resolveRate * 100) }}%</template>
    </p>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { fetchProfileStats } from "../../services/api/people.js";

const props = defineProps({
  personId: { type: String, required: true },
});

const stats = ref(null);
const loading = ref(false);

async function load() {
  if (!props.personId) return;
  loading.value = true;
  try {
    stats.value = await fetchProfileStats(props.personId);
  } catch {
    stats.value = null; // 失败不阻塞页面，画像区显示空态
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.personId, load);
</script>

<style scoped>
.profile-stats-block { margin: 14px 0; }
.stats-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.stats-head h2 { margin: 0; }
.stats-period { font-size: 12px; color: var(--text-secondary, #909399); }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-top: 10px;
}
.stat-item {
  text-align: center;
  padding: 10px 6px;
  border: 0.5px solid var(--border-color, #eef2f7);
  border-radius: 8px;
  background: #fafbfc;
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  font-variant-numeric: tabular-nums;
}
.stat-sub { font-size: 12px; font-weight: 400; color: #909399; }
.stat-label { margin-top: 4px; font-size: 12px; color: #909399; }
.stats-footnote {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-secondary, #909399);
}
@media (max-width: 720px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>
