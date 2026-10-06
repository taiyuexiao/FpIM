<template>
  <div ref="scroller" class="fpim-msg-scroll" @scroll="onScroll">
    <div v-if="store.hasMore[store.activeId]" class="fpim-msg-sep" style="cursor: pointer" @click="store.loadMore(store.activeId)">
      {{ store.loadingMessages ? "加载中…" : "查看更早的消息" }}
    </div>

    <template v-for="(msg, i) in messages" :key="msg.id || msg.clientMsgId">
      <div v-if="needTimeDivider(messages[i - 1], msg)" class="fpim-msg-sep">
        {{ fullTime(msg.createdAt) }}
      </div>
      <div v-if="isFirstUnread(msg, i)" class="fpim-msg-sep is-unread">以下是未读消息</div>

      <!-- 系统消息 / 撤回提示：居中灰底，不占气泡 -->
      <div v-if="isSystem(msg) || msg.revoked" class="fpim-sys">
        <span>
          {{ msg.revoked
            ? `${isMine(msg) ? "你" : nameOf(msg.senderId)}撤回了一条消息`
            : msg.content.text }}
        </span>
      </div>

      <div
        v-else
        class="fpim-msg"
        :class="{ mine: isMine(msg), 'is-pending': msg.pending,
                  'is-selected': selectedIds.includes(msg.id), 'is-selectable': selectMode }"
        @click="onRowClick(msg, $event)"
      >
        <div class="fpim-avatar sm" :style="{ background: avatarColor(msg.senderId) }">
          {{ avatarText(nameOf(msg.senderId)) }}
        </div>

        <div class="fpim-msg-body">
          <div class="fpim-msg-meta">
            <span>{{ isMine(msg) ? "我" : nameOf(msg.senderId) }}</span>
            <span v-if="msg.content?.automation" class="fpim-auto-badge"
                  title="由本人的 Agent 代为处理">Agent 代处理</span>
            <span>{{ shortTime(msg.createdAt) }}</span>
            <span v-if="msg.content?.editedAt">· 已编辑</span>
            <span v-if="msg.status === 'unknown'" class="fpim-unknown">
              状态待核实
              <button class="fpim-msg-act" @click.stop="store.resend(msg)">重发</button>
            </span>
            <span
              v-if="readMark(msg)"
              class="fpim-readmark"
              :class="{ 'is-clickable': isGroup }"
              :title="isGroup ? '查看已读名单' : ''"
              @click.stop="isGroup && openReadList(msg)"
            >{{ readMark(msg) }}</span>
            <span v-if="msg.pending">· 发送中</span>
            <span class="fpim-msg-actions">
              <el-tooltip content="点赞" placement="top">
                <button class="fpim-msg-icon" @click.stop="store.toggleReaction(msg.id, '👍')" v-html="ICON_LIKE"></button>
              </el-tooltip>
              <el-tooltip content="表情回应" placement="top">
                <button class="fpim-msg-icon" @click.stop="togglePicker(msg)" v-html="ICON_EMOJI"></button>
              </el-tooltip>
              <el-tooltip content="回复" placement="top">
                <button class="fpim-msg-icon" @click.stop="onQuote(msg)" v-html="ICON_REPLY"></button>
              </el-tooltip>
              <el-tooltip content="转发" placement="top">
                <button class="fpim-msg-icon" @click.stop="openForward(msg)" v-html="ICON_FORWARD"></button>
              </el-tooltip>
              <el-dropdown trigger="click" @command="(cmd) => onMore(cmd, msg)">
                <button class="fpim-msg-icon" title="更多" @click.stop v-html="ICON_MORE"></button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="msg.content?.text" command="copy">复制</el-dropdown-item>
                    <el-dropdown-item v-if="canEdit(msg)" command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item v-if="!msg.pending && !msg.revoked" command="pin">置顶</el-dropdown-item>
                    <el-dropdown-item v-if="canRevoke(msg)" command="revoke" divided>撤回</el-dropdown-item>
                    <el-dropdown-item v-if="!msg.pending" command="delete">删除（仅自己可见）</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </div>

          <!-- 引用块：展示被引用消息的摘要，点击可定位原消息 -->
          <div
            v-if="quoteOf(msg)"
            class="fpim-quote-ref"
            :class="{ 'is-missing': quoteOf(msg).missing }"
            :title="quoteOf(msg).missing ? '' : '点击定位原消息'"
            @click.stop="jumpToQuote(msg)"
          >
            <span class="fpim-quote-ref-name">{{ quoteOf(msg).name }}</span>
            <span class="fpim-quote-ref-text">{{ quoteOf(msg).text }}</span>
          </div>

          <!-- 转发来源标注（任意类型通用，独立于内容链） -->
          <div v-if="msg.content?.forwardFrom" class="fpim-forward-src">
            来自「{{ msg.content.forwardFrom.conversationTitle || "会话" }}」{{ msg.content.forwardFrom.senderName }} 的转发
          </div>

          <!-- 问题卡：会话里承载闭环的核心消息类型 -->
          <div v-if="msg.msgType === 'issue_card'" class="fpim-issuecard">
            <h4>{{ msg.content.summary || msg.content.question }}</h4>
            <div class="meta">
              <span v-if="msg.content.assigneeName">责任人：{{ msg.content.assigneeName }}</span>
              <span v-if="msg.content.askerName">提问人：{{ msg.content.askerName }}</span>
              <span>状态：{{ issueStatusMeta(msg.content.status).label }}</span>
            </div>
            <div v-if="!isMine(msg) && msg.content.status !== 'resolved'" class="actions">
              <button class="fpim-btn prim" @click="$emit('resolve', msg)">标记已解决</button>
              <button class="fpim-btn" @click="$emit('focus-issue', msg.issueId)">查看过程</button>
            </div>
          </div>

          <!-- 图片（点击放大查看） -->
          <div
            v-else-if="msg.msgType === 'image'"
            class="fpim-imgwrap"
            @click.stop="previewImage(msg)"
          >
            <img class="fpim-img" :src="fileUrl(msg)" :alt="msg.content.name || '图片'" />
          </div>

          <!-- 文件 -->
          <a
            v-else-if="msg.msgType === 'file'"
            class="fpim-attach" :href="fileUrl(msg)" target="_blank" rel="noopener"
          >
            <span class="ext">{{ fileExt(msg.content.name) }}</span>
            <span>
              <span class="nm">{{ msg.content.name }}</span>
              <span class="sz">{{ msg.content.sizeHuman || humanSize(msg.content.size) }}</span>
            </span>
          </a>

          <!-- 合并转发卡片：点击回放全部消息 -->
          <div
            v-else-if="msg.msgType === 'composite'"
            class="fpim-composite"
            @click.stop="selectMode ? onRowClick(msg, $event) : openComposite(msg)"
          >
            <div class="fpim-composite-head">
              {{ msg.content.note ? `${msg.content.note} · ` : "" }}合并转发的 {{ msg.content.count }} 条消息
            </div>
            <div class="fpim-composite-preview">
              {{ (msg.content.items || []).slice(0, 2).map((it) => `${it.senderName}：${it.text}`).join("；") }}
            </div>
          </div>

          <!-- 处理模板卡（二期：问题+解决套路+责任人） -->
          <div v-else-if="msg.msgType === 'template'" class="fpim-tplcard">
            <div class="fpim-tplcard-head">
              📋 {{ msg.content.title }}
              <span class="fpim-chip">处理模板</span>
            </div>
            <div class="fpim-tplcard-q">Q：{{ msg.content.question }}</div>
            <div class="fpim-tplcard-a">A：{{ msg.content.solution }}</div>
            <div class="fpim-tplcard-foot">
              责任人：{{ msg.content.ownerName || "—" }}
              <template v-if="msg.content.note"> · 附言：{{ msg.content.note }}</template>
            </div>
          </div>

          <!-- 人员名片卡（点击直达会话） -->
          <div
            v-else-if="msg.msgType === 'share_user'"
            class="fpim-usercard"
          >
            <div class="fpim-avatar" :style="{ background: avatarColor(msg.content.personId) }">
              {{ avatarText(msg.content.name) }}
            </div>
            <div class="fpim-usercard-main">
              <div class="fpim-usercard-name">{{ msg.content.name }}</div>
              <div class="fpim-usercard-meta">
                {{ [msg.content.department, msg.content.role].filter(Boolean).join(" · ") }}
              </div>
            </div>
            <button
              v-if="msg.content.personId !== auth.userId"
              class="fpim-btn prim"
              @click.stop="chatWith(msg.content.personId)"
            >发消息</button>
          </div>

          <!-- 内联编辑态（仅文本消息） -->
          <div v-else-if="editingId === msg.id" class="fpim-edit-box">
            <textarea v-model="editText" rows="2"></textarea>
            <div class="fpim-edit-actions">
              <button class="fpim-btn" @click="editingId = null">取消</button>
              <button class="fpim-btn prim" :disabled="!editText.trim()" @click="saveEdit(msg)">保存</button>
            </div>
          </div>

          <!-- 文本（@提及高亮；被 @ 的消息加淡底提示） -->
          <div v-else class="fpim-bubble" :class="{ 'is-mentioned': mentionedMe(msg) }">
            <template v-for="(seg, i) in textSegments(msg)" :key="i">
              <span v-if="seg.mention" class="fpim-mention">{{ seg.text }}</span>
              <template v-else>{{ seg.text }}</template>
            </template>
          </div>

          <!-- 表情回应聚合：对全员可见；点自己发过的即撤回 -->
          <div v-if="(msg.reactions || []).length" class="fpim-reactions">
            <button
              v-for="r in msg.reactions"
              :key="r.emoji"
              class="fpim-reaction"
              :class="{ 'is-mine': hasMyReaction(r) }"
              :title="reactionTitle(r)"
              @click="store.toggleReaction(msg.id, r.emoji)"
            >
              {{ r.emoji }}<span>{{ r.count }}</span>
            </button>
          </div>

          <!-- 表情选择器（点「表情」展开，选完即发） -->
          <div v-if="pickerFor === msg.id" class="fpim-emojipick">
            <button
              v-for="e in EMOJIS"
              :key="e"
              class="fpim-emojipick-btn"
              @click="react(msg, e)"
            >{{ e }}</button>
          </div>
        </div>
      </div>
    </template>

    <div v-if="!messages.length" class="fpim-empty">
      还没有消息。说点什么，或者把问题写清楚发过去。
    </div>

    <!-- ── 图片查看器（点击缩略图放大；点击任意处关闭）── -->
    <div v-if="previewUrl" class="fpim-imgviewer" @click="previewUrl = null">
      <img :src="previewUrl" alt="预览" @click.stop="previewUrl = null" />
      <a class="fpim-imgviewer-dl" :href="previewUrl" target="_blank" rel="noopener" @click.stop>查看原图</a>
    </div>

    <!-- ── 多选操作条 ── -->
    <div v-if="selectMode" class="fpim-select-bar">
      <span class="fpim-hint">已选 {{ selectedIds.length }} 条</span>
      <button class="fpim-btn" :disabled="!selectedIds.length" @click="openForward(null, 'combined')">合并转发</button>
      <button class="fpim-btn" :disabled="!selectedIds.length" @click="forwardEach">逐条转发</button>
      <button class="fpim-btn ghost" @click="exitSelect">取消</button>
    </div>

    <!-- ── 合并转发回放 ── -->
    <el-dialog v-model="compositeVisible" title="合并转发的消息" width="480px" append-to-body destroy-on-close>
      <div class="fpim-composite-replay">
        <div v-for="(it, idx) in compositeItems" :key="idx" class="fpim-composite-item">
          <div class="fpim-composite-item-meta">
            <span>{{ it.senderName }}</span>
            <span>{{ shortTime(it.createdAt) }}</span>
          </div>
          <div class="fpim-composite-item-text">{{ it.text }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- ── 群已读名单 ── -->
    <el-dialog v-model="readListVisible" title="消息阅读情况" width="420px" append-to-body destroy-on-close>
      <div class="fpim-readlist-group">已读（{{ readListData.read.length }}）</div>
      <div class="fpim-readlist-names">
        {{ readListData.read.map((m) => m.name).join("、") || "暂无" }}
      </div>
      <div class="fpim-readlist-group">未读（{{ readListData.unread.length }}）</div>
      <div class="fpim-readlist-names">
        {{ readListData.unread.map((m) => m.name).join("、") || "暂无" }}
      </div>
    </el-dialog>

    <!-- ── 转发对话框：选目标会话 + 可选留言 ── -->
    <el-dialog v-model="forwardVisible" title="转发消息" width="460px" append-to-body destroy-on-close>
      <input
        v-model="forwardNote"
        placeholder="留言（可选，会显示在转发内容上方）"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 10px"
      />
      <div style="max-height: 320px; overflow-y: auto">
        <label
          v-for="c in store.conversations"
          :key="c.id"
          class="fpim-conv"
          style="cursor: pointer"
        >
          <input type="radio" :value="c.id" v-model="forwardTarget" style="flex: 0 0 auto" />
          <div class="fpim-avatar sm" :style="{ background: avatarColor(c.peer?.id || c.title) }">
            {{ avatarText(c.title || c.peer?.name || "会话") }}
          </div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ c.title || c.peer?.name || "会话" }}</span></div>
          </div>
        </label>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="fpim-btn" @click="forwardVisible = false">取消</button>
          <button class="fpim-btn prim" :disabled="!forwardTarget" @click="confirmForward">
            {{ forwardMode === "combined" ? "合并发送" : "发送" }}
          </button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";

