<template>
  <div class="fpim-composer">
    <!-- 引用回复条：点消息「引用」后出现，发送后自动清除 -->
    <div v-if="quote" class="fpim-quote-bar">
      <div class="fpim-quote-main">
        <span class="fpim-quote-name">{{ quoteName }}</span>
        <span class="fpim-quote-text">{{ quotePreview }}</span>
      </div>
      <button class="fpim-iconbtn" title="取消引用" @click="store.clearQuote()">✕</button>
    </div>

    <!-- 人员名片选人 -->
    <el-dialog v-model="cardVisible" title="发送人员名片" width="420px" append-to-body destroy-on-close>
      <input
        v-model="cardKeyword"
        placeholder="搜索姓名 / 部门"
        style="width: 100%; box-sizing: border-box; height: 34px; padding: 0 10px; border: 0.5px solid var(--im-line-strong); border-radius: 6px; font-size: 13px; outline: none; margin-bottom: 8px"
      />
      <div style="max-height: 300px; overflow-y: auto">
        <div v-for="p in cardResults" :key="p.id" class="fpim-conv" style="cursor: pointer" @click="sendCard(p)">
          <div class="fpim-avatar sm" :style="{ background: avatarColor(p.id) }">{{ avatarText(p.name) }}</div>
          <div class="fpim-conv-main">
            <div class="fpim-conv-row1"><span class="fpim-conv-name">{{ p.name }}</span></div>
            <div class="fpim-conv-row2">
              <span class="fpim-conv-preview">{{ [p.department, p.role].filter(Boolean).join(" · ") }}</span>
            </div>
          </div>
        </div>
        <div v-if="!cardResults.length" class="fpim-empty">没有匹配的人员</div>
      </div>
    </el-dialog>

    <!-- @提及选择器：输入 @ 弹出（飞书同款交互） -->
    <div v-if="mentionVisible" class="fpim-mention-panel">
      <button
        v-for="m in mentionCandidates"
        :key="m.id"
        class="fpim-mention-item"
        type="button"
        @mousedown.prevent="pickMention(m)"
      >
        <div class="fpim-avatar sm" :style="{ background: avatarColor(m.id) }">{{ avatarText(m.name) }}</div>
        <span class="fpim-mention-name">{{ m.name }}</span>
        <span class="fpim-mention-dept">{{ m.department || "" }}</span>
      </button>
      <div v-if="!mentionCandidates.length" class="fpim-mention-empty">没有匹配的成员</div>
    </div>

    <!-- 快捷短语面板（自研补位：飞书普通会话没有用户级短语） -->
    <div v-if="phrasesVisible" class="fpim-phrases-panel">
      <div class="fpim-phrases-head">
        <span>快捷短语</span>
        <span class="fpim-hint">点击插入 · × 删除</span>
      </div>
      <button
        v-for="(q, i) in phrases"
        :key="i"
        class="fpim-phrase-item"
        type="button"
        @mousedown.prevent="insertPhrase(q)"
      >
        <span class="fpim-phrase-text">{{ q }}</span>
        <span class="fpim-phrase-del" @mousedown.prevent.stop="removePhrase(i)">×</span>
      </button>
      <div class="fpim-phrase-add">
        <input
          v-model="newPhrase"
          placeholder="添加常用语，回车保存"
          @keydown.enter.prevent="addPhrase"
        />
      </div>
    </div>

    <!-- 表情面板：点击即插入输入框 -->
    <div v-if="emojiVisible" class="fpim-emoji-panel">
      <button
        v-for="e in EMOJI_SET"
        :key="e"
        class="fpim-emoji-btn"
        type="button"
        @mousedown.prevent="insertEmoji(e)"
      >{{ e }}</button>
    </div>

    <div class="fpim-composer-tools">
      <el-tooltip content="表情" placement="top">
        <button class="fpim-iconbtn" @click="emojiVisible = !emojiVisible" v-html="ICON_EMOJI"></button>
      </el-tooltip>
      <el-tooltip content="快捷短语" placement="top">
        <button class="fpim-iconbtn" @click="phrasesVisible = !phrasesVisible" v-html="ICON_BOLT"></button>
      </el-tooltip>
      <el-tooltip content="发送文件" placement="top">
        <button class="fpim-iconbtn" @click="pickFile" v-html="ICON_CLIP"></button>
      </el-tooltip>
      <el-tooltip content="发送图片" placement="top">
        <button class="fpim-iconbtn" @click="pickImage" v-html="ICON_IMAGE"></button>
      </el-tooltip>
      <el-tooltip content="发送人员名片" placement="top">
        <button class="fpim-iconbtn" @click="cardVisible = true" v-html="ICON_CARD"></button>
      </el-tooltip>
      <el-tooltip content="召唤 Agent（任何会话都有）" placement="top">
        <button class="fpim-iconbtn is-bot" @click="summonAgent" v-html="ICON_BOT"></button>
      </el-tooltip>
      <span class="fpim-hint">Enter 发送 · Shift+Enter 换行 · @ 提及 · 可直接粘贴截图</span>
    </div>

    <textarea
      ref="box"
      v-model="text"
      rows="1"
      :placeholder="`发给 ${peerName}…`"
      :disabled="sending"
      @keydown.enter.exact.prevent="onEnter"
      @keydown.esc="mentionVisible = false"
      @input="onInput"
      @paste="onPaste"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    ></textarea>

    <div class="fpim-composer-foot">
      <span class="fpim-hint" v-if="errorText" style="color: var(--im-danger)">{{ errorText }}</span>
      <span class="fpim-hint" v-else>
        消息与问题同库留痕，发送后不可悄然删除<template v-if="mentions.length"> · 已 @ {{ mentions.length }} 人</template>
      </span>
      <button class="fpim-sendbtn" :disabled="!canSend" title="发送" @click="submit">
        <span v-if="sending">…</span>
        <span v-else class="fpim-sendbtn-icon" v-html="ICON_SEND"></span>
      </button>
    </div>

    <input ref="fileInput" type="file" style="display: none" @change="onFilePicked" />
    <input ref="imageInput" type="file" accept="image/*" style="display: none" @change="onFilePicked" />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";

