<template>
  <aside class="fpim-list">
    <div class="fpim-list-head">
      <span class="fpim-list-title">消息</span>
      <el-dropdown trigger="click" @command="(cmd) => cmd === 'create-group' && $emit('compose')">
        <button class="fpim-iconbtn" title="发起">＋</button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="create-group">创建群组</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="fpim-list-search">
      <input v-model="keyword" type="text" placeholder="搜索会话或联系人" />
    </div>

    <div class="fpim-list-scroll">
      <!-- ── 全局搜索态：联系人 + 跨会话消息 + 会话 ── -->
      <template v-if="searchMode">
        <div v-if="contactResults.length" class="fpim-search-group">
          <div class="fpim-search-label">联系人</div>
          <div
            v-for="p in contactResults"
            :key="p.id"
            class="fpim-search-row"
            @click="startChat(p)"
          >
            <div class="fpim-avatar sm" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
            <div class="fpim-conv-main">
              <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ p.name }}</span></div>
              <div class="fpim-conv-row2">
                <span class="fpim-conv-preview">{{ [p.department, p.role].filter(Boolean).join(" · ") }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="msgResults.length" class="fpim-search-group">
          <div class="fpim-search-label">消息</div>
          <div
            v-for="m in msgResults"
            :key="m.id"
            class="fpim-search-row"
            @click="jumpToMsg(m)"
          >
            <div class="fpim-conv-main">
              <div class="fpim-conv-row1">
                <span class="fpim-conv-name">{{ convTitleOf(m.conversationId) }}</span>
                <span class="fpim-conv-time">{{ shortTime(m.createdAt) }}</span>
              </div>
              <div class="fpim-conv-row2">
                <span class="fpim-conv-preview">{{ m.content?.text || m.content?.name || "[附件]" }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="filtered.length" class="fpim-search-group">
          <div class="fpim-search-label">会话</div>
          <div
            v-for="conv in filtered"
            :key="`c-${conv.id}`"
            class="fpim-search-row"
            @click="store.selectConversation(conv.id)"
          >
            <div class="fpim-avatar sm" :style="{ background: avatarColor(conv.peer?.id || conv.title) }">
              {{ avatarText(displayName(conv)) }}
            </div>
            <div class="fpim-conv-main">
              <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ displayName(conv) }}</span></div>
            </div>
          </div>
        </div>

        <div v-if="!contactResults.length && !msgResults.length && !filtered.length" class="fpim-empty">
          没有匹配的结果
        </div>
      </template>

      <!-- ── 常态：会话列表 ── -->
      <template v-else>
      <div v-if="!filtered.length" class="fpim-empty">
        还没有会话，去通讯录发起一个
      </div>

      <div
        v-for="conv in filtered"
        :key="conv.id"
        class="fpim-conv"
        :class="{ 'is-active': conv.id === store.activeId }"
        @click="store.selectConversation(conv.id)"
        @contextmenu.prevent="openMenu($event, conv)"
      >
        <div
          class="fpim-avatar"
          :style="{ background: avatarColor(conv.peer?.id || conv.title) }"
        >{{ avatarText(displayName(conv)) }}</div>

        <div class="fpim-conv-main">
          <div class="fpim-conv-row1">
            <span class="fpim-conv-name">
              <em v-if="conv.pinned" class="fpim-conv-flag" title="已置顶">📌</em>
              {{ displayName(conv) }}
            </span>
            <span class="fpim-conv-time">{{ shortTime(conv.lastMessageAt) }}</span>
          </div>
          <div class="fpim-conv-row2">
            <span class="fpim-conv-preview">{{ previewOf(conv.lastMessage) }}</span>
            <!-- 状态标签必须带文字：只靠颜色会被读成"系统在给我亮红牌" -->
            <span v-if="statusMeta(conv)" class="fpim-chip" :class="statusMeta(conv).cls">
              {{ statusMeta(conv).label }}
            </span>
            <span v-if="mentionedMe(conv)" class="fpim-chip is-at">@我</span>
            <em v-if="conv.muted" class="fpim-conv-flag" title="消息免打扰">🔕</em>
            <span v-if="conv.unreadCount" class="fpim-badge">{{ conv.unreadCount > 99 ? '99+' : conv.unreadCount }}</span>
          </div>
        </div>
      </div>
      </template>
    </div>

    <!-- 会话备注（自研补位：仅自己可见的本地显示名） -->
    <el-dialog v-model="remarkVisible" title="会话备注" width="420px" append-to-body destroy-on-close>
      <input
        v-model="remarkText"
        placeholder="备注名（仅自己可见，留空即清除）"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none"
      />
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="remarkVisible = false">取消</button>
          <button class="fpim-btn prim" @click="saveRemark">保存</button>
        </div>
      </template>
    </el-dialog>

    <!-- 会话右键菜单（对标飞书：置顶/免打扰/清空） -->
    <div
      v-if="menu.visible"
      class="fpim-ctxmenu"
      :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
      @click.stop
    >
      <button class="fpim-ctxitem" @click="togglePin">
        {{ menu.conv?.pinned ? "取消置顶" : "置顶会话" }}
      </button>
      <button class="fpim-ctxitem" @click="markUnread">标为未读</button>
      <button class="fpim-ctxitem" @click="openRemark">会话备注</button>
      <button class="fpim-ctxitem" @click="toggleMute">
        {{ menu.conv?.muted ? "允许消息通知" : "消息免打扰" }}
      </button>
      <button class="fpim-ctxitem is-danger" @click="clearHistory">清空聊天记录</button>
    </div>
  </aside>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { avatarColor, avatarText, issueStatusMeta, previewOf, shortTime } from "../../services/im/format.js";