import {
  avatarColor, avatarText, fileExt, fullTime, humanSize, issueStatusMeta,
  needTimeDivider, shortTime,
} from "../../services/im/format.js";
import {
  ICON_EMOJI, ICON_FORWARD, ICON_LIKE, ICON_MORE, ICON_REPLY,
} from "./icons.js";
import { useAuthStore } from "../../stores/auth.js";
import { useImStore } from "../../stores/im.js";

defineEmits(["resolve", "focus-issue"]);

/** 头部「多选」按钮开关（ChatView 调用） */
function toggleSelectMode() {
  if (selectMode.value) exitSelect();
  else selectMode.value = true;
}
defineExpose({ toggleSelectMode });

const store = useImStore();
const auth = useAuthStore();
const scroller = ref(null);

const messages = computed(() => store.activeMessages);

const SYSTEM_TYPES = new Set(["system", "resolve_confirm", "report_card"]);
// 系统消息：后端用 sender_id="system" 发送（sender_id 列 NOT NULL，不能真空）
const isSystem = (msg) => SYSTEM_TYPES.has(msg.msgType) && (!msg.senderId || msg.senderId === "system");

function isMine(msg) {
  return msg.senderId === auth.userId || msg.senderId === "me";
}

/** 从会话成员里查姓名；查不到就回落 id，不编造 */
function nameOf(userId) {
  if (userId === "group-agent") return "群聊 Agent";
  if (userId === "system") return "小管家";
  const conv = store.active;
  const hit = conv?.members?.find((m) => m.id === userId);
  if (hit?.name) return hit.name;
  if (conv?.peer?.id === userId && conv.peer.name) return conv.peer.name;
  return userId;
}

