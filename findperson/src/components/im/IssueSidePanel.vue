<template>
  <aside class="fpim-side">
    <div class="fpim-side-head" style="display: flex; align-items: center; justify-content: space-between">
      <span>
        问题详情
        <span v-if="issues.length > 1" class="fpim-main-sub" style="margin-left: 8px">
          （本会话共 {{ issues.length }} 个）
        </span>
      </span>
      <button class="fpim-btn prim" style="padding: 4px 12px; font-size: 12px" @click="openCreate">
        ＋ 立项
      </button>
    </div>

    <div class="fpim-side-scroll">
      <div v-if="!issues.length" class="fpim-empty">
        这个会话还没有关联问题。<br />
        聊到一个要跟踪的问题时，点右上角「＋ 立项」把它挂到这个会话上，<br />
        之后这个会话里说的每句话都会自动留痕。
      </div>

      <template v-for="issue in issues" :key="issue.id">
        <section class="fpim-section">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
            <span class="fpim-chip" :class="issueStatusMeta(issue.status).cls">
              {{ issueStatusMeta(issue.status).label }}
            </span>
            <span class="fpim-main-sub">#{{ issue.id }}</span>
          </div>
          <div style="font-size: 14px; font-weight: 600; margin-bottom: 10px">
            {{ issue.summary || issue.question }}
          </div>
          <dl style="margin: 0">
            <div class="fpim-kv"><dt>责任人</dt><dd>{{ issue.assigneeName || "未指定" }}</dd></div>
            <div class="fpim-kv"><dt>创建</dt><dd>{{ fullTime(issue.createdAt) }}</dd></div>
            <!-- 两个"留痕"字段分开显示：已读 ≠ 回复，这是本机制的核心区分 -->
            <div class="fpim-kv">
              <dt>首次已读</dt>
              <dd :style="!issue.firstReadAt ? 'color: var(--im-text-3)' : ''">
                {{ issue.firstReadAt ? fullTime(issue.firstReadAt) : "未读" }}
              </dd>
            </div>
            <div class="fpim-kv">
              <dt>首次响应</dt>
              <dd :style="!issue.firstResponseAt ? 'color: var(--im-text-3)' : ''">
                {{ issue.firstResponseAt ? fullTime(issue.firstResponseAt) : "未响应" }}
              </dd>
            </div>
            <div v-if="issue.resolvedAt" class="fpim-kv">
              <dt>已解决</dt><dd>{{ fullTime(issue.resolvedAt) }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="issue.resolutionNote" class="fpim-section">
          <h5>解决结论</h5>
          <p style="margin: 0; font-size: 13px; color: var(--im-text-2)">{{ issue.resolutionNote }}</p>
        </section>

        <section class="fpim-section">
          <h5>处理过程（{{ (issue.timeline || []).length }} 条留痕）</h5>
          <ul v-if="issue.timeline?.length" class="fpim-timeline">
            <li
              v-for="ev in issue.timeline"
              :key="ev.id"
              :class="{ 'is-key': KEY_EVENTS.has(ev.eventType) }"
            >
              <span>{{ eventLabel(ev.eventType) }}<template v-if="ev.operatorName"> · {{ ev.operatorName }}</template></span>
              <span v-if="ev.detail" style="color: var(--im-text-2)"> — {{ ev.detail }}</span>
              <span class="tl-time">{{ fullTime(ev.createdAt) }}</span>
            </li>
          </ul>
          <div v-else class="fpim-empty" style="padding: 12px 0">暂无过程记录</div>
        </section>

        <!-- 只有提问方能确认解决：被问方不能自己点"已解决" -->
        <section v-if="canResolve(issue)" class="fpim-section">
          <button class="fpim-btn prim" style="width: 100%" @click="openResolve(issue)">
            标记为已解决
          </button>
          <p style="font-size: 12px; color: var(--im-text-3); margin: 8px 0 0">
            解决后该问题会进入知识沉淀候选，供后续提问直接命中。
          </p>
        </section>

        <div v-if="issues.length > 1" style="height: 1px; background: var(--im-line); margin: 4px 0 18px"></div>
      </template>
    </div>

    <el-dialog
      v-model="dialogVisible"
      title="标记已解决"
      width="440px"
      append-to-body
      destroy-on-close
    >
      <p style="font-size: 13px; color: var(--im-text-2); margin: 0 0 10px">
        写一句结论，它会成为知识沉淀的素材（可后续编辑）。
      </p>
      <textarea
        v-model="note"
        rows="4"
        placeholder="例如：报销权限走 OA 费用报销模块，需部门负责人审批后由财务开通。"
        style="width: 100%; box-sizing: border-box; padding: 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-family: inherit; font-size: 13px; line-height: 1.7; resize: vertical"
      ></textarea>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="dialogVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="submitting" @click="confirmResolve">
            {{ submitting ? "提交中…" : "确认已解决" }}
          </button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 立项对话框：把这段聊天升格为"要跟踪的问题" ── -->
    <el-dialog
      v-model="createVisible"
      title="在本会话立项"
      width="480px"
      append-to-body
      destroy-on-close
    >
      <p style="font-size: 13px; color: var(--im-text-2); margin: 0 0 12px">
        立项后：这个问题会被留痕跟踪（责任人已读、首次回复、解决情况都会记录），
        本会话后续消息自动挂接到这个问题上。
      </p>

      <div style="margin-bottom: 12px">
        <div class="fpim-form-label">问题描述 *</div>
        <textarea
          v-model="createForm.question"
          rows="3"
          placeholder="把问题写清楚，例如：报销系统的权限申请该走哪个流程？"
          style="width: 100%; box-sizing: border-box; padding: 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-family: inherit; font-size: 13px; line-height: 1.7; resize: vertical"
        ></textarea>
      </div>

      <div style="margin-bottom: 12px">
        <div class="fpim-form-label">责任人 *</div>
        <select
          v-model="createForm.assigneePersonId"
          style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 8px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-family: inherit; font-size: 13px; background: #fff"
        >
          <option v-for="m in assigneeOptions" :key="m.id" :value="m.id">
            {{ m.name }}{{ m.department ? ` · ${m.department}` : "" }}
          </option>
        </select>
        <p v-if="isDirect" style="font-size: 12px; color: var(--im-text-3); margin: 6px 0 0">
          单聊默认责任人为对方。群聊必须显式指定唯一责任人——集体负责等于无人负责。
        </p>
      </div>

      <div style="margin-bottom: 4px">
        <div class="fpim-form-label">一句话摘要（可选，默认取问题前 120 字）</div>
        <input
          v-model="createForm.summary"
          placeholder="用于问题列表展示"
          style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-family: inherit; font-size: 13px"
        />
      </div>

      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="createVisible = false">取消</button>
          <button
            class="fpim-btn prim"
            :disabled="creating || !createForm.question.trim()"
            @click="confirmCreate"
          >
            {{ creating ? "创建中…" : "确认立项" }}
          </button>
        </div>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchConversationIssues } from "../../services/api/im.js";
