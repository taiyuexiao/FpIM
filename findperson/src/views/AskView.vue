<template>
  <section class="view active" id="view-ask">
    <div
      class="ask-workspace"
      :class="{
        'has-session': agui.activeMessages.length,
        'has-detail': agui.isDetailSidebarVisible,
        'detail-collapsed': !agui.isDetailSidebarVisible
      }"
    >
      <ConversationSidebar
        v-model:search="historySearch"
        :sessions="sessions.sessions"
        :searched-sessions="searchedSessions"
        :active-session-id="sessions.activeSessionId"
        :is-search-open="isHistorySearchOpen"
        @toggle-search="isHistorySearchOpen = !isHistorySearchOpen"
        @close-search="isHistorySearchOpen = false"
        @new-chat="newChat"
        @select="selectSession"
        @command="handleSessionCommand"
      />

      <section class="chat-shell" :class="{ 'has-session': agui.activeMessages.length, 'is-loading': agui.isStreaming }">
        <div class="chat-topbar">
          <div><h1>智能问答</h1></div>
          <el-button class="topbar-icon-button ask-detail-toggle" @click="agui.isDetailSidebarVisible = !agui.isDetailSidebarVisible">
            <el-icon><Memo /></el-icon>
          </el-button>
        </div>

        <div class="chat-main">
          <div v-if="!agui.activeMessages.length && !agui.isStreaming" class="chat-hero">
            <div class="sample-row home-samples" aria-label="示例问题">
              <div class="chat-entry-title">开始对话</div>
            </div>
          </div>
          <div ref="threadPanel" class="chat-thread-panel">
            <ThreadList>
              <ThreadTurn v-for="turn in turns" :key="turn.user.id">
                <article class="thread-bubble user-bubble">
                  <p>{{ turn.user.text }}</p>
                  <button class="copy-instruction-button" type="button" title="复制该指令"
                          @click.stop="copyInstruction(turn.user)">
                    <el-icon v-if="copiedInstructionId !== turn.user.id"><CopyDocument /></el-icon>
                    <span v-else class="copied-tip">已复制</span>
                  </button>
                </article>
                <AssistantBubble :message="turn.assistant" />

                <RecommendationCardGroup
                  :cards="recommendationCards(turn.assistant.id)"
                  @profile="openProfile"
                  @detail="(personId) => agui.openPersonDetail(personId, { question: turn.user.text })"
                />

                <ActionCard
                  v-for="card in confirmationCards(turn.assistant.id)"
                  :key="card.id"
                  :card="card"
                  :people="directory.people"
                  :latest="true"
                  @confirm="agui.confirmCard"
                  @edit="continueActionDraft"
                  @publish="startPublishDraft"
                  @profile="openProfile"
                  @content="openContentDetail"
                  @detail="agui.openActionDetail"
                />

                <!-- 回答级反馈(有帮助/没帮助)放在一轮对话末尾,点踩弹原因选项 -->
                <AnswerFeedbackBar
                  v-if="!turn.assistant.streaming && turn.assistant.text"
                  :message="turn.assistant"
                  :question="turn.user.text"
                  :candidates="candidateNames(turn.assistant.id)"
                  :session-id="sessions.activeSessionId"
                />
              </ThreadTurn>
            </ThreadList>
          </div>
        </div>

        <ChatComposer v-model="questionInput" :disabled="agui.isStreaming" @send="sendQuestion" />
      </section>

      <DetailSidebar
        :visible="agui.isDetailSidebarVisible"
        :detail="agui.activeDetail"
        :people="directory.people"
        :content="content.publicContentRecords"
        :feedback="feedback.feedbackMap"
        :current-user-id="auth.userId"
        @close="agui.closeDetailSidebar"
        @profile="openProfile"
        @content="openContentDetail"
        @mine="continueDetailAction"
        @confirm-profile="confirmProfileFromDetail"
        @confirm-content="confirmCardFromDetail"
        @confirm-review="confirmCardFromDetail"
        @toggle-feedback="toggleFeedback"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import { Memo, CopyDocument } from "@element-plus/icons-vue";
import ActionCard from "../components/ask/ActionCard.vue";
import AnswerFeedbackBar from "../components/ask/AnswerFeedbackBar.vue";
import AssistantBubble from "../components/ask/AssistantBubble.vue";
import ChatComposer from "../components/ask/ChatComposer.vue";
import ConversationSidebar from "../components/ask/ConversationSidebar.vue";
import DetailSidebar from "../components/ask/DetailSidebar.vue";
import RecommendationCardGroup from "../components/ask/RecommendationCardGroup.vue";
import ThreadList from "../components/ask/ThreadList.vue";
import ThreadTurn from "../components/ask/ThreadTurn.vue";
import { useAguiStore } from "../stores/agui.js";
import { useAuthStore } from "../stores/auth.js";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useFeedbackStore } from "../stores/feedback.js";
import { useSessionsStore } from "../stores/sessions.js";
import { useDraftsStore } from "../stores/drafts.js";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const sessions = useSessionsStore();
const agui = useAguiStore();
const directory = useDirectoryStore();
const content = useContentStore();
const feedback = useFeedbackStore();
const drafts = useDraftsStore();

sessions.init();
sessions.ensureActiveSession();
// 进入问答页(含从其他页面切回):本地无缓存时从服务端回拉当前会话历史
agui.loadSessionHistory(sessions.activeSessionId);