function fileUrl(msg) {
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return `${base}${msg.content.url}`;
}

/** 引用块：从已加载消息里解析被引用消息；不在窗口内则显示占位 */
function quoteOf(msg) {
  if (!msg.replyToId) return null;
  const hit = messages.value.find((m) => m.id === msg.replyToId);
  if (!hit) return { name: "", text: "引用的消息", missing: true };
  const body = hit.content?.text || hit.content?.name || "[附件]";
  return {
    name: isMine(hit) ? "我" : nameOf(hit.senderId),
    text: body.length > 60 ? `${body.slice(0, 60)}…` : body,
    missing: false,
  };
}

/** 只有自己的、未撤回的、2 分钟内的消息可撤回（后端再校验一次） */
function canRevoke(msg) {
  if (msg.revoked || msg.pending || !msg.id || typeof msg.id !== "number") return false;
  if (!isMine(msg)) return false;
  return Date.now() - new Date(msg.createdAt).getTime() < 2 * 60 * 1000;
}

function onQuote(msg) {
  store.setQuote({ ...msg, senderName: isMine(msg) ? "我" : nameOf(msg.senderId) });
}

/** 常用表情回应（飞书首发 14 个） */
const EMOJIS = ["👍", "🎉", "❤️", "😄", "😂", "🙏", "👌", "🔥", "✅", "👀", "😢", "😮", "🤔", "💩"];
const pickerFor = ref(null);

