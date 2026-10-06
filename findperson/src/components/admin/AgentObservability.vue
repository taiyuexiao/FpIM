<template>
  <div class="obs-toolbar">
    <el-input v-model="keyword" placeholder="搜索问题 / 用户" clearable class="obs-search" @keyup.enter="!$event.isComposing && $event.keyCode !== 229 && load()" @clear="load" />
    <el-button class="secondary-button small-button" @click="load">刷新</el-button>
  </div>

  <div class="admin-table-wrap">
    <el-table :data="items" stripe v-loading="loading" @row-click="openDetail" class="obs-table">
      <el-table-column prop="createdAt" label="时间" width="160" />
      <el-table-column prop="user" label="用户" width="100" />
      <el-table-column prop="query" label="用户问题" min-width="220" show-overflow-tooltip />
      <el-table-column label="意图" width="150">
        <template #default="{ row }">
          <span class="tag">{{ row.intent || '-' }}</span>
          <span v-if="row.queryType" class="tag">{{ row.queryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="90">
        <template #default="{ row }">{{ (row.latencyMs / 1000).toFixed(1) }}s</template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <span class="status-chip" :class="row.degraded ? 'status-pending' : 'status-published'">{{ row.degraded ? '降级' : '正常' }}</span>
          <span v-if="row.gateDecision" class="tag">{{ gateLabel(row.gateDecision) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="80" fixed="right">
        <template #default><span class="obs-view-link">查看</span></template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page" :total="total" :page-size="20"
      layout="total, prev, pager, next" class="obs-pagination" @current-change="load" />
  </div>

  <el-dialog
    v-model="showDetail" class="obs-dialog" width="92%" top="4vh"
    :show-close="true" destroy-on-close>
    <template #header>
      <div class="obs-dialog-head">
        <span class="obs-dialog-title">{{ detail?.trace?.query || '链路详情' }}</span>
        <span v-if="detail" class="status-chip" :class="detail.trace.degraded ? 'status-pending' : 'status-published'">
          {{ detail.trace.degraded ? '降级' : '正常' }}
        </span>
      </div>
    </template>

    <div v-loading="detailLoading && !detail" class="obs-dialog-body">
      <template v-if="detail">
        <!-- 概览 -->
        <section class="obs-card">
          <div class="obs-overview">
            <div class="obs-ov-item"><label>时间</label><span>{{ detail.trace.createdAt }}</span></div>
            <div class="obs-ov-item"><label>用户</label><span>{{ detail.trace.user || '-' }}</span></div>
            <div class="obs-ov-item"><label>总耗时</label><span class="obs-ov-strong">{{ (detail.trace.latencyMs / 1000).toFixed(2) }}s</span></div>
            <div class="obs-ov-item"><label>意图</label><span>{{ detail.recommendation?.queryType || '-' }}</span></div>
            <div class="obs-ov-item"><label>门禁</label><span>{{ gateLabel(detail.recommendation?.gateDecision) || '-' }}</span></div>
            <div class="obs-ov-item"><label>排序策略</label><span>{{ detail.recommendation?.rankPolicy || '-' }}</span></div>
          </div>
          <div class="obs-traceid">
            <span class="obs-traceid-text">trace: {{ detail.trace.traceId }}</span>
            <button class="obs-copy-btn" @click="copyTraceId">复制</button>
          </div>
        </section>

        <!-- 节点链路 -->
        <section class="obs-card">
          <h3 class="obs-card-title">节点链路 <span class="obs-card-count">{{ detail.spans.length }}</span></h3>
          <div v-if="!detail.spans.length" class="obs-empty">无节点记录</div>
          <div v-for="(s, i) in detail.spans" :key="s.node + i" class="obs-span">
            <div class="obs-span-rail">
              <span class="obs-span-dot" :class="{ 'is-error': s.errorCode, 'is-degraded': s.degraded }">{{ i + 1 }}</span>
              <span v-if="i < detail.spans.length - 1" class="obs-span-line"></span>
            </div>
            <div class="obs-span-main">
              <div class="obs-span-head">
                <strong class="obs-span-name">{{ s.node }}</strong>
                <span class="obs-span-latency">{{ formatMs(s.latencyMs) }}</span>
                <span v-if="s.degraded" class="status-chip status-pending">降级</span>
                <span v-if="s.errorCode" class="status-chip status-rejected">{{ s.errorCode }}</span>
                <span v-if="s.llmTokens" class="obs-mini-tag">tokens {{ s.llmTokens }}</span>
                <button v-if="s.input || s.output" class="obs-io-toggle" @click="toggleIo(i)">
                  {{ expandedSpans.has(i) ? '收起' : '输入/输出' }}
                </button>
              </div>
              <div class="obs-span-bar">
                <div class="obs-span-bar-fill" :class="{ 'is-error': s.errorCode }" :style="{ width: latencyPercent(s.latencyMs) + '%' }"></div>
              </div>
              <div v-if="expandedSpans.has(i)" class="obs-span-io">
                <p v-if="s.input"><label>输入</label>{{ s.input }}</p>
                <p v-if="s.output"><label>输出</label>{{ s.output }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 概念链接 -->
        <section v-if="detail.conceptLink" class="obs-card">
          <h3 class="obs-card-title">概念链接</h3>
          <div v-for="t in detail.conceptLink.linkTrace" :key="t.term" class="obs-term">
            <div class="obs-term-head">
              <span class="obs-term-name">「{{ t.term }}」</span>
              <span v-if="!t.candidates.length" class="obs-empty-inline">无候选</span>
            </div>
            <div v-for="c in t.candidates.slice(0, 5)" :key="c.concept_id + c.candidate_source" class="obs-cand" :class="{ 'is-resolved': isResolved(c.concept_id) }">
              <span class="obs-cand-name">{{ c.canonical_name }}</span>
              <span class="obs-mini-tag">{{ c.candidate_source }}</span>
              <span class="obs-cand-score">{{ c.candidate_score }}</span>
              <span v-if="isResolved(c.concept_id)" class="obs-mini-tag is-resolved-tag">已确认</span>
            </div>
          </div>
          <div v-if="detail.conceptLink.resolvedConcepts?.length" class="obs-resolved">
            已确认概念:
            <span v-for="c in detail.conceptLink.resolvedConcepts" :key="c.concept_id" class="tag">{{ c.canonical_name }}</span>
          </div>
        </section>

        <!-- MCP 调用 -->
        <section v-if="detail.mcpCalls.length" class="obs-card">
          <h3 class="obs-card-title">MCP 调用 <span class="obs-card-count">{{ detail.mcpCalls.length }}</span></h3>
          <div v-for="(m, i) in detail.mcpCalls" :key="i" class="obs-mcp">
            <span class="obs-mcp-tool">{{ m.tool }}</span>
            <span class="status-chip" :class="m.ok ? 'status-published' : 'status-rejected'">{{ m.ok ? '成功' : '失败' }}</span>
            <span class="obs-span-latency">{{ formatMs(m.latencyMs) }}</span>
          </div>
        </section>

        <!-- 推荐候选 -->
        <section v-if="detail.recommendation?.candidates?.length" class="obs-card">
          <h3 class="obs-card-title">推荐候选 <span class="obs-card-count">{{ detail.recommendation.candidates.length }}</span></h3>
          <div v-for="(c, i) in detail.recommendation.candidates" :key="c.person_id" class="obs-person">
            <span class="obs-person-rank">{{ i + 1 }}</span>
            <div class="obs-person-main">
              <div class="obs-person-head">
                <strong>{{ c.person_id }}</strong>
                <span class="obs-person-score">score {{ c.score }}</span>
                <span v-if="c.has_formal" class="tag">正式责任</span>
                <span v-if="c.is_related_fallback" class="obs-mini-tag">相关兜底</span>
              </div>
              <div class="obs-person-ev">
                <span v-for="(e, j) in (c.evidences || []).slice(0, 6)" :key="j" class="obs-ev-tag">
                  {{ evidenceLabel(e.evidence_type) }}<template v-if="e.concept_id">@{{ shortId(e.concept_id) }}</template>
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 对话内容 -->
        <section class="obs-card">
          <h3 class="obs-card-title">对话内容</h3>
          <div v-if="!detail.messages.length" class="obs-empty">无消息记录</div>
          <div v-for="(m, i) in detail.messages" :key="i" class="obs-msg-row" :class="`is-${m.role}`">
            <div class="obs-msg-bubble">
              <span class="obs-msg-role">{{ m.role === 'user' ? '用户' : '助手' }}</span>
              <p class="obs-msg-text">{{ m.text }}</p>
              <p v-if="m.cards?.length" class="obs-msg-cards">名片 {{ m.cards.length }} 张</p>
            </div>
          </div>
        </section>

        <!-- 反馈 -->
        <section v-if="detail.feedbacks.length" class="obs-card">
          <h3 class="obs-card-title">反馈 <span class="obs-card-count">{{ detail.feedbacks.length }}</span></h3>
          <div v-for="(f, i) in detail.feedbacks" :key="i" class="obs-feedback">
            <span class="obs-mini-tag">{{ f.value }}</span>
            <span v-if="f.reason">{{ f.reason }}</span>
          </div>
        </section>
      </template>
    </div>
  </el-dialog>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchAgentTraceDetail, fetchAgentTraces } from "../../services/api/admin.js";

const GATE_LABELS = {
  answer: "直接作答",
  clarify: "需澄清",
  no_result: "无结果",
  degraded_answer: "降级作答",
};

const EVIDENCE_LABELS = {
  formal_assignment: "正式责任",
  explicit_self_tag: "自填标签",
  inferred_from_profile: "画像推断",
  inferred_from_review: "评价推断",
  inferred_from_article: "文章推断",
  directory_match: "名录匹配",
};

const items = ref([]);
const total = ref(0);
const page = ref(1);
const keyword = ref("");
const loading = ref(false);
const showDetail = ref(false);
const detail = ref(null);
const detailLoading = ref(false);
const maxLatency = ref(1);
const expandedSpans = ref(new Set());

async function load() {
  loading.value = true;
  try {
    const data = await fetchAgentTraces({ page: page.value, page_size: 20, keyword: keyword.value || undefined });
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  showDetail.value = true;
  detailLoading.value = true;
  detail.value = null;
  expandedSpans.value = new Set();
  try {
    detail.value = await fetchAgentTraceDetail(row.traceId);
    maxLatency.value = Math.max(...detail.value.spans.map((s) => s.latencyMs), 1);
  } catch {
    showDetail.value = false;
  } finally {
    detailLoading.value = false;
  }
}

function latencyPercent(ms) {
  return Math.max(2, Math.round((ms / maxLatency.value) * 100));
}

function formatMs(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

function gateLabel(v) {
  return GATE_LABELS[v] || v || "";
}

function evidenceLabel(v) {
  return EVIDENCE_LABELS[v] || v;
}

function shortId(id) {
  return String(id).length > 8 ? `${String(id).slice(0, 8)}…` : id;
}

function isResolved(conceptId) {
  return (detail.value?.conceptLink?.resolvedConcepts || []).some((c) => c.concept_id === conceptId);
}

function toggleIo(i) {
  const next = new Set(expandedSpans.value);
  if (next.has(i)) next.delete(i);
  else next.add(i);
  expandedSpans.value = next;
}

async function copyTraceId() {
  const text = detail.value?.trace?.traceId || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("traceId 已复制");
  } catch {
    ElMessage.warning("复制失败,请手动选择复制");
  }
}

onMounted(load);
</script>

<style scoped>
.obs-toolbar { display: flex; gap: 10px; margin-bottom: 12px; }
.obs-search { width: 240px; }
.obs-pagination { margin-top: 12px; justify-content: flex-end; }
.obs-table :deep(tbody tr) { cursor: pointer; }
.obs-view-link { color: var(--blue); font-size: 13px; }

.obs-dialog-head { display: flex; align-items: center; gap: 10px; padding-right: 24px; }
.obs-dialog-title { font-size: 15px; font-weight: 600; color: var(--ink-strong); word-break: break-all; }
.obs-dialog-body { min-height: 200px; }

.obs-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 14px 16px;
  margin-bottom: 14px;
}
.obs-card-title { font-size: 14px; margin: 0 0 10px; color: var(--ink-strong); display: flex; align-items: center; gap: 8px; }
.obs-card-count {
  font-size: 12px; font-weight: 400; color: var(--muted);
  background: var(--surface-tint); border-radius: 999px; padding: 1px 8px;
}
.obs-empty { color: var(--muted); font-size: 13px; }
.obs-empty-inline { color: var(--muted); font-size: 12px; }

/* 概览 */
.obs-overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px 16px; }
.obs-ov-item label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.obs-ov-item span { font-size: 13px; color: var(--ink); word-break: break-all; }
.obs-ov-strong { font-weight: 600; color: var(--ink-strong); }
.obs-traceid {
  margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--line);
  display: flex; align-items: center; gap: 10px;
}
.obs-traceid-text { font-size: 12px; color: var(--muted); font-family: ui-monospace, monospace; word-break: break-all; }
.obs-copy-btn {
  flex-shrink: 0; border: 1px solid var(--blue-line); background: var(--blue-soft);
  color: var(--blue-strong); border-radius: 6px; padding: 2px 10px; font-size: 12px; cursor: pointer;
}
.obs-copy-btn:hover { border-color: var(--blue); }

/* 节点链路(时间线 + 瀑布条) */
.obs-span { display: flex; gap: 12px; }
.obs-span-rail { display: flex; flex-direction: column; align-items: center; width: 24px; flex-shrink: 0; }
.obs-span-dot {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--blue-soft); color: var(--blue-strong);
  font-size: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.obs-span-dot.is-degraded { background: var(--warning-soft); color: var(--warning); }
.obs-span-dot.is-error { background: var(--danger-soft); color: var(--danger); }
.obs-span-line { width: 2px; flex: 1; background: var(--line); margin: 2px 0; }
.obs-span-main { flex: 1; min-width: 0; padding-bottom: 14px; }
.obs-span-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.obs-span-name { font-size: 13px; color: var(--ink-strong); }
.obs-span-latency { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.obs-span-bar { height: 6px; background: var(--surface-tint); border-radius: 4px; margin-top: 6px; overflow: hidden; }
.obs-span-bar-fill { height: 100%; background: var(--blue); border-radius: 4px; }
.obs-span-bar-fill.is-error { background: var(--danger); }
.obs-io-toggle {
  margin-left: auto; border: none; background: none; color: var(--blue);
  font-size: 12px; cursor: pointer; padding: 0;
}
.obs-io-toggle:hover { text-decoration: underline; }
.obs-span-io {
  margin-top: 8px; background: var(--surface-soft); border-radius: 6px; padding: 8px 10px;
}
.obs-span-io p { margin: 0 0 6px; font-size: 12px; color: var(--ink); word-break: break-all; white-space: pre-wrap; }
.obs-span-io p:last-child { margin-bottom: 0; }
.obs-span-io label { display: block; color: var(--muted); font-size: 11px; margin-bottom: 2px; }

/* 通用小标签 */
.obs-mini-tag {
  font-size: 11px; color: var(--muted); background: var(--surface-tint);
  border-radius: 4px; padding: 1px 6px; white-space: nowrap;
}
.obs-mini-tag.is-resolved-tag { background: var(--success-soft); color: var(--success); }

/* 概念链接 */
.obs-term { padding: 8px 0; border-bottom: 1px dashed var(--line); }
.obs-term:last-of-type { border-bottom: none; }
.obs-term-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.obs-term-name { font-size: 13px; font-weight: 600; color: var(--ink-strong); }
.obs-cand { display: flex; align-items: center; gap: 8px; padding: 3px 0 3px 12px; font-size: 12px; color: var(--ink); }
.obs-cand.is-resolved .obs-cand-name { color: var(--success); font-weight: 600; }
.obs-cand-score { color: var(--muted); font-variant-numeric: tabular-nums; }
.obs-resolved { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line); font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

/* MCP 调用 */
.obs-mcp { display: flex; align-items: center; gap: 10px; padding: 5px 0; border-bottom: 1px dashed var(--line); font-size: 13px; }
.obs-mcp:last-child { border-bottom: none; }
.obs-mcp-tool { font-family: ui-monospace, monospace; color: var(--ink); }

/* 推荐候选 */
.obs-person { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px dashed var(--line); }
.obs-person:last-child { border-bottom: none; }
.obs-person-rank {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  background: var(--surface-tint); color: var(--muted);
  font-size: 12px; display: flex; align-items: center; justify-content: center;
}
.obs-person-main { flex: 1; min-width: 0; }
.obs-person-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.obs-person-score { font-size: 12px; color: var(--blue-strong); font-variant-numeric: tabular-nums; }
.obs-person-ev { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.obs-ev-tag { font-size: 11px; color: var(--muted); background: var(--surface-soft); border: 1px solid var(--line); border-radius: 4px; padding: 1px 6px; }

/* 对话气泡 */
.obs-msg-row { display: flex; margin-bottom: 8px; }
.obs-msg-row.is-user { justify-content: flex-end; }
.obs-msg-bubble {
  max-width: 78%; border-radius: 10px; padding: 8px 12px;
  background: var(--surface-soft); border: 1px solid var(--line);
}
.obs-msg-row.is-user .obs-msg-bubble { background: var(--blue-soft); border-color: var(--blue-line); }
.obs-msg-role { font-size: 11px; color: var(--muted); }
.obs-msg-text { margin: 3px 0 0; font-size: 13px; color: var(--ink); white-space: pre-wrap; word-break: break-word; }
.obs-msg-cards { margin: 4px 0 0; font-size: 11px; color: var(--muted); }

/* 反馈 */
.obs-feedback { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; color: var(--ink); }

:deep(.obs-dialog) { max-width: 1080px; border-radius: var(--radius-md); }
:deep(.obs-dialog .el-dialog__body) { padding-top: 12px; max-height: 78vh; overflow-y: auto; }
</style>