import { avatarColor, avatarText } from "../../services/im/format.js";
import {
  ICON_BOLT, ICON_BOT, ICON_CARD, ICON_CLIP, ICON_EMOJI, ICON_IMAGE, ICON_SEND,
} from "./icons.js";
import { useDirectoryStore } from "../../stores/directory.js";
import { useImStore } from "../../stores/im.js";

const store = useImStore();
const directory = useDirectoryStore();

const box = ref(null);
const fileInput = ref(null);
const imageInput = ref(null);
const text = ref("");
const sending = ref(false);
const errorText = ref("");
const mentions = ref([]);   // [{id, name}] 本条消息提及的人（发送后清空）
const composing = ref(false);   // 中文输入法组合态：确认回车不触发发送（否则正文会丢）

const peerName = computed(() => store.active?.title || store.active?.peer?.name || "对方");
const canSend = computed(() => !!text.value.trim() && !sending.value);

const quote = computed(() => store.quote[store.activeId] || null);
const quoteName = computed(() => quote.value?.senderName || quote.value?.senderId || "");
const quotePreview = computed(() => {
  const q = quote.value;
  if (!q) return "";
  if (q.content?.text) return q.content.text.slice(0, 80);
  return q.content?.name || "[附件]";
});

// ── @提及 ────────────────────────────────────────────────────
const mentionVisible = ref(false);
const mentionKeyword = ref("");
const EMOJI_SET = "😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 😉 😊 😍 🥰 😘 😋 😎 🤓 🧐 🤔 🤨 😐 😴 😌 😔 😢 😭 😤 😠 🤬 🥳 🤯 😱 🤗 🤭 🤫 😇 🙏 👍 👎 👌 🤌 ✌️ 🤞 💪 🔥 🎉 🎊 ❤️ 💔 ⭐ ✅ ❌ 💡 📌 🚀 ☕ 🍎".split(" ").filter(Boolean);

/** 候选人：Agent 常驻首位（用户决策：只要有会话就要有 agent），群聊含群成员，单聊含对方 */
const AGENT_MEMBER = { id: "group-agent", name: "群聊 Agent", department: "平台智能服务" };
const mentionCandidates = computed(() => {
  const conv = store.active;
  if (!conv) return [];
  const list = [
    AGENT_MEMBER,
    ...(conv.type === "group" ? (conv.members || []) : (conv.peer ? [conv.peer] : []))
      .filter((m) => m.id !== "system" && m.id !== "group-agent"),
  ];
  const kw = mentionKeyword.value.trim().toLowerCase();
  return list
    .filter((m) => !kw || (m.name || "").toLowerCase().includes(kw))
    .slice(0, 6);
});