function togglePicker(msg) {
  pickerFor.value = pickerFor.value === msg.id ? null : msg.id;
}

function react(msg, emoji) {
  store.toggleReaction(msg.id, emoji);
  pickerFor.value = null;
}

function hasMyReaction(r) {
  return (r.users || []).some((u) => u.id === auth.userId);
}

/** 文本分段：@名字 识别为提及（名字按长度倒序，避免短名吃掉长名） */
function textSegments(msg) {
  const body = msg.content?.text || "";
  const names = (msg.content?.mentions || [])
    .map((m) => m.name)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);
  if (!names.length) return [{ text: body, mention: false }];
  const segs = [{ text: body, mention: false }];
  for (const name of names) {
    for (let i = 0; i < segs.length; i += 1) {
      const seg = segs[i];
      if (seg.mention) continue;
      const parts = seg.text.split(`@${name}`);
      if (parts.length > 1) {
        const next = [];
        parts.forEach((part, idx) => {
          if (part) next.push({ text: part, mention: false });
          if (idx < parts.length - 1) next.push({ text: `@${name}`, mention: true });
        });
        segs.splice(i, 1, ...next);
        i += next.length - 1;
      }
    }
  }
  return segs.filter((seg) => seg.text);
}

function mentionedMe(msg) {
  return (msg.content?.mentions || []).some((m) => m.id === auth.userId);
}

