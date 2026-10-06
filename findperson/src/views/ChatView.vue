<template>
  <div class="fpim">
    <ConversationList @compose="createGroupVisible = true" />

    <!-- ── 会话区（支持拖拽文件进窗口即发送）── -->
    <section class="fpim-main" @dragover.prevent @drop.prevent="onDrop">
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
            class="fpim-btn ghost"
            title="搜索本会话的消息记录"
            @click="openSearch"
          >搜索</button>
          <button
            class="fpim-btn ghost"
            title="多选消息（合并转发/逐条转发）"
            @click="messageListRef?.toggleSelectMode()"
          >多选</button>
          <el-dropdown trigger="click" @command="onConvCommand">
            <button class="fpim-btn ghost" title="会话设置">···</button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="pin">
                  {{ store.active?.pinned ? "取消置顶" : "置顶会话" }}
                </el-dropdown-item>
                <el-dropdown-item command="mute">
                  {{ store.active?.muted ? "允许消息通知" : "消息免打扰" }}
                </el-dropdown-item>
                <el-dropdown-item command="search">查找聊天记录</el-dropdown-item>
                <el-dropdown-item
                  v-if="store.active?.type === 'direct'"
                  command="delegation"
                >代理设置</el-dropdown-item>
                <template v-if="store.active?.type === 'group'">
                  <el-dropdown-item command="rename" divided>修改群名</el-dropdown-item>
                  <el-dropdown-item command="announcement">群公告</el-dropdown-item>
                  <el-dropdown-item command="members">成员管理</el-dropdown-item>
                  <el-dropdown-item command="speak">发言权限</el-dropdown-item>
                </template>
                <el-dropdown-item command="clear" :divided="store.active?.type !== 'group'">
                  清空聊天记录
                </el-dropdown-item>
                <el-dropdown-item
                  v-if="store.active?.type === 'group'"
                  command="leave"
                  divided
                >退出群聊</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button
            v-if="store.active.type === 'group'"
            class="fpim-btn"
            style="margin-left: 10px"
            @click="inviteVisible = true"
          >邀请成员</button>
          <button
            class="fpim-btn ghost"
            :class="{ prim: sideVisible && sideTab === 'issue' }"
            title="问题详情面板"
            @click="toggleSide('issue')"
          >问题详情</button>
          <button
            class="fpim-btn ghost"
            :class="{ prim: sideVisible && sideTab === 'agent' }"
            title="AI 助手面板（Agent 交互）"
            @click="toggleSide('agent')"
          >AI 助手</button>
        </header>

        <div v-if="store.active?.pinnedMessage" class="fpim-pinbar">
          <span class="fpim-pinbar-tag">📌 置顶</span>
          <span class="fpim-pinbar-text">
            {{ store.active.pinnedMessage.content?.text || store.active.pinnedMessage.content?.name || "[附件]" }}
          </span>
          <button class="fpim-btn ghost" @click="jumpToPinned">查看</button>
          <button class="fpim-iconbtn" title="取消置顶" @click="unpin">✕</button>
        </div>

        <MessageList ref="messageListRef" @resolve="onResolve" @focus-issue="sideVisible = true" />
        <MessageComposer />
      </template>

      <div v-else class="fpim-empty" style="margin: auto">
        <div style="font-size: 15px; color: var(--im-text-2); margin-bottom: 6px">
          选择一个会话开始沟通
        </div>
        <div>去「通讯录」找人发起单聊，或点左上角 ＋ 创建群聊</div>
      </div>
    </section>

    <!-- ── 右侧面板：问题详情 / AI 助手（二期 agent-panel）── -->
    <IssueSidePanel v-if="store.active && sideVisible && sideTab === 'issue'" />
    <AgentPanel
      v-else-if="store.active && sideVisible && sideTab === 'agent'"
      :conversation-id="store.activeId"
    />

    <!-- ── 私聊代理设置（二期 R2）── -->
    <el-dialog v-model="delegationVisible" title="私聊代理（你的 Agent 代处理）" width="460px" append-to-body destroy-on-close>
      <label style="display: flex; gap: 8px; align-items: flex-start; margin-bottom: 12px; cursor: pointer">
        <input type="radio" value="off" v-model="delegationMode" />
        <span><strong>关闭</strong><br /><span style="font-size: 12px; color: var(--im-text-3)">不代理，一切自己来</span></span>
      </label>
      <label style="display: flex; gap: 8px; align-items: flex-start; margin-bottom: 12px; cursor: pointer">
        <input type="radio" value="draft" v-model="delegationMode" />
        <span><strong>仅起草</strong><br /><span style="font-size: 12px; color: var(--im-text-3)">Agent 想好回复发到你的小管家，由你确认后手动回复</span></span>
      </label>
      <label style="display: flex; gap: 8px; align-items: flex-start; margin-bottom: 12px; cursor: pointer">
        <input type="radio" value="auto" v-model="delegationMode" />
        <span><strong>自动处理</strong><br /><span style="font-size: 12px; color: var(--im-text-3)">你未读期间，Agent 基于你的知识库自主代答（标注「Agent 代处理」）；覆盖不了就安静交接给你，不说废话</span></span>
      </label>
      <p style="font-size: 12px; color: var(--im-text-3); margin: 0">
        你读到消息或亲自回复后，代理立即停止；再有新消息未读时才会继续。
      </p>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="delegationVisible = false">取消</button>
          <button class="fpim-btn prim" @click="saveDelegation">保存</button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 群管理：改名 / 群公告 / 成员管理 ── -->
    <el-dialog v-model="renameVisible" title="修改群名" width="420px" append-to-body destroy-on-close>
      <input
        v-model="renameTitle"
        placeholder="群名称"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none"
      />
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="renameVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="!renameTitle.trim()" @click="saveRename">保存</button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="announcementVisible" title="群公告" width="480px" append-to-body destroy-on-close>
      <textarea
        v-model="announcementText"
        rows="5"
        :readonly="!isGroupOwner"
        :placeholder="isGroupOwner ? '群公告（全员可见，修改后在群里留痕）' : '暂无群公告'"
        style="width: 100%; box-sizing: border-box; padding: 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-family: inherit; font-size: 13px; line-height: 1.7; resize: vertical"
      ></textarea>
      <p v-if="!isGroupOwner" style="font-size: 12px; color: var(--im-text-3); margin: 8px 0 0">
        只有群主可以编辑群公告。
      </p>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="announcementVisible = false">关闭</button>
          <button v-if="isGroupOwner" class="fpim-btn prim" @click="saveAnnouncement">保存</button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="speakVisible" title="发言权限" width="420px" append-to-body destroy-on-close>
      <label style="display: flex; gap: 8px; align-items: center; margin-bottom: 10px; cursor: pointer">
        <input type="radio" value="all" v-model="speakPermission" />
        <span>所有成员可发言</span>
      </label>
      <label style="display: flex; gap: 8px; align-items: center; cursor: pointer">
        <input type="radio" value="owner" v-model="speakPermission" />
        <span>仅群主可发言（其他成员进入只读）</span>
      </label>
      <p v-if="!isGroupOwner" style="font-size: 12px; color: var(--im-text-3); margin: 10px 0 0">
        只有群主可以修改发言权限。
      </p>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="speakVisible = false">关闭</button>
          <button v-if="isGroupOwner" class="fpim-btn prim" @click="saveSpeakPermission">保存</button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="membersVisible" title="成员管理" width="480px" append-to-body destroy-on-close>
      <div style="max-height: 340px; overflow-y: auto">
        <div v-for="m in store.active?.members || []" :key="m.id" class="fpim-conv">
          <div class="fpim-avatar sm" :style="{ background: avatarColor(m.id) }">{{ avatarText(m.name) }}</div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1">
              <span class="fpim-conv-name">{{ m.name }}</span>
              <span v-if="m.id === store.active?.ownerId" class="fpim-chip">群主</span>
            </div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ m.department || "" }}</span>
            </div>
          </div>
          <button
            v-if="isGroupOwner && m.id !== auth.userId && !m.isAgent"
            class="fpim-btn ghost"
            @click="transferTo(m.id)"
          >转让群主</button>
          <button
            v-if="isGroupOwner && m.id !== auth.userId && !m.isAgent"
            class="fpim-btn ghost"
            @click="kickMember(m.id)"
          >移出</button>
          <span v-if="m.isAgent" class="fpim-chip">智能服务</span>
        </div>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="membersVisible = false">关闭</button>
          <button class="fpim-btn" style="color: var(--im-danger)" @click="leaveGroup">退出群聊</button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 创建群组（「+」菜单入口；发起单聊走「通讯录」）── -->
    <el-dialog v-model="createGroupVisible" title="创建群组" width="520px" append-to-body destroy-on-close class="cg-dialog">
      <div class="cg-body">
        <div class="cg-field">
          <label class="cg-label">群名称</label>
          <input v-model="groupTitle" class="cg-input" placeholder="例如：报销权限问题会诊" />
        </div>

        <div class="cg-field">
          <label class="cg-label">群成员 <span class="cg-label-sub">已选 {{ selectedMembers.length }} 人</span></label>
          <div v-if="selectedMembers.length" class="cg-selected">
            <span v-for="id in selectedMembers" :key="id" class="cg-chip">
              {{ nameOfMember(id) }}
              <button type="button" title="移除" @click="unselect(id)">✕</button>
            </span>
          </div>
          <input v-model="memberKeyword" class="cg-input" placeholder="搜索成员" />
          <div class="cg-list">
            <button
              v-for="p in memberResults"
              :key="p.id"
              type="button"
              class="cg-row"
              :class="{ 'is-on': selectedMembers.includes(p.id) }"
              @click="toggleMember(p.id)"
            >
              <div class="fpim-avatar sm" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
              <div class="cg-row-main">
                <span class="cg-row-name">{{ p.name }}</span>
                <span class="cg-row-dept">{{ [p.department, p.role].filter(Boolean).join(" · ") }}</span>
              </div>
              <span class="cg-check">
                <svg v-if="selectedMembers.includes(p.id)" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8"/></svg>
              </span>
            </button>
            <div v-if="!memberResults.length" class="fpim-empty">没有匹配的成员</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="cg-foot">
          <button class="fpim-btn" @click="createGroupVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="!groupTitle.trim() || !selectedMembers.length" @click="doCreateGroup">
            创建（{{ selectedMembers.length + 1 }} 人）
          </button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 会话内消息搜索（一期 pg ILIKE；点击结果跳转到该消息附近）── -->
    <el-dialog v-model="searchVisible" title="搜索聊天记录" width="560px" append-to-body destroy-on-close>
      <input
        v-model="searchKeyword"
        placeholder="搜索本会话的正文 / 文件名"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 10px"
        @input="onSearchInput"
      />
      <div style="max-height: 380px; overflow-y: auto">
        <div v-if="searching" class="fpim-empty">搜索中…</div>
        <div v-else-if="!searchResults.length" class="fpim-empty">
          {{ searchKeyword.trim() ? "没有匹配的消息" : "输入关键词开始搜索" }}
        </div>
        <div
          v-for="m in searchResults"
          :key="m.id"
          class="fpim-conv"
          style="cursor: pointer"
          @click="jumpTo(m)"
        >
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1">
              <span class="fpim-conv-name">{{ m.senderId === auth.userId ? "我" : m.senderId }}</span>
              <span class="fpim-conv-time">{{ shortTime(m.createdAt) }}</span>
            </div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ m.content?.text || m.content?.name || "[附件]" }}</span>
            </div>
          </div>
        </div>
      </div>
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
import { ElMessage, ElMessageBox } from "element-plus";

