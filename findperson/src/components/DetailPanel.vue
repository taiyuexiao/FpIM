<!-- 右侧详情面板：展示人员详情、内容详情、内容草稿、资料维护、空状态 -->
<template>
  <div class="detail-panel">

    <!-- ── 人员详情 ── -->
    <template v-if="detail.type === 'person'">
      <div class="detail-panel-top">
        <div class="detail-panel-label">人员详情</div>
        <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
      </div>
      <div class="detail-header">
        <div class="detail-title-row">
          <h2>{{ personOf(detail.personId)?.name }}</h2>
          <button class="chat-tab" type="button" title="发起会话(免加好友,直接对话)"
                  @click="startChat()">💬 发消息</button>
        </div>
        <p>{{ departmentText(personOf(detail.personId)) }} · {{ personOf(detail.personId)?.role }}</p>
        <p>联系方式：{{ personOf(detail.personId)?.contact || personOf(detail.personId)?.phone }}</p>
      </div>
      <div class="field-row">
        <span v-for="tag in personOf(detail.personId)?.domains" :key="tag" class="tag">{{ tag }}</span>
      </div>
      <div class="detail-card">
        <p>{{ personOf(detail.personId)?.selfPortrait }}</p>
      </div>
      <div class="detail-section">
        <h3>相关发布内容</h3>
        <div v-if="personRelated.length" class="related-list">
          <button v-for="item in personRelated" :key="item.id" type="button" @click="$emit('content', item.id)">
            {{ item.title }}
          </button>
        </div>
        <div v-else class="empty-state compact">暂无相关发布内容。</div>
      </div>
      <button class="primary-button small-button" @click="$emit('profile', detail.personId)">查看完整主页</button>
    </template>

    <!-- ── 内容详情 ── -->
    <template v-else-if="detail.type === 'content'">
      <div class="detail-panel-top">
        <div class="detail-panel-label">内容详情</div>
        <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
      </div>
      <div class="detail-card">
        <div class="detail-title">
          <strong>{{ contentOf(detail.contentId)?.title }}</strong>
          <span v-if="contentOf(detail.contentId)?.pinned" class="pin-badge">置顶</span>
        </div>
        <p>{{ personOf(contentOf(detail.contentId)?.ownerId)?.name || '未知发布人' }} · {{ contentOf(detail.contentId)?.publishedAt }}</p>
        <p>{{ contentOf(detail.contentId)?.summary }}</p>
      </div>
      <div class="field-row">
        <span v-for="tag in contentOf(detail.contentId)?.tags" :key="tag" class="tag">{{ tag }}</span>
      </div>
      <button class="primary-button small-button" @click="$emit('content', detail.contentId)">查看详情页</button>
    </template>

    <!-- ── 内容发布草稿(可直接修改) ── -->
    <template v-else-if="detail.type === 'contentDraft'">
      <div class="detail-panel-top">
        <div class="detail-panel-label">内容发布草稿</div>
        <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
      </div>
      <div class="detail-card">
        <h3>标题</h3>
        <input class="detail-edit-input" :value="detail.draft?.title" @input="updateDraftField('title', $event.target.value)" />
        <h3>关联领域(顿号分隔)</h3>
        <input class="detail-edit-input" :value="(detail.draft?.tags || []).join('、')" @input="updateDraftField('tags', $event.target.value)" />
        <h3>摘要</h3>
        <textarea class="detail-edit-input" rows="3" :value="detail.draft?.summary" @input="updateDraftField('summary', $event.target.value)"></textarea>
        <h3>正文</h3>
        <textarea class="detail-edit-input detail-edit-body" :value="detail.draft?.body" @input="updateDraftField('body', $event.target.value)"></textarea>
      </div>
      <div class="thread-card-actions">
        <button v-if="!detail.confirmed" class="primary-button small-button" @click="$emit('confirmContent')">确认发布</button>
        <button class="secondary-button small-button" @click="$emit('mine')">去发布页继续编辑</button>
      </div>
    </template>

    <!-- ── 他人画像草稿(上:画像事项表单,与个人中心-为他人画像同模块;下:画像对象信息) ── -->
    <template v-else-if="detail.type === 'reviewAction'">
      <div class="detail-panel-top">
        <div class="detail-panel-label">为 {{ reviewPerson?.name || '同事' }} 画像</div>
        <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
      </div>
      <!-- 上:画像事项表单(同事/日期/事项,与个人中心-为他人画像同结构) -->
      <div class="detail-card">
        <label class="detail-edit-field">
          <span>同事</span>
          <input class="detail-edit-input" :value="reviewPerson?.name || '待确认人员'" disabled />
        </label>
        <label class="detail-edit-field">
          <span>日期</span>
          <input class="detail-edit-input" :value="detail.action?.nextReview?.date" disabled />
        </label>
        <label class="detail-edit-field">
          <span>负责领域</span>
          <input class="detail-edit-input" :value="detail.action?.nextReview?.tag" @input="updateReviewField('tag', $event.target.value)" placeholder="请输入负责领域(顿号分隔)" />
        </label>
      </div>
      <!-- 下:画像对象信息(紧凑展示) -->
      <div class="detail-card">
        <div class="detail-panel-label">画像对象</div>
        <h2>{{ reviewPerson?.name }}</h2>
        <p>{{ departmentText(reviewPerson) }} · {{ reviewPerson?.role }}</p>
        <p>联系方式：{{ reviewPerson?.contact || reviewPerson?.phone }}</p>
        <div class="field-row" v-if="reviewPerson?.domains?.length">
          <span v-for="tag in reviewPerson.domains" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
      <!-- 操作按钮上下排列,均独占一行蓝底白字 -->
      <div class="thread-card-actions detail-action-stack">
        <button v-if="!detail.confirmed" class="primary-button small-button" @click="$emit('confirmReview')">确认保存画像</button>
        <button class="primary-button small-button" @click="$emit('profile', detail.action?.nextReview?.personId)">查看完整主页</button>
        <button class="primary-button small-button" @click="$emit('mine')">去画像页修改</button>
      </div>
    </template>

    <!-- ── 资料维护 ── -->
    <template v-else-if="detail.type === 'profileAction'">
      <div class="detail-panel-top">
        <div class="detail-panel-label">资料维护</div>
        <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
      </div>
      <div class="detail-card">
        <h2>{{ detail.action?.confirmed ? '资料维护已完成' : '待更新字段(可直接修改)' }}</h2>
        <template v-if="profilePatchEntries.length">
          <label v-for="entry in profilePatchEntries" :key="entry.key" class="detail-edit-field">
            <span>{{ entry.label }}</span>
            <textarea v-if="entry.key === 'selfPortrait'" class="detail-edit-input" rows="3" :value="entry.text" @input="updateProfileField(entry.key, $event.target.value)"></textarea>
            <input v-else class="detail-edit-input" :value="entry.text" @input="updateProfileField(entry.key, $event.target.value)" />
          </label>
        </template>
        <p v-else>暂未识别到完整字段，可进入个人中心手动补充。</p>
      </div>
      <div v-if="profileUser" class="detail-card">
        <h3>当前用户信息</h3>
        <p>{{ profileUser.name }} · {{ departmentText(profileUser) }} · {{ profileUser.role }}</p>
        <p>联系方式：{{ profileUser.contact || profileUser.phone }}</p>
      </div>
      <div class="thread-card-actions">
        <button v-if="!detail.action?.confirmed && canConfirmProfile" class="primary-button small-button" @click="$emit('confirmProfile')">
          确认更新主页
        </button>
        <button class="secondary-button small-button" @click="$emit('mine')">
          {{ detail.action?.confirmed ? '继续编辑' : '手动编辑' }}
        </button>
      </div>
    </template>

    <!-- ── 空状态 ── -->
    <template v-else>
      <div class="detail-empty">
        <div class="detail-panel-top">
          <div class="detail-panel-label">详情面板</div>
          <button class="detail-close-button" @click="$emit('close')"><span>收起</span><strong>×</strong></button>
        </div>
        <div class="detail-empty-copy">
          <h2>右侧详情</h2>
          <p>点击问答里的人员卡片或内容卡片，就可以在这里展开查看。</p>
        </div>
      </div>
    </template>

  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useImStore } from '../stores/im.js';

