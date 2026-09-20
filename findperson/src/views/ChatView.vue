<template>
  <div class="fpim">
    <ConversationList @compose="pickerVisible = true" />

    <!-- ── 会话区 ── -->
    <section class="fpim-main">
      <template v-if="store.active">
        <header class="fpim-main-head">
          <div class="fpim-avatar sm" :style="{ background: avatarColor(peerKey) }">
            {{ avatarText(title) }}
          </div>
          <div>
            <div class="fpim-main-title">{{ title }}</div>
            <div class="fpim-main-sub">{{ subtitle }}</div>
          </div>
          <div class="fpim-conn">
            <span class="fpim-dot" :class="connDot"></span>{{ connText }}
          </div>
          <button
            class="fpim-btn"
            title="把这段聊天里的问题升格为可跟踪的问题（自动留痕）"
            @click="createIssue()"
          >＋ 立项</button>
          <button
            v-if="store.active.type === 'group'"
            class="fpim-btn"
            style="margin-left: 10px"
            @click="inviteVisible = true"
          >邀请成员</button>
          <button
            class="fpim-btn ghost"
            :title="sideVisible ? '收起问题面板' : '展开问题面板'"
            @click="sideVisible = !sideVisible"
          >{{ sideVisible ? "收起详情" : "问题详情" }}</button>
        </header>

        <MessageList @resolve="onResolve" @focus-issue="sideVisible = true" />
        <MessageComposer />
      </template>

      <div v-else class="fpim-empty" style="margin: auto">
        <div style="font-size: 15px; color: var(--im-text-2); margin-bottom: 6px">
          选择一个会话开始沟通
        </div>
        <div>或者点左上角 ＋ 从名片库找人发起</div>
      </div>
    </section>

    <!-- ── 问题详情面板 ── -->
    <IssueSidePanel v-if="store.active && sideVisible" />

    <!-- ── 发起会话：从名片库选人（免加好友） ── -->
    <el-dialog v-model="pickerVisible" title="发起会话" width="520px" append-to-body destroy-on-close>
      <input
        v-model="pickerKeyword"
        placeholder="搜索姓名 / 部门 / 负责领域"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 10px"
      />
      <div style="max-height: 380px; overflow-y: auto">
        <div
          v-for="p in pickerResults"
          :key="p.id"
          class="fpim-conv"
          @click="startWith(p.id)"
        >
          <div class="fpim-avatar" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1">
              <span class="fpim-conv-name">{{ p.name }}</span>
            </div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ [p.department, p.role].filter(Boolean).join(" · ") }}</span>
            </div>
          </div>
        </div>
        <div v-if="!pickerResults.length" class="fpim-empty">没有匹配的人员</div>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="pickerVisible = false">关闭</button>
          <button class="fpim-btn" @click="createGroupVisible = true">建群聊</button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 建群 ── -->
    <el-dialog v-model="createGroupVisible" title="新建群聊（上限 100 人）" width="520px" append-to-body destroy-on-close>
      <input
        v-model="groupTitle"
        placeholder="群名称，例如：报销权限问题会诊"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 10px"
      />
      <input
        v-model="memberKeyword"
        placeholder="搜索并勾选成员"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 8px"
      />
      <div style="max-height: 300px; overflow-y: auto">
        <label
          v-for="p in memberResults"
          :key="p.id"
          class="fpim-conv"
          style="cursor: pointer"
        >
          <input type="checkbox" :value="p.id" v-model="selectedMembers" style="flex: 0 0 auto" />
          <div class="fpim-avatar sm" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ p.name }}</span></div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ p.department || "" }}</span>
            </div>
          </div>
        </label>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end; align-items: center">
          <span style="margin-right: auto; font-size: 12px; color: var(--im-text-3)">
            已选 {{ selectedMembers.length }} 人
          </span>
          <button class="fpim-btn" @click="createGroupVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="!groupTitle.trim() || !selectedMembers.length" @click="doCreateGroup">
            创建
          </button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 邀请成员 ── -->
    <el-dialog v-model="inviteVisible" title="邀请成员" width="520px" append-to-body destroy-on-close>
      <input
        v-model="memberKeyword"
        placeholder="搜索人员"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 8px"
      />
      <div style="max-height: 320px; overflow-y: auto">
        <label
          v-for="p in memberResults.filter(invitable)"
          :key="p.id"
          class="fpim-conv"
          style="cursor: pointer"
        >
          <input type="checkbox" :value="p.id" v-model="selectedMembers" style="flex: 0 0 auto" />
          <div class="fpim-avatar sm" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ p.name }}</span></div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ p.department || "" }}</span>
            </div>
          </div>
        </label>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="inviteVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="!selectedMembers.length" @click="doInvite">加入</button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { avatarColor, avatarText } from "../services/im/format.js";