import { useAuthStore } from "../../stores/auth.js";
import { useDirectoryStore } from "../../stores/directory.js";
import { useImStore } from "../../stores/im.js";

defineEmits(["compose"]);

const store = useImStore();
const auth = useAuthStore();
const directory = useDirectoryStore();
const keyword = ref("");

const searchMode = computed(() => !!keyword.value.trim());

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  // 置顶区在前（服务端已排好序，这里保序过滤即可）
  if (!kw) return store.conversations;
  return store.conversations.filter((c) =>
    `${displayName(c)} ${c.lastMessage?.content?.text || ""}`.toLowerCase().includes(kw));
});

// ── 全局搜索：联系人 + 跨会话消息 ──
const msgResults = ref([]);
let searchTimer = null;

const contactResults = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return [];
  return directory.people
    .filter((p) => p.id !== auth.userId && p.active !== false)
    .filter((p) => `${p.name} ${p.department || ""} ${p.role || ""}`.toLowerCase().includes(kw))
    .slice(0, 5);
});

watch(keyword, (kw) => {
  clearTimeout(searchTimer);
  const key = kw.trim();
  if (!key) {
    msgResults.value = [];
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      msgResults.value = (await store.searchMessagesGlobal(key)).slice(0, 10);
    } catch {
      msgResults.value = [];
    }
  }, 300);
});

function convTitleOf(cid) {
  const conv = store.conversations.find((c) => c.id === cid);
  return conv ? displayName(conv) : "会话";
}

async function startChat(person) {
  try {
    await store.openWith(person.id);
    keyword.value = "";
    msgResults.value = [];
  } catch (err) {
    ElMessage.error(err.message || "发起会话失败");
  }
}

async function jumpToMsg(msg) {
  try {
    await store.selectConversation(msg.conversationId);
    await store.jumpToMessage(msg);
    keyword.value = "";
    msgResults.value = [];
  } catch (err) {
    ElMessage.error(err.message || "跳转失败");
  }
}

/** 会话显示名：备注（仅自己可见，localStorage）> 群名/对方名 */
function displayName(conv) {
  return remarks.value[conv.id] || conv.title || conv.peer?.name || "会话";
}