const router = useRouter();
const im = useImStore();

const props = defineProps({
  /** 当前详情对象，决定面板展示哪种内容 */
  detail: Object,
  /** 全部人员列表 */
  people: Array,
  /** 全部内容列表 */
  content: Array,
  /** 全局反馈数据 */
  feedback: Object,
  /** 当前登录用户 ID */
  currentUserId: String,
});
defineEmits(['close', 'profile', 'content', 'mine', 'confirmProfile', 'confirmContent', 'confirmReview', 'toggleFeedback']);

// ── 查找工具 ──
const personOf = (id) => props.people.find((item) => item.id === id);
const contentOf = (id) => props.content.find((item) => item.id === id);
const departmentText = (person) => person?.departmentPath?.join(' / ') || person?.department || '';

// ── 发起会话(人员详情) ──
// 原为「写邮件」，IM 化后改为直接建单聊：免加好友，一键进聊天框
async function startChat() {
  const target = props.detail;
  if (!target?.personId) return;
  try {
    await im.openWith(target.personId, target.issueId || null);
    router.push({ name: 'chat' });
  } catch (error) {
    ElMessage.error(error.message || '发起会话失败');
  }
}

// ── 计算属性 ──
const personRelated = computed(() => {
  if (props.detail?.type !== 'person') return [];
  const person = personOf(props.detail.personId);
  if (!person) return [];
  return props.content.filter((item) => item.ownerId === person.id).slice(0, 4);
});

