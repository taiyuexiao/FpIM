<template>
  <div class="fpim todo-page">
    <header class="todo-head">
      <h3>待办</h3>
      <span class="fpim-main-sub">问题闭环的驱动入口：待你处理的问题在这里排队</span>
    </header>

    <nav class="todo-tabs">
      <button
        class="todo-tab"
        :class="{ active: tab === 'assigned' }"
        @click="tab = 'assigned'; applyFilter()"
      >
        待我处理
        <em v-if="issues.assignedOpen" class="todo-count">{{ issues.assignedOpen }}</em>
      </button>
      <button
        class="todo-tab"
        :class="{ active: tab === 'mine' }"
        @click="tab = 'mine'; applyFilter()"
      >
        我提出的
      </button>
    </nav>

    <div class="todo-filters">
      <button
        v-for="t in statusTabs"
        :key="t.value"
        class="todo-chip"
        :class="{ active: filter === t.value }"
        @click="filter = t.value; applyFilter()"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="todo-list">
      <div v-if="loading" class="fpim-empty">加载中…</div>
      <div v-else-if="!rows.length" class="fpim-empty">
        {{ tab === "assigned" ? "没有待你处理的问题，太棒了。" : "你还没有提出的问题。" }}
      </div>

      <div
        v-for="issue in rows"
        :key="issue.id"
        class="todo-row"
        @click="openConversation(issue)"
      >
        <span class="fpim-chip" :class="issueStatusMeta(issue.status).cls">
          {{ issueStatusMeta(issue.status).label }}
        </span>
        <div class="todo-main">
          <div class="todo-title">{{ issue.summary || issue.question }}</div>
          <div class="todo-meta">
            <span v-if="tab === 'assigned'">来自 {{ issue.askerName || issue.askerId }}</span>
            <span v-else>责任人：{{ issue.assigneeName || "未指定" }}</span>
            <span>·</span>
            <span>{{ shortTime(issue.lastActionAt) }}</span>
            <!-- 待我处理视角：我读过没有、回过没有 -->
            <template v-if="tab === 'assigned' && issue.status !== 'resolved'">
              <span>·</span>
              <span :style="traceStyle(issue.firstReadAt)">
                {{ issue.firstReadAt ? "已读" : "未读" }}
              </span>
              <span :style="traceStyle(issue.firstResponseAt)">
                {{ issue.firstResponseAt ? "已回复" : "未回复" }}
              </span>
            </template>
          </div>
        </div>
        <button class="fpim-btn" @click.stop="openConversation(issue)">进入会话</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { issueStatusMeta, shortTime } from "../services/im/format.js";
import { useAuthStore } from "../stores/auth.js";
import { useImStore } from "../stores/im.js";
import { useIssuesStore } from "../stores/issues.js";

const router = useRouter();
const auth = useAuthStore();
const im = useImStore();
const issues = useIssuesStore();

const tab = ref("assigned");
const filter = ref("open"); // open = 未联系+处理中
const loading = ref(false);

const statusTabs = [
  { value: "open", label: "待办（未结）" },
  { value: "", label: "全部" },
  { value: "resolved", label: "已解决" },
  { value: "unresolved", label: "未解决" },
];

const rows = computed(() => {
  const list = tab.value === "assigned" ? issues.assignedItems : issues.items;
  if (filter.value === "open") {
    return list.filter((i) => i.status !== "resolved");
  }
  if (filter.value) {
    return list.filter((i) => i.status === filter.value);
  }
  return list;
});

const traceStyle = (v) => (v ? "color: var(--im-text-3)" : "color: var(--im-brand)");

async function applyFilter() {
  loading.value = true;
  try {
    if (tab.value === "assigned") {
      await issues.loadAssigned();
    } else {
      await issues.load();
    }
  } finally {
    loading.value = false;
  }
}

/** 点击问题 → 进会话：已挂会话的直接进，否则取或建与对方（对方 = 提问方或责任人）的单聊 */
async function openConversation(issue) {
  try {
    if (issue.conversationId) {
      await router.push({ name: "chat" });
      await im.selectConversation(issue.conversationId);
      return;
    }
    const peerId = tab.value === "assigned" ? issue.askerId : issue.assigneePersonId;
    if (!peerId) {
      ElMessage.warning("该问题还没有责任人，先在智能问答里指派");
      return;
    }
    await im.openWith(peerId, issue.id);
    await router.push({ name: "chat" });
  } catch (err) {
    ElMessage.error(err.message || "打开会话失败");
  }
}

onMounted(async () => {
  await applyFilter();
  // 侧栏红点也要同步
  issues.loadAssigned();
});
</script>

<style scoped>
.todo-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 20px 24px;
  height: 100%;
  overflow-y: auto;
}
.todo-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.todo-head h3 { margin: 0; font-size: 17px; }
.todo-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 0.5px solid var(--im-line);
  margin-bottom: 12px;
}
.todo-tab {
  border: none;
  background: none;
  padding: 8px 14px;
  font-size: 13px;
  font-family: inherit;
  color: var(--im-text-2);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  display: flex;
  align-items: center;
  gap: 6px;
}
.todo-tab.active {
  color: var(--im-brand);
  border-bottom-color: var(--im-brand);
  font-weight: 600;
}
.todo-count {
  background: #f54a45;
  color: #fff;
  border-radius: 9px;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  font-size: 11px;
  font-style: normal;
  text-align: center;
  padding: 0 5px;
}
.todo-filters {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}
.todo-chip {
  border: 0.5px solid var(--im-line-strong);
  background: #fff;
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 12px;
  font-family: inherit;
  color: var(--im-text-2);
  cursor: pointer;
}
.todo-chip.active {
  background: var(--im-brand-bg, rgba(51, 112, 255, 0.08));
  border-color: var(--im-brand);
  color: var(--im-brand);
}
.todo-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 0.5px solid var(--im-line);
  cursor: pointer;
  background: #fff;
}
.todo-row:hover { background: var(--im-hover, rgba(0, 0, 0, 0.03)); }
.todo-main { flex: 1; min-width: 0; }
.todo-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--im-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.todo-meta {
  margin-top: 3px;
  font-size: 12px;
  color: var(--im-text-3);
  display: flex;
  gap: 4px;
}
</style>