import { useAuthStore } from "../stores/auth.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useImStore } from "../stores/im.js";
import ConversationList from "../components/im/ConversationList.vue";
import IssueSidePanel from "../components/im/IssueSidePanel.vue";
import MessageComposer from "../components/im/MessageComposer.vue";
import MessageList from "../components/im/MessageList.vue";

const store = useImStore();
const directory = useDirectoryStore();
const auth = useAuthStore();

const sideVisible = ref(true);
const pickerVisible = ref(false);
const createGroupVisible = ref(false);
const inviteVisible = ref(false);
const pickerKeyword = ref("");
const memberKeyword = ref("");
const groupTitle = ref("");
const selectedMembers = ref([]);

const title = computed(() => store.active?.title || store.active?.peer?.name || "会话");
const peerKey = computed(() => store.active?.peer?.id || store.active?.title || "");
const subtitle = computed(() => {
  const conv = store.active;
  if (!conv) return "";
  if (conv.type === "group") {
    const names = (conv.members || []).map((m) => m.name).join("、");
    return `${(conv.members || []).length} 人 · ${names}`;
  }
  return [conv.peer?.department, conv.peer?.role].filter(Boolean).join(" · ");
});

const CONN_TEXT = {
  open: "已连接", connecting: "连接中", reconnecting: "重连中",
  error: "连接异常", closed: "已断开", idle: "未连接",
};
const connText = computed(() => CONN_TEXT[store.connection] || store.connection);
const connDot = computed(() => (store.connection === "open" ? "on"
  : store.connection === "reconnecting" || store.connection === "error" ? "warn" : ""));

/** 排除自己 */
const candidates = computed(() =>
  directory.people.filter((p) => p.id !== auth.userId && p.active !== false));

function match(list, kw) {
  const key = kw.trim().toLowerCase();
  if (!key) return list.slice(0, 60);
  return list.filter((p) =>
    `${p.name} ${p.department || ""} ${p.role || ""} ${(p.domains || []).join(" ")}`
      .toLowerCase().includes(key)).slice(0, 60);
}

const pickerResults = computed(() => match(candidates.value, pickerKeyword.value));
const memberResults = computed(() => match(candidates.value, memberKeyword.value));

const invitable = (p) => !(store.active?.members || []).some((m) => m.id === p.id);

async function startWith(peerId) {
  try {
    await store.openWith(peerId);
    pickerVisible.value = false;
    pickerKeyword.value = "";
  } catch (err) {
    ElMessage.error(err.message || "发起会话失败");
  }
}

async function doCreateGroup() {
  try {
    await store.newGroup(groupTitle.value.trim(), selectedMembers.value);
    createGroupVisible.value = false;
    groupTitle.value = "";
    selectedMembers.value = [];
  } catch (err) {
    ElMessage.error(err.message || "建群失败");
  }
}

async function doInvite() {
  try {
    await store.invite(store.activeId, selectedMembers.value);
    ElMessage.success("已加入群聊");
    inviteVisible.value = false;
    selectedMembers.value = [];
  } catch (err) {
    ElMessage.error(err.message || "邀请失败");
  }
}

/** 会话里点「标记已解决」——问题卡上的快捷入口，走侧栏同一套接口 */
async function onResolve() {
  sideVisible.value = true;
  ElMessage.info("请在右侧「问题详情」里填写解决结论");
}

/** 头部「＋ 立项」：先展开问题面板，再唤起立项对话框（IssueSidePanel 监听同一事件） */
function createIssue() {
  sideVisible.value = true;
  window.dispatchEvent(new CustomEvent("fpim:create-issue"));
}

function onCreated() {
  // 名片/问答侧发起会话后，直接跳到这里；会话已由 store.openWith 建好并选中。
  pickerVisible.value = false;
}

onMounted(() => {
  store.init();
  window.addEventListener("fpim:start-conversation", onCreated);
});
onUnmounted(() => window.removeEventListener("fpim:start-conversation", onCreated));

watch(() => auth.userId, () => store.teardown(), { flush: "post" });
</script>