import { avatarColor, avatarText, shortTime } from "../services/im/format.js";
import { useAuthStore } from "../stores/auth.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useImStore } from "../stores/im.js";
import AgentPanel from "../components/im/AgentPanel.vue";
import ConversationList from "../components/im/ConversationList.vue";
import IssueSidePanel from "../components/im/IssueSidePanel.vue";
import MessageComposer from "../components/im/MessageComposer.vue";
import MessageList from "../components/im/MessageList.vue";

const store = useImStore();
const directory = useDirectoryStore();
const auth = useAuthStore();

const sideVisible = ref(true);
const sideTab = ref("issue");   // issue=问题详情 | agent=AI 助手（二期）
const messageListRef = ref(null);
const createGroupVisible = ref(false);
const inviteVisible = ref(false);
const memberKeyword = ref("");
const groupTitle = ref("");
const selectedMembers = ref([]);

// ── 会话内搜索 ──
const searchVisible = ref(false);
const searchKeyword = ref("");
const searchResults = ref([]);
const searching = ref(false);
let searchTimer = null;

function openSearch() {
  searchVisible.value = true;
  searchKeyword.value = "";
  searchResults.value = [];
}

function onSearchInput() {
  clearTimeout(searchTimer);
  const kw = searchKeyword.value.trim();
  if (!kw) {
    searchResults.value = [];
    return;
  }
  searching.value = true;
  searchTimer = setTimeout(async () => {
    try {
      searchResults.value = await store.searchMessages(kw);
    } catch (err) {
      ElMessage.error(err.message || "搜索失败");
    } finally {
      searching.value = false;
    }
  }, 300);
}