// ── 消息编辑（24h 内 ≤20 次，仅文本）──
const editingId = ref(null);
const editText = ref("");

function canEdit(msg) {
  if (!isMine(msg) || msg.pending || msg.revoked) return false;
  if (msg.msgType !== "text" || typeof msg.id !== "number") return false;
  const age = Date.now() - new Date(msg.createdAt).getTime();
  return age < 24 * 3600 * 1000;
}

function startEdit(msg) {
  editingId.value = msg.id;
  editText.value = msg.content?.text || "";
}

async function saveEdit(msg) {
  try {
    await store.editMessage(msg.id, editText.value.trim());
    editingId.value = null;
  } catch (err) {
    window.alert(err.message || "编辑失败");
  }
}

// ── 单条 / 合并转发 ──
const forwardVisible = ref(false);
const forwardTarget = ref(null);
const forwardNote = ref("");
const forwardMsg = ref(null);
const forwardMode = ref("single");

function openForward(msg = null, mode = "single") {
  forwardMsg.value = msg;
  forwardMode.value = mode;
  forwardTarget.value = null;
  forwardNote.value = "";
  forwardVisible.value = true;
}

async function confirmForward() {
  if (!forwardTarget.value) return;
  try {
    if (forwardMode.value === "combined" || forwardMode.value === "each") {
      const ids = [...selectedIds.value];
      if (forwardMode.value === "each") {
        for (const mid of ids) await store.forwardMessage(mid, forwardTarget.value, forwardNote.value.trim());
      } else {
        await store.forwardCombined(ids, forwardTarget.value, forwardNote.value.trim());
      }
      exitSelect();
    } else {
      if (!forwardMsg.value) return;
      await store.forwardMessage(forwardMsg.value.id, forwardTarget.value, forwardNote.value.trim());
    }
    forwardVisible.value = false;
  } catch (err) {
    window.alert(err.message || "转发失败");
  }
}

