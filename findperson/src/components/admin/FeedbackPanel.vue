<template>
  <div class="feedback-panel">
    <!-- 指标卡:有帮助率 / 有帮助 / 没帮助 / 总反馈 -->
    <div class="admin-grid">
      <MetricCard label="有帮助率" :value="summary ? `${summary.helpfulRate}%` : '-'" primary />
      <MetricCard label="有帮助" :value="summary?.up ?? '-'" />
      <MetricCard label="没帮助" :value="summary?.down ?? '-'" />
      <MetricCard label="总反馈数" :value="summary?.total ?? '-'" />
    </div>

    <div class="admin-layout">
      <!-- 近 7 天赞/踩趋势 -->
      <div>
        <div class="module-title"><div><h2>近 7 天反馈趋势</h2></div></div>
        <div class="activity-panel trend-panel">
          <div class="activity-chart">
            <div v-for="item in trend" :key="item.day" class="activity-bar activity-bar-wide">
              <strong>{{ item.up + item.down }}</strong>
              <span :style="{ height: `${item.percent}%` }"></span>
              <em>{{ item.day }}</em>
            </div>
          </div>
          <div class="trend-legend">
            <span><i class="legend-dot legend-up" />有帮助 {{ totalUp }}</span>
            <span><i class="legend-dot legend-down" />没帮助 {{ totalDown }}</span>
          </div>
        </div>
      </div>

      <!-- 点踩原因分布 -->
      <div>
        <div class="module-title"><div><h2>点踩原因分布（近 7 天）</h2></div></div>
        <div class="activity-panel">
          <div v-if="!reasons.length" class="empty-state compact">近 7 天没有点踩反馈。</div>
          <div v-for="r in reasons" :key="r.reason" class="reason-row">
            <span class="reason-label">{{ r.reason }}</span>
            <div class="reason-bar-wrap">
              <div class="reason-bar" :style="{ width: `${r.percent}%` }"></div>
            </div>
            <span class="reason-count">{{ r.count }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近反馈明细 -->
    <div class="module-title"><div><h2>最近反馈明细</h2></div></div>
    <div class="admin-table-wrap">
      <el-table :data="recent" stripe>
        <el-table-column prop="createdAt" label="时间" min-width="140" />
        <el-table-column prop="user" label="反馈人" min-width="80" />
        <el-table-column prop="question" label="用户问题" min-width="180" show-overflow-tooltip />
        <el-table-column label="反馈" width="80">
          <template #default="{ row }">
            <span class="status-chip" :class="row.value === 'up' ? 'status-published' : 'status-rejected'">
              {{ row.value === 'up' ? '有帮助' : '没帮助' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="130" show-overflow-tooltip />
        <el-table-column label="该轮候选人" min-width="160">
          <template #default="{ row }">{{ candidateNames(row.candidates) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import MetricCard from "./MetricCard.vue";
import { fetchFeedbackRecent, fetchFeedbackSummary } from "../../services/api/admin.js";
import { useDirectoryStore } from "../../stores/directory.js";

const directory = useDirectoryStore();
const summary = ref(null);
const recent = ref([]);

const trend = computed(() => {
  const items = summary.value?.trend || [];
  const max = Math.max(1, ...items.map((i) => i.up + i.down));
  return items.map((i) => ({ ...i, percent: Math.round(((i.up + i.down) / max) * 100) }));
});
const totalUp = computed(() => trend.value.reduce((t, i) => t + i.up, 0));
const totalDown = computed(() => trend.value.reduce((t, i) => t + i.down, 0));
const reasons = computed(() => {
  const list = summary.value?.reasons || [];
  const max = Math.max(1, ...list.map((r) => r.count));
  return list.map((r) => ({ ...r, percent: Math.round((r.count / max) * 100) }));
});

function candidateNames(ids) {
  return (ids || []).map((id) => directory.getPerson(id)?.name || id).join("、");
}

onMounted(async () => {
  try {
    const [s, r] = await Promise.all([fetchFeedbackSummary(), fetchFeedbackRecent({ limit: 50 })]);
    summary.value = s;
    recent.value = r;
  } catch {
    // 接口异常保持空态,不阻断后台其他页签
  }
});
</script>

<style scoped>
.feedback-panel { display: grid; gap: 18px; }
.trend-legend { display: flex; gap: 18px; margin-top: 10px; font-size: 13px; color: var(--muted); }
.legend-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
.legend-up { background: #22a06b; }
.legend-down { background: #e5484d; }
.reason-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
.reason-label { width: 150px; flex-shrink: 0; font-size: 13px; }
.reason-bar-wrap { flex: 1; height: 8px; background: #eef2f7; border-radius: 4px; overflow: hidden; }
.reason-bar { height: 100%; background: #e5484d; border-radius: 4px; opacity: 0.75; }
.reason-count { width: 32px; text-align: right; font-weight: 700; font-size: 13px; }
</style>