const profileUser = computed(() => personOf(props.currentUserId));
const canConfirmProfile = computed(() => Object.keys(props.detail?.action?.nextProfilePatch || {}).length > 0);
// 他人画像:被画像人详情(结构对齐查人侧栏)
const reviewPerson = computed(() => personOf(props.detail?.action?.nextReview?.personId));

// ── 侧边栏直接修改(改动写回卡片 action,确认时生效) ──
const PROFILE_FIELD_LABELS = {
  contact: '联系方式',
  addDomains: '负责领域(新增,顿号分隔)',
  removeDomains: '负责领域(删除,顿号分隔)',
  domainsText: '负责领域',
  selfPortrait: '自画像',
};
const profilePatchEntries = computed(() => {
  const patch = props.detail?.action?.nextProfilePatch || {};
  return Object.entries(patch).map(([key, value]) => ({
    key,
    label: PROFILE_FIELD_LABELS[key] || key,
    text: Array.isArray(value) ? value.join('、') : String(value ?? ''),
  }));
});
const splitList = (text) => text.split(/[、,，]/).map((s) => s.trim()).filter(Boolean);
function updateProfileField(key, text) {
  const patch = props.detail?.action?.nextProfilePatch;
  if (!patch) return;
  patch[key] = Array.isArray(patch[key]) ? splitList(text) : text;
}
function updateDraftField(key, text) {
  const draft = props.detail?.draft;
  if (!draft) return;
  draft[key] = key === 'tags' ? splitList(text) : text;
}
function updateReviewField(key, text) {
  const review = props.detail?.action?.nextReview;
  if (!review) return;
  review[key] = text;
}
</script>

<style scoped>
/* 姓名行:名字与发消息按钮同行展示 */
.detail-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-title-row h2 {
  margin: 0;
}
/* 发消息按钮:名字右侧的小标签按钮,悬停高亮 */
.chat-tab {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 10px;
  border: 1px solid var(--primary-color, #2563eb);
  border-radius: 12px;
  background: transparent;
  color: var(--primary-color, #2563eb);
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.chat-tab:hover {
  background: var(--primary-color, #2563eb);
  color: #ffffff;
}

/* 侧栏操作按钮:竖排堆叠,每个独占一行 */
.detail-action-stack {
  flex-direction: column;
  align-items: stretch;
}

/* 侧边栏直接修改输入框(与全局卡片风格一致的轻量样式) */
.detail-edit-field {
  display: block;
  margin-top: 8px;
  font-size: 13px;
}
.detail-edit-field > span {
  display: block;
  margin-bottom: 4px;
  color: var(--text-secondary, #666);
}
.detail-edit-input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 8px;
  border: 1px solid var(--border-color, #dcdfe6);
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
}
.detail-card h3 {
  margin: 10px 0 4px;
  font-size: 13px;
}
/* 正文编辑框:大框+限高滚动(长正文上下滑动) */
.detail-edit-body {
  min-height: 220px;
  max-height: 45vh;
  overflow-y: auto;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