function forwardEach() {
  if (!selectedIds.value.length) return;
  openForward(null, "each"); // 逐条也走选会话弹层
}

// ── 多选 ──
const selectMode = ref(false);
const selectedIds = ref([]);
let lastSelectedIndex = null;

function onRowClick(msg, event) {
  if (!selectMode.value) return;
  const list = messages.value;
  const idx = list.findIndex((m) => (m.id || m.clientMsgId) === (msg.id || msg.clientMsgId));
  if (event.shiftKey && lastSelectedIndex !== null) {
    // Shift 区间选择
    const [from, to] = [Math.min(lastSelectedIndex, idx), Math.max(lastSelectedIndex, idx)];
    for (let i = from; i <= to; i += 1) {
      const id = list[i].id;
      if (id && !selectedIds.value.includes(id)) selectedIds.value.push(id);
    }
  } else if (msg.id) {
    const at = selectedIds.value.indexOf(msg.id);
    if (at >= 0) selectedIds.value.splice(at, 1);
    else selectedIds.value.push(msg.id);
    lastSelectedIndex = idx;
  }
}

function exitSelect() {
  selectMode.value = false;
  selectedIds.value = [];
  lastSelectedIndex = null;
}

async function onHide(msg) {
  if (!window.confirm("删除这条消息？仅自己不可见，留痕证据保留。")) return;
  try {
    await store.hideMessage(msg.id);
  } catch (err) {
    window.alert(err.message || "删除失败");
  }
}

async function chatWith(personId) {
  try {
    await store.openWith(personId);
  } catch (err) {
    window.alert(err.message || "发起会话失败");
  }
}

// ── 复制 / 图片预览 / 引用跳转 ──
/** 「更多」菜单分发 */
function onMore(cmd, msg) {
  if (cmd === "copy") onCopy(msg);
  else if (cmd === "edit") startEdit(msg);
  else if (cmd === "pin") onPin(msg);
  else if (cmd === "revoke") onRevoke(msg);
  else if (cmd === "delete") onHide(msg);
}

function onCopy(msg) {
  const body = msg.content?.text || "";
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(body);
}

const previewUrl = ref(null);

function previewImage(msg) {
  previewUrl.value = fileUrl(msg);
}

async function jumpToQuote(msg) {
  const hit = messages.value.find((m) => m.id === msg.replyToId);
  if (!hit) return;
  try {
    await store.jumpToMessage(hit);
  } catch (err) {
    window.alert(err.message || "定位失败");
  }
}

// ── 未读分隔线：会话刚打开时，首条未读消息前插线 ──
const initialUnreadSeq = ref(null);
watch(() => store.activeId, () => {
  // 进入会话瞬间记下未读起点（markRead 前的 lastReadSeq）
  initialUnreadSeq.value = store.active?.lastReadSeq ?? null;
}, { immediate: true });

function isFirstUnread(msg, index) {
  const base = initialUnreadSeq.value;
  if (!base || msg.pending || isSystem(msg)) return false;
  if ((msg.seq || 0) <= base) return false;
  const prev = messages.value[index - 1];
  return !prev || (prev.seq || 0) <= base;
}

// ── 置顶消息 ──
async function onPin(msg) {
  try {
    await store.setPinnedMessage(msg.id);
  } catch (err) {
    window.alert(err.message || "置顶失败");
  }
}

// ── 合并转发回放 ──
const compositeVisible = ref(false);
const compositeItems = ref([]);

function openComposite(msg) {
  compositeItems.value = msg.content?.items || [];
  compositeVisible.value = true;
}

// ── 群已读名单 ──
const readListVisible = ref(false);
const readListData = ref({ read: [], unread: [] });

const isGroup = computed(() => store.active?.type === "group");

function openReadList(msg) {
  const members = (store.active?.members || []).filter((m) => m.id !== auth.userId);
  const read = [];
  const unread = [];
  for (const m of members) {
    ((m.lastReadSeq || 0) >= (msg.seq || 0) ? read : unread).push(m);
  }
  readListData.value = { read, unread };
  readListVisible.value = true;
}

