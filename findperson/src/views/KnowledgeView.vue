<!-- 知识库(面向人):平台沉淀的标准答案,与 Agent 检索用的是同一份数据源 -->
<template>
  <section class="view active">
    <div class="page-heading">
      <div>
        <h1>知识库</h1>
        <p class="page-sub">平台沉淀的标准答案：谁问过、谁负责、什么时候更新的。问答里问同样的问题会直接命中这里。</p>
      </div>
    </div>

    <div class="search-field kb-search">
      <el-icon><Search /></el-icon>
      <el-input v-model="keyword" placeholder="搜索问题或答案，例如「接口对接」「自动化测试」" clearable />
    </div>

    <p v-if="loading" class="empty-state">加载中…</p>
    <template v-else>
      <p v-if="faqs.length" class="kb-stats">共 {{ faqs.length }} 条知识 · 累计被引用 {{ totalAsked }} 次</p>
      <div class="kb-list">
        <article v-for="item in filtered" :key="item.id" class="kb-card" :class="{ 'is-open': openId === item.id }">
          <header class="kb-head" @click="toggle(item.id)">
            <div>
              <h3>{{ item.question }}</h3>
              <p class="kb-meta">
                <span v-if="item.ownerName">责任人：{{ item.ownerName }}</span>
                <span v-if="item.askedCount">被引用 {{ item.askedCount }} 次</span>
                <span v-if="item.updatedAt">更新于 {{ formatDate(item.updatedAt) }}</span>
              </p>
            </div>
            <span class="kb-toggle">{{ openId === item.id ? '收起' : '展开' }}</span>
          </header>
          <div v-if="openId === item.id" class="kb-body">
            <p class="kb-answer">{{ item.answer }}</p>
            <div v-if="item.tags?.length" class="field-row">
              <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <p class="kb-foot">来自知识库 FAQ #{{ item.id }}；由「我的问题」里标记「已解决」的问答沉淀而来。</p>
          </div>
        </article>
        <p v-if="!filtered.length" class="empty-state">
          {{ faqs.length ? '没有匹配的知识条目。' : '知识库还是空的。问答里被标记「已解决」的问题会沉淀到这里。' }}
        </p>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Search } from "@element-plus/icons-vue";
import { fetchFaqs } from "../services/api/issues.js";
import { isServerMode } from "../services/mode.js";

const faqs = ref([]);
const keyword = ref("");
const openId = ref(null);
const loading = ref(false);

const filtered = computed(() => {
  const key = keyword.value.trim().toLowerCase();
  if (!key) return faqs.value;
  return faqs.value.filter((item) =>
    `${item.question} ${item.answer} ${(item.tags || []).join(" ")}`.toLowerCase().includes(key));
});
const totalAsked = computed(() => faqs.value.reduce((sum, item) => sum + (item.askedCount || 0), 0));

function toggle(id) {
  openId.value = openId.value === id ? null : id;
}
function formatDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

onMounted(async () => {
  if (!isServerMode()) return;
  loading.value = true;
  try {
    const data = await fetchFaqs();
    faqs.value = data.items || [];
  } catch {
    faqs.value = [];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.page-sub { margin: 6px 0 0; color: var(--text-secondary, #666); font-size: 13px; }
.kb-search { margin: 14px 0 10px; }
.kb-stats { margin: 0 0 10px; color: var(--text-secondary, #909399); font-size: 13px; }
.kb-list { display: flex; flex-direction: column; gap: 10px; }
.kb-card {
  border: 1px solid var(--border-color, #eef2f7);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.kb-card.is-open { border-color: #c9d8ff; box-shadow: 0 2px 10px rgba(74, 125, 255, 0.08); }
.kb-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 12px 14px; cursor: pointer;
}
.kb-head h3 { margin: 0; font-size: 15px; color: #303133; }
.kb-meta { display: flex; flex-wrap: wrap; gap: 12px; margin: 6px 0 0; color: #909399; font-size: 12px; }
.kb-toggle { flex: 0 0 auto; color: #4a7dff; font-size: 13px; }
.kb-body { padding: 0 14px 14px; }
.kb-answer { margin: 0 0 10px; white-space: pre-wrap; line-height: 1.75; color: #303133; }
.kb-foot { margin: 10px 0 0; color: #c0c4cc; font-size: 12px; }
</style>
