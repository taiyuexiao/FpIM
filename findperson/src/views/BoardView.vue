<template>
  <div class="fpim board-page">
    <header class="board-head">
      <h3>看板</h3>
      <span class="fpim-main-sub">只公开正向榜与知识缺口——不公示个人拖延明细</span>
    </header>

    <div class="board-grid">
      <!-- 帮助榜 -->
      <section class="board-col">
        <div class="board-col-head">
          <h4>帮助榜</h4>
          <span class="fpim-main-sub">按「解决数」排名 · 累计</span>
        </div>
        <p v-if="loading" class="fpim-empty">加载中…</p>
        <p v-else-if="!leaderboard.length" class="fpim-empty">还没有数据。立项并解决几个问题后就有了。</p>
        <div v-else class="lb-list">
          <div
            v-for="row in leaderboard"
            :key="row.personId"
            class="lb-row"
            :class="{ top: row.rank <= 3 }"
            @click="openProfile(row.personId)"
          >
            <span class="lb-rank">{{ row.rank }}</span>
            <div class="fpim-avatar sm" :style="{ background: avatarColor(row.personId) }">
              {{ avatarText(row.name) }}
            </div>
            <div class="lb-main">
              <div class="lb-name">{{ row.name }}</div>
              <div class="lb-dept">{{ row.department || "—" }}</div>
            </div>
            <div class="lb-nums">
              <span class="lb-resolved">{{ row.resolvedCount }} 解决</span>
              <span class="lb-asked">被问 {{ row.askedCount }}</span>
              <span v-if="row.avgFirstResponseHours != null" class="lb-resp">
                首响 {{ row.avgFirstResponseHours }}h
              </span>
              <span v-if="row.avgRating != null" class="lb-resp">
                ★ {{ row.avgRating }}（{{ row.ratingCount }}）
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- 知识缺口地图 -->
      <section class="board-col">
        <div class="board-col-head">
          <h4>知识缺口地图</h4>
          <span class="fpim-main-sub">未结问题按部门聚合</span>
        </div>
        <p v-if="loading" class="fpim-empty">加载中…</p>
        <p v-else-if="!gaps.length" class="fpim-empty">当前没有未结问题。</p>
        <div v-else class="gap-list">
          <div v-for="g in gaps" :key="g.department" class="gap-row">
            <div class="gap-head">
              <span class="gap-dept">{{ g.department }}</span>
              <span class="gap-count">
                {{ g.openCount }} 个未结
                <em v-if="g.untouchedCount" class="gap-untouched">{{ g.untouchedCount }} 未联系</em>
              </span>
            </div>
            <p v-if="g.latestOpen" class="gap-latest">最新：{{ g.latestOpen.summary }}</p>
          </div>
        </div>
      </section>
    </div>

    <!-- 一期：领导点名的数据分析与统计（科室维度；不做排名，见 stats-board.md 红线） -->
    <section class="board-stats">
      <div class="board-col-head">
        <h4>分析统计 · 科室维度</h4>
        <span class="fpim-main-sub">被问量高说明缺知识、缺流程，不是这里的人不行</span>
      </div>
      <p v-if="loading" class="fpim-empty">加载中…</p>
      <p v-else-if="!deptStats.length" class="fpim-empty">还没有数据。</p>
      <table v-else class="stats-table">
        <thead>
          <tr>
            <th>科室</th>
            <th>被问次数</th>
            <th>解决件数</th>
            <th>解决率</th>
            <th>回复时长（中位数）</th>
            <th>回复时长（均值）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in deptStats" :key="row.department">
            <td class="stats-dept">{{ row.department }}</td>
            <td>{{ row.askedCount }}</td>
            <td>{{ row.resolvedCount }}</td>
            <td>{{ row.resolveRate != null ? (row.resolveRate * 100).toFixed(1) + "%" : "—" }}</td>
            <td>{{ row.medianFirstResponseHours != null ? row.medianFirstResponseHours + "h" : "—" }}</td>
            <td>{{ row.avgFirstResponseHours != null ? row.avgFirstResponseHours + "h" : "—" }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { fetchDepartmentStats, fetchGapMap, fetchLeaderboard } from "../services/api/issues.js";
import { avatarColor, avatarText } from "../services/im/format.js";

const router = useRouter();
const loading = ref(false);
const leaderboard = ref([]);
const gaps = ref([]);
const deptStats = ref([]);

function openProfile(personId) {
  router.push({ name: "profile", params: { id: personId } });
}

onMounted(async () => {
  loading.value = true;
  try {
    const [lb, gm, ds] = await Promise.all([
      fetchLeaderboard(20), fetchGapMap(), fetchDepartmentStats(),
    ]);
    leaderboard.value = lb.items || [];
    gaps.value = gm.items || [];
    deptStats.value = ds.items || [];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
/* 根节点带 .fpim（借用设计 token）但需纵向文档流，覆盖其 flex 布局 */
.board-page { display: block; max-width: 1080px; margin: 0 auto; padding: 20px 24px; height: 100%; overflow-y: auto; }
.board-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.board-head h3 { margin: 0; font-size: 17px; }
.board-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
.board-col {
  background: #fff; border: 0.5px solid var(--im-line-strong, #dee0e3);
  border-radius: 10px; padding: 14px 16px;
}
.board-col-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.board-col-head h4 { margin: 0; font-size: 14px; }
.lb-list { display: flex; flex-direction: column; }
.lb-row {
  display: flex; align-items: center; gap: 10px; padding: 9px 6px;
  border-bottom: 0.5px solid var(--im-line, #f0f0f0); cursor: pointer;
}
.lb-row:last-child { border-bottom: none; }
.lb-row:hover { background: var(--im-hover, rgba(0,0,0,0.03)); }
.lb-rank {
  width: 24px; text-align: center; font-weight: 700; font-size: 13px;
  color: var(--im-text-3, #8f959e); font-variant-numeric: tabular-nums;
}
.lb-row.top .lb-rank { color: #f7b500; }
.lb-main { flex: 1; min-width: 0; }
.lb-name { font-size: 13px; font-weight: 600; color: var(--im-text-1, #1f2329); }
.lb-dept { font-size: 12px; color: var(--im-text-3, #8f959e); }
.lb-nums { display: flex; gap: 10px; font-size: 12px; color: var(--im-text-2, #646a73); }
.lb-resolved { color: #1f9d55; font-weight: 600; }
.lb-resp { color: var(--im-text-3, #8f959e); }
.gap-list { display: flex; flex-direction: column; gap: 10px; }
.gap-row { padding: 10px 12px; border: 0.5px solid var(--im-line, #f0f0f0); border-radius: 8px; }
.gap-head { display: flex; align-items: center; justify-content: space-between; }
.gap-dept { font-size: 13px; font-weight: 600; color: var(--im-text-1, #1f2329); }
.gap-count { font-size: 12px; color: var(--im-text-2, #646a73); }
.gap-untouched {
  font-style: normal; margin-left: 6px; padding: 1px 7px; border-radius: 8px;
  background: #fdf0f0; color: #d64545; font-size: 11px;
}
.gap-latest { margin: 6px 0 0; font-size: 12px; color: var(--im-text-3, #8f959e);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.board-stats {
  margin-top: 16px; background: #fff; border: 0.5px solid var(--im-line-strong, #dee0e3);
  border-radius: 10px; padding: 14px 16px;
}
.stats-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.stats-table th {
  text-align: left; font-weight: 500; color: var(--im-text-3, #8f959e);
  padding: 8px 10px; border-bottom: 0.5px solid var(--im-line-strong, #dee0e3);
}
.stats-table td {
  padding: 9px 10px; color: var(--im-text-2, #646a73);
  border-bottom: 0.5px solid var(--im-line, #f0f0f0);
  font-variant-numeric: tabular-nums;
}
.stats-table tr:last-child td { border-bottom: none; }
.stats-dept { color: var(--im-text-1, #1f2329); font-weight: 500; }
@media (max-width: 900px) { .board-grid { grid-template-columns: 1fr; } }
</style>