// 新消息/流式更新后自动滚动到对话最新位置(发送问题后不再停留在原位置)
const threadPanel = ref(null);
function scrollThreadToBottom() {
  nextTick(() => {
    const el = threadPanel.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}
watch(() => agui.activeMessages, () => scrollThreadToBottom(), { deep: true });
watch(() => agui.cardsByMessage, () => scrollThreadToBottom(), { deep: true });
onMounted(() => scrollThreadToBottom());

// 输入框草稿存在 agui store(按会话):切页/刷新不丢,发送后清空
const questionInput = computed({
  get: () => agui.composerDrafts[sessions.activeSessionId] || "",
  set: (value) => agui.setComposerDraft(sessions.activeSessionId, value),
});
// 历史对话搜索(main 分支标准:侧栏搜索按钮 + 弹层检索标题/摘要)
const historySearch = ref("");
const isHistorySearchOpen = ref(false);
const copiedInstructionId = ref("");
let copiedTimer = null;

async function copyInstruction(message) {
  const text = message.text || "";
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // 降级:隐藏 textarea 选区复制(非安全上下文兜底)
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  copiedInstructionId.value = message.id;
  clearTimeout(copiedTimer);
  copiedTimer = setTimeout(() => { copiedInstructionId.value = ""; }, 1500);
}
const searchedSessions = computed(() => sessions.searchSessions(historySearch.value));
const turns = computed(() => {
  const messages = agui.activeMessages;
  const pairs = [];
  for (let index = 0; index < messages.length; index += 2) {
    if (messages[index]?.role === "user" && messages[index + 1]?.role === "assistant") {
      pairs.push({ user: messages[index], assistant: messages[index + 1] });
    }
  }
  return pairs;
});

function recommendationCards(messageId) {
  return (agui.cardsByMessage[messageId] || []).filter((card) => card.kind === "recommendation");
}

function confirmationCards(messageId) {
  return (agui.cardsByMessage[messageId] || []).filter((card) => card.kind === "confirmation");
}

function candidateNames(messageId) {
  // 推荐人选姓名列表(随反馈入库,后台可视化用)
  return recommendationCards(messageId)
    .map((card) => directory.getPerson(card.personId)?.name || card.person?.name || card.personId)
    .filter(Boolean);
}

function newChat() {
  sessions.createOrReuseBlankSession();
}

function selectSession(id) {
  sessions.selectSession(id);
  isHistorySearchOpen.value = false;
  agui.loadSessionHistory(id);
}

async function handleSessionCommand(command, sessionId) {
  if (command === "rename") {
    try {
      const session = sessions.sessions.find((item) => item.id === sessionId);
      const { value } = await ElMessageBox.prompt("请输入新的会话标题", "重命名会话", {
        confirmButtonText: "确认",
        cancelButtonText: "取消",
        inputValue: session?.title || "新对话",
      });
      sessions.renameSession(sessionId, value);
    } catch {
      return;
    }
  }
  if (command === "delete") sessions.deleteSession(sessionId);
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  const session = sessions.ensureActiveSession();
  questionInput.value = "";
  agui.setComposerDraft(session.id, "");
  scrollThreadToBottom();
  await agui.sendMessage(session.id, question);
}

function toggleFeedback(targetKey, value) {
  feedback.toggle(targetKey, value, { sessionId: sessions.activeSessionId });
}

function openProfile(personId) {
  router.push({ name: "profile", params: { id: personId }, query: { redirect: route.fullPath } });
}

function openContentDetail(contentId) {
  router.push({ name: "contentDetail", params: { id: contentId }, query: { redirect: route.fullPath } });
}

function startPublishDraft(draft) {
  // 已确认/已入库的内容:走编辑路径而非新建草稿(验收:继续编辑不应变新建)
  if (draft?.id) {
    router.push({ name: "publish", query: { id: draft.id, redirect: route.fullPath } });
    return;
  }
  const draftId = drafts.create("content", draft || {}, route.fullPath);
  router.push({
    name: "publish",
    query: { draftId, redirect: route.fullPath },
  });
}

function continueActionDraft(action) {
  if (action.type === "profile") {
    const draftId = drafts.create("profile", action.nextProfilePatch || {}, route.fullPath);
    router.push({ name: "mine", query: { edit: "profile", draftId, redirect: route.fullPath } });
  } else if (action.type === "review") {
    const draftId = drafts.create("review", action.nextReview || {}, route.fullPath);
    router.push({ name: "review", query: { draftId, redirect: route.fullPath } });
  }
}

function continueDetailAction() {
  if (agui.activeDetail.type === "profileAction") continueActionDraft(agui.activeDetail.action || {});
  else if (agui.activeDetail.type === "reviewAction") continueActionDraft(agui.activeDetail.action || {});
  else if (agui.activeDetail.type === "contentDraft") startPublishDraft(agui.activeDetail.draft);
  else router.push({ name: "mine", query: { redirect: route.fullPath } });
}

function confirmProfileFromDetail() {
  const cardId = agui.activeDetail.cardId;
  if (cardId) agui.confirmCard(cardId);
}

function confirmCardFromDetail() {
  const cardId = agui.activeDetail.cardId;
  if (cardId) agui.confirmCard(cardId);
}
</script>

<style scoped>
/* 用户指令气泡右上角复制按钮(蓝色气泡上的轻量白图标) */
.user-bubble {
  position: relative;
}
.copy-instruction-button {
  position: absolute;
  top: 4px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  border: 0;
  padding: 2px;
  background: transparent;
  color: rgba(255, 255, 255, 0.65);
  cursor: pointer;
  font-size: 13px;
  opacity: 0.65;
  transition: opacity 0.15s ease;
}
.user-bubble:hover .copy-instruction-button,
.copy-instruction-button:focus-visible,
.copy-instruction-button:hover {
  opacity: 1;
  color: #ffffff;
}
.copied-tip {
  font-size: 11px;
  color: #ffffff;
  opacity: 1;
}
</style>
