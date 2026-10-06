<template>
  <!-- Agent 交互面板（二期 agent-panel）：右侧栏 AI 场景展开，参考飞书「豆包工作」侧栏 -->
  <aside class="fpim-side agent-panel">
    <div class="fpim-side-head">
      <span>AI 助手</span>
      <span class="fpim-main-sub" v-if="replies.degraded">（降级模式）</span>
      <button class="fpim-btn ghost" style="margin-left: auto" @click="openKnowledge">📚 知识库</button>
    </div>

    <!-- 知识库管理（二期 R1：预提供知识 → 群内自主代答） -->
    <el-dialog v-model="kbVisible" title="我的知识库（供 Agent 代答）" width="520px" append-to-body destroy-on-close>
      <div v-for="k in kbList" :key="k.id" class="kb-item">
        <div class="kb-item-main">
          <div class="kb-item-title">{{ k.title }}</div>
          <div class="kb-item-meta">
            已授权 {{ k.sharedGroupIds.length }} 个群 ·
            <a href="javascript:;" @click="removeKnowledge(k)">撤销</a>
          </div>
        </div>
      </div>
      <div v-if="!kbList.length" class="fpim-empty">还没有知识。添加后在授权的群里被 @ 时 Agent 会代答。</div>

      <div class="kb-form">
        <input v-model="kbForm.title" placeholder="知识标题，例如「metric key 规范」" />
        <textarea v-model="kbForm.content" rows="3" placeholder="知识内容（Agent 代答的依据）"></textarea>
        <select v-model="kbForm.groupId" style="width: 100%; height: 32px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font: inherit; font-size: 13px;">
          <option :value="null">授权给：暂不授权任何群</option>
          <option v-for="c in groupOptions" :key="c.id" :value="c.id">授权给群：{{ c.title || c.peer?.name || c.id }}</option>
        </select>
        <button class="fpim-btn prim" :disabled="!kbForm.title.trim() || !kbForm.content.trim()" @click="saveKnowledge">
          保存知识
        </button>
      </div>
    </el-dialog>

    <div ref="stream" class="fpim-side-scroll agent-stream">
      <div v-if="!messages.length" class="fpim-empty">
        和 Agent 聊聊当前会话：<br />
        「总结一下这段对话」「这个问题该谁处理」「生成处理建议」<br />
        会自动带上当前会话的最近上下文。
      </div>

      <div v-for="(m, i) in messages" :key="i" class="agent-msg" :class="`is-${m.role}`">
        <div class="agent-msg-text">{{ m.text }}</div>
        <div v-if="m.actions?.length" class="agent-actions">
          <div v-for="a in m.actions" :key="a.id" class="agent-action-card">
            <div class="agent-action-title">{{ a.title }}</div>
            <div class="agent-action-desc">{{ a.description }}</div>
            <div class="agent-action-hint">待确认后执行（草稿）</div>
          </div>
        </div>
      </div>

      <div v-if="sending" class="agent-msg is-agent">
        <div class="agent-msg-text">思考中…</div>
      </div>
    </div>

    <div class="agent-input">
      <textarea
        v-model="text"
        rows="2"
        placeholder="问 Agent…（Enter 发送，Shift+Enter 换行）"
        :disabled="sending"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button class="fpim-btn prim" :disabled="!text.trim() || sending" @click="send">
        {{ sending ? "…" : "发送" }}
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import http from "../../services/api/http.js";
import {
  createKnowledge, listKnowledge, revokeKnowledge,
} from "../../services/api/agentKnowledge.js";
import { useImStore } from "../../stores/im.js";

const store = useImStore();

const props = defineProps({
  conversationId: { type: [Number, String], default: null },
});

// ── 知识库管理（二期 R1）──
const kbVisible = ref(false);
const kbList = ref([]);
const kbForm = ref({ title: "", content: "", groupId: null });

const groupOptions = computed(() => (store.conversations || []).filter((c) => c.type === "group"));

async function openKnowledge() {
  try {
    const res = await listKnowledge();
    kbList.value = res.items || [];
    kbVisible.value = true;
  } catch (err) {
    ElMessage.error(err.message || "加载失败");
  }
}

async function saveKnowledge() {
  try {
    await createKnowledge({
      title: kbForm.value.title.trim(),
      content: kbForm.value.content.trim(),
      domains: [],
      sharedGroupIds: kbForm.value.groupId ? [kbForm.value.groupId] : [],
    });
    kbForm.value = { title: "", content: "", groupId: null };
    const res = await listKnowledge();
    kbList.value = res.items || [];
    ElMessage.success("已保存。在授权的群里被 @ 时 Agent 将基于它代答");
  } catch (err) {
    ElMessage.error(err.message || "保存失败");
  }
}

async function removeKnowledge(k) {
  try {
    await revokeKnowledge(k.id);
    kbList.value = kbList.value.filter((x) => x.id !== k.id);
    ElMessage.success("已撤销，Agent 不再引用");
  } catch (err) {
    ElMessage.error(err.message || "撤销失败");
  }
}

const messages = ref([]);
const replies = ref({ degraded: false });
const text = ref("");
const sending = ref(false);
const stream = ref(null);

watch(messages, () => {
  nextTick(() => {
    if (stream.value) stream.value.scrollTop = stream.value.scrollHeight;
  });
}, { deep: true });

async function send() {
  const body = text.value.trim();
  if (!body || sending.value) return;
  messages.value.push({ role: "user", text: body });
  text.value = "";
  sending.value = true;
  try {
    const res = await http.post("/agent/chat", {
      text: body,
      conversationId: props.conversationId || null,
    });
    replies.value = { degraded: !!res.reply?.degraded };
    messages.value.push({
      role: "agent",
      text: res.reply?.text || "（无回复）",
      actions: res.reply?.actions || [],
    });
  } catch (err) {
    ElMessage.error(err.message || "Agent 暂不可用");
    messages.value.push({ role: "agent", text: "抱歉，我暂时没有响应，请稍后再试。" });
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped>
.agent-panel {
  display: flex;
  flex-direction: column;
}
.agent-stream {
  flex: 1;
}
.agent-msg {
  margin: 8px 12px;
  display: flex;
  flex-direction: column;
}
.agent-msg.is-user {
  align-items: flex-end;
}
.agent-msg-text {
  max-width: 92%;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.agent-msg.is-user .agent-msg-text {
  background: var(--im-primary-weak);
  color: var(--im-text-1);
}
.agent-msg.is-agent .agent-msg-text {
  background: var(--im-bg-side);
  color: var(--im-text-1);
}
.agent-actions {
  margin-top: 6px;
  width: 100%;
}
.agent-action-card {
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  padding: 8px 10px;
  margin-bottom: 6px;
}
.agent-action-title {
  font-size: 13px;
  font-weight: 500;
}
.agent-action-desc {
  font-size: 12px;
  color: var(--im-text-2);
  margin-top: 2px;
}
.agent-action-hint {
  font-size: 11px;
  color: var(--im-warn, #ff8800);
  margin-top: 4px;
}
.kb-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 0.5px solid var(--im-line);
}
.kb-item-title {
  font-size: 13px;
  font-weight: 500;
}
.kb-item-meta {
  font-size: 12px;
  color: var(--im-text-3);
  margin-top: 2px;
}
.kb-form {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kb-form input,
.kb-form textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 8px 10px;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  font: inherit;
  font-size: 13px;
  outline: none;
  resize: vertical;
}
.agent-input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 10px 12px;
  border-top: 0.5px solid var(--im-line);
}
.agent-input textarea {
  flex: 1;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  outline: none;
}
</style>