async function jumpTo(msg) {
  try {
    await store.jumpToMessage(msg);
    searchVisible.value = false;
    sideVisible.value = true;
  } catch (err) {
    ElMessage.error(err.message || "跳转失败");
  }
}

// ── 私聊代理（二期 R2）──
const delegationVisible = ref(false);
const delegationMode = ref("off");

async function openDelegation() {
  try {
    const item = await store.loadDelegation();
    delegationMode.value = item?.mode || "off";
    delegationVisible.value = true;
  } catch (err) {
    ElMessage.error(err.message || "读取代理设置失败");
  }
}

async function saveDelegation() {
  try {
    await store.setDelegationMode(delegationMode.value);
    delegationVisible.value = false;
    ElMessage.success({
      off: "已关闭代理",
      draft: "已开启：仅起草（建议发到你的小管家）",
      draft2: "",
      auto: "已开启：未读期间 Agent 自动处理",
    }[delegationMode.value] || "已保存");
  } catch (err) {
    ElMessage.error(err.message || "保存失败");
  }
}

// ── 置顶横幅 ──
async function jumpToPinned() {
  const pinned = store.active?.pinnedMessage;
  if (!pinned) return;
  try {
    await store.jumpToMessage(pinned);
    sideVisible.value = true;
  } catch (err) {
    ElMessage.error(err.message || "跳转失败");
  }
}