/** 🤖 一键召唤：群里/单聊里 @Agent，Agent 会回复「有何吩咐」 */
function summonAgent() {
  text.value = `${text.value ? text.value.trim() + " " : ""}@群聊 Agent `;
  nextTick(() => {
    box.value?.focus();
    autoGrow();
  });
}

function onInput() {
  const el = box.value;
  if (!el) return;
  const before = text.value.slice(0, el.selectionStart);
  const at = before.match(/@([^\s@]*)$/);
  if (at) {
    mentionKeyword.value = at[1] || "";
    mentionVisible.value = true;
  } else {
    mentionVisible.value = false;
  }
  autoGrow();
}

function pickMention(member) {
  const el = box.value;
  const cursor = el ? el.selectionStart : text.value.length;
  const before = text.value.slice(0, cursor).replace(/@([^\s@]*)$/, `@${member.name} `);
  text.value = before + text.value.slice(cursor);
  if (!mentions.value.some((m) => m.id === member.id)) {
    mentions.value.push({ id: member.id, name: member.name });
  }
  mentionVisible.value = false;
  nextTick(() => {
    if (!el) return;
    el.focus();
    el.selectionStart = el.selectionEnd = before.length;
    autoGrow();
  });
}

// ── 表情 ─────────────────────────────────────────────────────
const emojiVisible = ref(false);

// ── 人员名片 ──
const cardVisible = ref(false);
const cardKeyword = ref("");

const cardResults = computed(() => {
  const kw = cardKeyword.value.trim().toLowerCase();
  return directory.people
    .filter((p) => p.active !== false)
    .filter((p) => !kw || `${p.name} ${p.department || ""} ${p.role || ""}`.toLowerCase().includes(kw))
    .slice(0, 8);
});

async function sendCard(person) {
  try {
    await store.sendShareUser(person);
    cardVisible.value = false;
    cardKeyword.value = "";
  } catch (err) {
    window.alert(err.message || "发送失败");
  }
}

// ── 快捷短语（自研补位，本地存储）──
const PHRASE_KEY = "fpim.quickPhrases";
const DEFAULT_PHRASES = ["收到，马上处理", "稍等，我看一下", "已解决，请查收", "这个问题我需要转给相关同事"];
const phrasesVisible = ref(false);
const phrases = ref(JSON.parse(localStorage.getItem(PHRASE_KEY) || "null") || DEFAULT_PHRASES);
const newPhrase = ref("");

function insertPhrase(q) {
  const el = box.value;
  const cursor = el ? el.selectionStart : text.value.length;
  text.value = text.value.slice(0, cursor) + q + text.value.slice(cursor);
  phrasesVisible.value = false;
  nextTick(() => {
    if (!el) return;
    el.focus();
    el.selectionStart = el.selectionEnd = cursor + q.length;
    autoGrow();
  });
}

function addPhrase() {
  const q = newPhrase.value.trim();
  if (!q) return;
  phrases.value.push(q.slice(0, 60));
  localStorage.setItem(PHRASE_KEY, JSON.stringify(phrases.value));
  newPhrase.value = "";
}

function removePhrase(index) {
  phrases.value.splice(index, 1);
  localStorage.setItem(PHRASE_KEY, JSON.stringify(phrases.value));
}

function insertEmoji(emoji) {
  const el = box.value;
  const cursor = el ? el.selectionStart : text.value.length;
  text.value = text.value.slice(0, cursor) + emoji + text.value.slice(cursor);
  emojiVisible.value = false;
  nextTick(() => {
    if (!el) return;
    el.focus();
    el.selectionStart = el.selectionEnd = cursor + emoji.length;
    autoGrow();
  });
}

watch(() => store.activeId, () => {
  text.value = store.draft[store.activeId] || "";
  mentions.value = [];
  mentionVisible.value = false;
  emojiVisible.value = false;
  nextTick(autoGrow);
});

function autoGrow() {
  const el = box.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
}

function onEnter(event) {
  // IME 组合期间的 Enter 是"上屏原文"，不是发送（此前无此防护会发出截断/空正文）
  if (composing.value || event.isComposing || event.keyCode === 229) return;
  submit();
}