// ── 已读回执（带文字不只用色）：单聊「已读/未读」，群聊「N 人已读」可点名单 ──
function readMark(msg) {
  const conv = store.active;
  if (!conv || !isMine(msg) || msg.pending || msg.revoked) return null;
  if (conv.type === "direct") {
    const peerId = conv.peer?.id;
    const member = (conv.members || []).find((m) => m.id === peerId);
    const peerSeq = member?.lastReadSeq ?? 0;
    return (msg.seq || 0) <= peerSeq ? "已读" : "未读";
  }
  const others = (conv.members || []).filter(
    (m) => m.id !== auth.userId && m.id !== "system" && m.id !== "group-agent");
  const readCount = others.filter((m) => (m.lastReadSeq || 0) >= (msg.seq || 0)).length;
  return readCount ? `${readCount} 人已读` : null;
}

function reactionTitle(r) {
  const names = (r.users || []).map((u) => u.name || u.id).join("、");
  return names ? `${names} 的回应` : "";
}

async function onRevoke(msg) {
  if (!window.confirm("撤回这条消息？2 分钟内可撤回。")) return;
  try {
    await store.revoke(msg.id);
  } catch {
    /* 后端拒绝时（超时/非本人）静默，toast 交由 store 后续增强 */
  }
}

/** 新消息或切换会话后滚到底部 */
async function scrollToBottom() {
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

watch(() => store.activeId, () => scrollToBottom());
watch(() => messages.value.length, (n, o) => {
  // 只在贴近底部时自动滚动，避免用户翻历史时被拽走
  const el = scroller.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 220;
  if (nearBottom || n > o) scrollToBottom();
});
watch(() => messages.value[messages.value.length - 1]?.seq, scrollToBottom);

/** 滚动到顶自动加载更早的消息 */
let loadingMore = false;
async function onScroll() {
  const el = scroller.value;
  if (!el || loadingMore) return;
  if (el.scrollTop > 60 || !store.hasMore[store.activeId]) return;
  loadingMore = true;
  const before = el.scrollHeight;
  try {
    await store.loadMore(store.activeId);
    await nextTick();
    el.scrollTop = el.scrollHeight - before;   // 维持视觉位置不跳动
  } finally {
    loadingMore = false;
  }
}
</script>

<style scoped>
.fpim-msg-actions {
  /* 绝对定位悬浮：显示/隐藏不占布局空间，杜绝消息抖动（对齐飞书附图三：
     小消息体在右侧，大消息体右上角覆盖——统一贴气泡右上外沿即可兼得） */
  position: absolute;
  top: -8px;
  right: -8px;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: 8px;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}
.fpim-msg.is-mine .fpim-msg-actions {
  right: auto;
  left: -8px;
}
.fpim-msg:hover .fpim-msg-actions {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}
.fpim-msg-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: none;
  border-radius: 6px;
  color: var(--im-text-2);
  cursor: pointer;
}
.fpim-msg-icon:hover {
  background: var(--im-hover);
  color: var(--im-text-1);
}
.fpim-quote-ref {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin-bottom: 4px;
  padding: 4px 8px;
  background: var(--im-bg-side);
  border-left: 2px solid var(--im-line-strong);
  border-radius: 4px;
}
.fpim-quote-ref.is-missing {
  opacity: 0.7;
}
.fpim-quote-ref-name {
  font-size: 11px;
  color: var(--im-text-3);
}
.fpim-quote-ref-text {
  font-size: 12px;
  color: var(--im-text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

<style scoped>
.fpim-reactions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.fpim-reaction {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border: 0.5px solid var(--im-line-strong);
  background: var(--im-bg-side);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 12px;
  font-family: inherit;
  color: var(--im-text-2);
  cursor: pointer;
}
.fpim-reaction:hover {
  border-color: var(--im-primary);
}
.fpim-reaction.is-mine {
  background: var(--im-primary-weak);
  border-color: var(--im-primary);
  color: var(--im-primary);
}
.fpim-emojipick {
  display: flex;
  gap: 2px;
  margin-top: 4px;
  padding: 4px 6px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  width: fit-content;
}
.fpim-emojipick-btn {
  border: none;
  background: none;
  font-size: 18px;
  line-height: 1;
  padding: 3px;
  border-radius: 4px;
  cursor: pointer;
}
.fpim-emojipick-btn:hover {
  background: var(--im-hover);
}
</style>

<style scoped>
.fpim-mention {
  color: var(--im-primary);
  font-weight: 500;
}
.fpim-bubble.is-mentioned {
  background: #fff8e6;
}
</style>

<style scoped>
.fpim-readmark {
  color: var(--im-text-3);
}
.fpim-unknown {
  color: var(--im-warn, #ff8800);
  font-size: 12px;
}
.fpim-auto-badge {
  padding: 0 6px;
  border-radius: 4px;
  background: var(--im-primary-weak);
  color: var(--im-primary);
  font-size: 11px;
}
.fpim-forward-src {
  margin-bottom: 4px;
  padding: 4px 8px;
  background: var(--im-bg-side);
  border-radius: 4px;
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-edit-box {
  margin-top: 2px;
}
.fpim-edit-box textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 0.5px solid var(--im-primary);
  border-radius: var(--im-radius);
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}
.fpim-edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 6px;
}
.fpim-readmark.is-clickable {
  color: var(--im-primary);
  cursor: pointer;
}
.fpim-quote-ref {
  cursor: pointer;
}
.fpim-msg-sep.is-unread {
  color: var(--im-danger);
}
.fpim-imgwrap {
  cursor: zoom-in;
  display: inline-block;
}
.fpim-imgviewer {
  position: fixed;
  inset: 0;
  z-index: 4000;
  background: rgba(0, 0, 0, 0.82);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}
.fpim-imgviewer img {
  max-width: 88vw;
  max-height: 80vh;
  border-radius: 4px;
}
.fpim-imgviewer-dl {
  margin-top: 12px;
  color: #fff;
  font-size: 13px;
}
.fpim-msg {
  position: relative;
}
.fpim-msg.is-selectable {
  cursor: pointer;
}
.fpim-msg.is-selected .fpim-msg-body {
  background: var(--im-primary-weak);
  border-radius: var(--im-radius);
  padding: 4px 8px;
  margin: -4px -8px;
}
.fpim-select-bar {
  position: sticky;
  bottom: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #fff;
  border-top: 0.5px solid var(--im-line-strong);
}
.fpim-tplcard {
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 10px 12px;
  min-width: 260px;
  max-width: 360px;
}
.fpim-tplcard-head {
  font-size: 13px;
  font-weight: 500;
  color: var(--im-text-1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.fpim-tplcard-q {
  margin-top: 6px;
  font-size: 12px;
  color: var(--im-text-2);
}
.fpim-tplcard-a {
  margin-top: 4px;
  font-size: 12px;
  color: var(--im-text-1);
  line-height: 1.7;
}
.fpim-tplcard-foot {
  margin-top: 8px;
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-usercard {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 10px 12px;
  min-width: 240px;
}
.fpim-usercard-main {
  flex: 1;
  min-width: 0;
}
.fpim-usercard-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--im-text-1);
}
.fpim-usercard-meta {
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-composite {
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 10px 12px;
  min-width: 220px;
  cursor: pointer;
}
.fpim-composite:hover {
  border-color: var(--im-primary);
}
.fpim-composite-head {
  font-size: 13px;
  font-weight: 500;
  color: var(--im-text-1);
}
.fpim-composite-preview {
  margin-top: 4px;
  font-size: 12px;
  color: var(--im-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}
.fpim-composite-replay {
  max-height: 380px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.fpim-composite-item-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-composite-item-text {
  margin-top: 2px;
  font-size: 13px;
  color: var(--im-text-1);
}
.fpim-readlist-group {
  margin: 10px 0 4px;
  font-size: 12px;
  color: var(--im-text-3);
}
.fpim-readlist-names {
  font-size: 13px;
  color: var(--im-text-1);
  line-height: 1.7;
}
</style>