async function unpin() {
  try {
    await store.setPinnedMessage(null);
  } catch (err) {
    ElMessage.error(err.message || "取消置顶失败");
  }
}

// ── 发言权限 ──
const speakVisible = ref(false);
const speakPermission = ref("all");

function openSpeak() {
  speakPermission.value = store.active?.speakPermission || "all";
  speakVisible.value = true;
}

async function saveSpeakPermission() {
  try {
    await store.updateGroupInfo({ speakPermission: speakPermission.value });
    speakVisible.value = false;
    ElMessage.success("发言权限已更新");
  } catch (err) {
    ElMessage.error(err.message || "保存失败");
  }
}

async function transferTo(memberId) {
  try {
    await ElMessageBox.confirm("确定将群主转让给该成员？转让后你将失去群管理权限。", "转让群主", {
      confirmButtonText: "转让", cancelButtonText: "取消", type: "warning",
    });
    await store.transferOwner(memberId);
    membersVisible.value = false;
    ElMessage.success("群主已转让");
  } catch (err) {
    if (err !== "cancel" && err !== "close") ElMessage.error(err.message || "操作失败");
  }
}

// ── 群管理 ──
const renameVisible = ref(false);
const renameTitle = ref("");
const announcementVisible = ref(false);
const announcementText = ref("");
const membersVisible = ref(false);
const isGroupOwner = computed(() => store.active?.ownerId === auth.userId);

function openRename() {
  renameTitle.value = store.active?.title || "";
  renameVisible.value = true;
}

async function saveRename() {
  try {
    await store.updateGroupInfo({ title: renameTitle.value.trim() });
    renameVisible.value = false;
    ElMessage.success("群名已更新");
  } catch (err) {
    ElMessage.error(err.message || "保存失败");
  }
}

function openAnnouncement() {
  announcementText.value = store.active?.announcement || "";
  announcementVisible.value = true;
}

async function saveAnnouncement() {
  try {
    await store.updateGroupInfo({ announcement: announcementText.value });
    announcementVisible.value = false;
    ElMessage.success("群公告已更新");
  } catch (err) {
    ElMessage.error(err.message || "保存失败");
  }
}

async function kickMember(memberId) {
  try {
    await ElMessageBox.confirm("确定将该成员移出群聊？", "移出成员", {
      confirmButtonText: "移出", cancelButtonText: "取消", type: "warning",
    });
    await store.removeMember(memberId);
    ElMessage.success("已移出");
  } catch (err) {
    if (err !== "cancel" && err !== "close") ElMessage.error(err.message || "操作失败");
  }
}

async function leaveGroup() {
  try {
    await ElMessageBox.confirm(
      "退出后将不再接收本群消息（历史留痕保留）。确定退出？",
      "退出群聊",
      { confirmButtonText: "退出", cancelButtonText: "取消", type: "warning" },
    );
    await store.removeMember(auth.userId);
    membersVisible.value = false;
    ElMessage.success("已退出群聊");
  } catch (err) {
    if (err !== "cancel" && err !== "close") ElMessage.error(err.message || "操作失败");
  }
}