async function submit() {
  if (!canSend.value) return;
  sending.value = true;
  errorText.value = "";
  const body = text.value;
  const replyToId = quote.value?.id || null;
  // 只保留文本里实际出现的 @（改文案后提及自动失效）
  const activeMentions = mentions.value.filter((m) => body.includes(`@${m.name}`));
  try {
    await store.sendText(body, {
      replyToId,
      mentions: activeMentions.map((m) => ({ id: m.id, name: m.name })),
    });
    text.value = "";
    mentions.value = [];
    store.draft[store.activeId] = "";
    store.clearQuote();
    nextTick(autoGrow);
  } catch (err) {
    errorText.value = err.message || "发送失败，请重试";
    text.value = body;                       // 失败保留内容，不让人白写
  } finally {
    sending.value = false;
  }
}

function pickFile() { fileInput.value?.click(); }
function pickImage() { imageInput.value?.click(); }

async function onFilePicked(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (file) await upload(file);
}

/** 截图直接粘进输入框（Web 端覆盖 80% 的截图场景，剩下的交给桌面壳） */
async function onPaste(event) {
  const items = Array.from(event.clipboardData?.items || []);
  const image = items.find((it) => it.type.startsWith("image/"));
  if (!image) return;
  const file = image.getAsFile();
  if (!file) return;
  event.preventDefault();
  await upload(file);
}

async function upload(file) {
  sending.value = true;
  errorText.value = "";
  try {
    await store.sendFile(file);
  } catch (err) {
    errorText.value = err.message || "上传失败";
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped>
.fpim-composer {
  position: relative;
}
.fpim-iconbtn.is-bot:hover {
  color: var(--im-primary);
}
.fpim-sendbtn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: var(--im-primary);
  color: #fff;
  cursor: pointer;
}
.fpim-sendbtn:hover {
  background: var(--im-primary-hover);
}
.fpim-sendbtn:disabled {
  background: var(--im-primary-weak);
  color: var(--im-text-4);
  cursor: default;
}
.fpim-sendbtn-icon {
  display: inline-flex;
}
.fpim-quote-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 12px 0;
  padding: 6px 10px;
  background: var(--im-bg-side);
  border-left: 2px solid var(--im-primary);
  border-radius: 4px;
}
.fpim-quote-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.fpim-quote-name {
  font-size: 12px;
  color: var(--im-primary);
}
.fpim-quote-text {
  font-size: 12px;
  color: var(--im-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* @提及面板 */
.fpim-mention-panel {
  position: absolute;
  bottom: calc(100% - 4px);
  left: 12px;
  z-index: 40;
  width: 260px;
  max-height: 220px;
  overflow-y: auto;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 4px;
}
.fpim-mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: none;
  background: none;
  padding: 6px 8px;
  border-radius: 4px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.fpim-mention-item:hover {
  background: var(--im-hover);
}
.fpim-mention-name {
  color: var(--im-text-1);
  font-weight: 500;
}
.fpim-mention-dept {
  color: var(--im-text-3);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fpim-mention-empty {
  padding: 10px;
  font-size: 12px;
  color: var(--im-text-3);
  text-align: center;
}

/* 快捷短语面板 */
.fpim-phrases-panel {
  position: absolute;
  bottom: calc(100% - 4px);
  left: 12px;
  z-index: 40;
  width: 280px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 8px;
}
.fpim-phrases-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--im-text-3);
  padding: 2px 4px 6px;
}
.fpim-phrase-item {
  display: flex;
  align-items: center;
  width: 100%;
  border: none;
  background: none;
  padding: 6px 8px;
  border-radius: 4px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.fpim-phrase-item:hover {
  background: var(--im-hover);
}
.fpim-phrase-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fpim-phrase-del {
  color: var(--im-text-3);
  padding: 0 4px;
}
.fpim-phrase-del:hover {
  color: var(--im-danger);
}
.fpim-phrase-add {
  margin-top: 6px;
}
.fpim-phrase-add input {
  width: 100%;
  box-sizing: border-box;
  height: 28px;
  padding: 0 8px;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius);
  font: inherit;
  font-size: 12px;
  outline: none;
}

/* 表情面板 */
.fpim-emoji-panel {
  position: absolute;
  bottom: calc(100% - 4px);
  left: 12px;
  z-index: 40;
  width: 320px;
  background: #fff;
  border: 0.5px solid var(--im-line-strong);
  border-radius: var(--im-radius-lg);
  padding: 8px;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
}
.fpim-emoji-btn {
  border: none;
  background: none;
  font-size: 20px;
  line-height: 1;
  padding: 5px;
  border-radius: 4px;
  cursor: pointer;
}
.fpim-emoji-btn:hover {
  background: var(--im-hover);
}
</style>