import http from "../../services/api/http.js";
import { eventLabel, fullTime, issueStatusMeta } from "../../services/im/format.js";
import { useAuthStore } from "../../stores/auth.js";
import { useImStore } from "../../stores/im.js";

const store = useImStore();
const auth = useAuthStore();

/** 时间线上标蓝的关键节点 */
const KEY_EVENTS = new Set(["read", "responded", "resolved", "knowledged"]);

const dialogVisible = ref(false);
const submitting = ref(false);
const note = ref("");
const target = ref(null);

// ⚠️ 必须用 computed：写成 () => store.issues 会让模板拿到函数对象，
// issues.length 变成函数参数个数（恒为 0），面板永远显示"暂无问题"
const issues = computed(() => store.issues);

/** 只有提问方能确认解决（提问人 = issues.user_id；后端也会再校验一次） */
function canResolve(issue) {
  if (issue.status === "resolved") return false;
  return !issue.askerId || issue.askerId === auth.userId;
}

// ── 立项 ──
const createVisible = ref(false);
const creating = ref(false);
const createForm = reactive({ question: "", assigneePersonId: "", summary: "" });

const isDirect = computed(() => store.active?.type === "direct");

/** 责任人候选：会话成员里除了"我"以外的所有人（责任人不能是自己） */
const assigneeOptions = computed(() => {
  const members = store.active?.members || [];
  return members.filter((m) => m.id !== auth.userId);
});

function openCreate() {
  createForm.question = "";
  createForm.summary = "";
  // 默认责任人：单聊默认对方；群聊默认第一个人选
  const opts = assigneeOptions.value;
  createForm.assigneePersonId = opts[0]?.id || "";
  createVisible.value = true;
}

async function confirmCreate() {
  if (!createForm.question.trim() || !store.activeId) return;
  if (!createForm.assigneePersonId) {
    ElMessage.warning("请选择责任人");
    return;
  }
  creating.value = true;
  try {
    await store.createIssue(store.activeId, {
      question: createForm.question.trim(),
      assigneePersonId: createForm.assigneePersonId,
      summary: createForm.summary.trim() || null,
    });
    ElMessage.success("已立项：本会话后续消息都会自动留痕");
    createVisible.value = false;
  } catch (err) {
    ElMessage.error(err.message || "立项失败");
  } finally {
    creating.value = false;
  }
}

// 会话头部「＋ 立项」按钮通过自定义事件唤起本对话框（与 fpim:start-conversation 同一套约定）
function onCreateEvent() {
  if (store.active) openCreate();
}
onMounted(() => window.addEventListener("fpim:create-issue", onCreateEvent));
onUnmounted(() => window.removeEventListener("fpim:create-issue", onCreateEvent));

function openResolve(issue) {
  target.value = issue;
  note.value = issue.resolutionNote || "";
  dialogVisible.value = true;
}

async function confirmResolve() {
  if (!target.value) return;
  submitting.value = true;
  try {
    await http.patch(`/issues/${target.value.id}`, {
      status: "resolved",
      resolutionNote: note.value.trim() || null,
    });
    ElMessage.success("已标记为已解决，进入知识沉淀候选");
    dialogVisible.value = false;
    await store.loadIssues(store.activeId);
    await refreshConversationIssues();
  } catch (err) {
    ElMessage.error(err.message || "提交失败");
  } finally {
    submitting.value = false;
  }
}

async function refreshConversationIssues() {
  if (!store.activeId) return;
  try {
    const res = await fetchConversationIssues(store.activeId);
    store.issues = res.items || [];
  } catch {
    /* 忽略：面板刷新失败不影响主流程 */
  }
}
</script>