// ── 会话设置（置顶/免打扰/清空）──
async function onConvCommand(command) {
  try {
    if (command === "pin") {
      await store.setPrefs({ pinned: !store.active?.pinned });
      await store.loadConversations();
    } else if (command === "mute") {
      await store.setPrefs({ muted: !store.active?.muted });
      await store.loadConversations();
    } else if (command === "search") {
      openSearch();
    } else if (command === "delegation") {
      await openDelegation();
    } else if (command === "rename") {
      openRename();
    } else if (command === "announcement") {
      openAnnouncement();
    } else if (command === "members") {
      membersVisible.value = true;
    } else if (command === "speak") {
      openSpeak();
    } else if (command === "leave") {
      await leaveGroup();
    } else if (command === "clear") {
      await ElMessageBox.confirm(
        "清空后本会话的消息记录将不可见（仅影响你自己，留痕证据保留）。确定清空？",
        "清空聊天记录",
        { confirmButtonText: "清空", cancelButtonText: "取消", type: "warning" },
      );
      await store.clearHistory();
      ElMessage.success("已清空本会话的聊天记录");
    }
  } catch (err) {
    if (err !== "cancel" && err !== "close") ElMessage.error(err.message || "操作失败");
  }
}

// ── 拖拽发送 ──
async function onDrop(event) {
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length || !store.activeId) return;
  for (const file of files) {
    try {
      await store.sendFile(file);
    } catch (err) {
      ElMessage.error(err.message || `「${file.name}」上传失败`);
    }
  }
}

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

const memberResults = computed(() => match(candidates.value, memberKeyword.value));

const invitable = (p) => !(store.active?.members || []).some((m) => m.id === p.id);

const nameOfMember = (id) => directory.getPerson(id)?.name || id;
function unselect(id) {
  selectedMembers.value = selectedMembers.value.filter((x) => x !== id);
}
function toggleMember(id) {
  if (selectedMembers.value.includes(id)) unselect(id);
  else selectedMembers.value.push(id);
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
  sideTab.value = "issue";
  sideVisible.value = true;
  ElMessage.info("请在右侧「问题详情」里填写解决结论");
}

/** 头部「＋ 立项」：先展开问题面板，再唤起立项对话框（IssueSidePanel 监听同一事件） */
function createIssue() {
  sideTab.value = "issue";   // 立项对话框挂在 IssueSidePanel 上
  sideVisible.value = true;
  window.dispatchEvent(new CustomEvent("fpim:create-issue"));
}

function toggleSide(tab) {
  if (sideVisible.value && sideTab.value === tab) sideVisible.value = false;
  else {
    sideTab.value = tab;
    sideVisible.value = true;
  }
}

function onCreated() {
  // 名片/问答侧发起会话后，直接跳到这里；会话已由 store.openWith 建好并选中。
  createGroupVisible.value = false;
  inviteVisible.value = false;
}

onMounted(() => {
  store.init();
  window.addEventListener("fpim:start-conversation", onCreated);
});
onUnmounted(() => window.removeEventListener("fpim:start-conversation", onCreated));

watch(() => auth.userId, () => store.teardown(), { flush: "post" });
</script>

<style scoped>
.fpim-pinbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: var(--im-bg-side);
  border-bottom: 0.5px solid var(--im-line);
}
.fpim-pinbar-tag {
  font-size: 12px;
  color: var(--im-text-2);
  flex: 0 0 auto;
}
.fpim-pinbar-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--im-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>


<style scoped>
/* 创建群组弹窗（飞书式） */
.cg-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.cg-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cg-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--im-text-1);
}
.cg-label-sub {
  margin-left: 8px;
  font-weight: 400;
  color: var(--im-text-3);
  font-size: 12px;
}
.cg-input {
  width: 100%;
  box-sizing: border-box;
  height: 36px;
  padding: 0 12px;
  border: 0.5px solid var(--im-line-strong);
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  color: var(--im-text-1);
  outline: none;
  background: #fff;
}
.cg-input::placeholder {
  color: var(--im-text-4);
}
.cg-input:focus {
  border-color: var(--im-primary);
}
.cg-selected {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cg-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px 3px 10px;
  background: var(--im-primary-weak);
  color: var(--im-primary);
  border-radius: 6px;
  font-size: 12px;
}
.cg-chip button {
  border: none;
  background: none;
  color: inherit;
  font-size: 11px;
  line-height: 1;
  padding: 2px;
  cursor: pointer;
  opacity: 0.7;
}
.cg-chip button:hover {
  opacity: 1;
}
.cg-list {
  max-height: 280px;
  overflow-y: auto;
}
.cg-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  background: none;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  font: inherit;
}
.cg-row:hover {
  background: var(--im-hover);
}
.cg-row.is-on {
  background: var(--im-primary-weak);
}
.cg-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.cg-row-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--im-text-1);
}
.cg-row-dept {
  font-size: 12px;
  color: var(--im-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cg-check {
  flex: 0 0 auto;
  display: inline-flex;
  color: var(--im-primary);
}
.cg-row:not(.is-on) .cg-check {
  color: var(--im-text-4);
}
.cg-foot {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