/** 最后一条消息是否 @ 了我 */
function mentionedMe(conv) {
  return (conv.lastMessage?.content?.mentions || []).some((m) => m.id === auth.userId);
}

/** 会话的第二行状态标签：仅当会话挂着一个"还在进行"的问题时才显示 */
function statusMeta(conv) {
  if (!conv.issueId) return null;
  const issue = store.issues.find((i) => i.id === conv.issueId);
  if (!issue) return null;
  return issueStatusMeta(issue.status);
}

// ── 会话备注（自研补位，本地存储仅自己可见）──
const REMARK_KEY = "fpim.convRemarks";
const remarks = ref(JSON.parse(localStorage.getItem(REMARK_KEY) || "{}"));
const remarkVisible = ref(false);
const remarkText = ref("");

function openRemark() {
  remarkText.value = remarks.value[menu.conv?.id] || "";
  remarkVisible.value = true;
}

function saveRemark() {
  const cid = menu.conv?.id;
  if (!cid) return;
  const next = { ...remarks.value };
  const text = remarkText.value.trim();
  if (text) next[cid] = text;
  else delete next[cid];
  remarks.value = next;
  localStorage.setItem(REMARK_KEY, JSON.stringify(next));
  remarkVisible.value = false;
}

async function markUnread() {
  closeMenu();
  try {
    if (menu.conv?.id !== store.activeId) await store.selectConversation(menu.conv.id);
    await store.markUnread();
    await store.loadConversations();
    ElMessage.success("已标为未读");
  } catch (err) {
    ElMessage.error(err.message || "操作失败");
  }
}

// ── 右键菜单 ──
const menu = reactive({ visible: false, x: 0, y: 0, conv: null });

function openMenu(event, conv) {
  menu.conv = conv;
  menu.x = Math.min(event.clientX, window.innerWidth - 160);
  menu.y = Math.min(event.clientY, window.innerHeight - 120);
  menu.visible = true;
}

function closeMenu() {
  menu.visible = false;
}

onMounted(() => window.addEventListener("click", closeMenu));
onUnmounted(() => window.removeEventListener("click", closeMenu));

async function togglePin() {
  try {
    const conv = menu.conv;
    await store.setPrefs({ pinned: !conv.pinned });
    await store.loadConversations();
  } catch (err) {
    ElMessage.error(err.message || "操作失败");
  }
  closeMenu();
}

async function toggleMute() {
  try {
    const conv = menu.conv;
    await store.setPrefs({ muted: !conv.muted });
    await store.loadConversations();
  } catch (err) {
    ElMessage.error(err.message || "操作失败");
  }
  closeMenu();
}

async function clearHistory() {
  closeMenu();
  try {
    await ElMessageBox.confirm(
      "清空后本会话的消息记录将不可见（仅影响你自己，留痕证据保留）。确定清空？",
      "清空聊天记录",
      { confirmButtonText: "清空", cancelButtonText: "取消", type: "warning" },
    );
    if (menu.conv?.id !== store.activeId) await store.selectConversation(menu.conv.id);
    await store.clearHistory();
    ElMessage.success("已清空本会话的聊天记录");
  } catch {
    /* 用户取消 */
  }
}
</script>

<style scoped>
.fpim-conv-flag {
  font-style: normal;
  font-size: 11px;
  margin-right: 2px;
}
.fpim-search-group {
  padding: 4px 0 8px;
}
.fpim-search-label {
  padding: 6px 12px 4px;
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-search-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  cursor: pointer;
}
.fpim-search-row:hover {
  background: var(--im-hover);
}
.fpim-ctxmenu {
  position: fixed;
  z-index: 3000;
  min-width: 148px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  padding: 4px;
  display: flex;
  flex-direction: column;
}
.fpim-ctxitem {
  border: none;
  background: none;
  text-align: left;
  padding: 7px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--im-text-1);
  border-radius: 4px;
  cursor: pointer;
}
.fpim-ctxitem:hover {
  background: var(--im-hover);
}
.fpim-ctxitem.is-danger {
  color: var(--im-danger);
}
</style>
