<!-- 操作卡片：用于问答页中资料维护、画像、内容发布等待确认动作 -->
<template>

  <!-- ── 资料维护 ── -->
  <article
    v-if="action.type === 'profile'"
    :class="['thread-card', 'action-card', latest ? 'is-pending' : '', 'is-clickable']"
    @click="$emit('detail', card || { type: 'profileAction', action })"
  >
    <div class="thread-card-head">
      <span class="intent-pill">{{ analysis.intent }}</span>
      <strong>{{ action.title }}</strong>
    </div>
    <p>{{ action.description }}</p>
    <div class="action-preview">
      <span v-for="item in (action.changes?.length ? action.changes : ['未识别到明确字段，将引导进入个人中心编辑。'])" :key="item">
        {{ item }}
      </span>
    </div>
    <div class="thread-card-actions" @click.stop>
      <button v-if="isConfirmed" class="secondary-button small-button" @click="$emit('edit', action)">继续编辑</button>
      <button v-else-if="hasProfilePatch" class="primary-button small-button" @click="$emit('confirm', confirmKey)">确认更新主页</button>
      <button v-if="!isConfirmed" class="secondary-button small-button" @click="$emit('edit', action)">手动编辑</button>
    </div>
  </article>

  <!-- ── 他人画像 ── -->
  <article
    v-else-if="action.type === 'review'"
    :class="['thread-card', 'action-card', latest ? 'is-pending' : '', 'is-clickable']"
    @click="$emit('detail', card || { type: 'person', personId: action.nextReview.personId })"
  >
    <div class="thread-card-head">
      <span class="intent-pill">{{ analysis.intent }}</span>
      <strong>{{ action.title }}</strong>
    </div>
    <p>{{ action.description }}</p>
    <div class="publish-preview review-person-preview">
      <!-- 与查人推荐卡片(RecommendationCard)同格式:姓名/部门/职位/上级/联系方式/领域/自我介绍 -->
      <div class="person-head">
        <div>
          <p class="person-name">{{ reviewPerson?.name || action.nextReview.personName || '待确认人员' }}</p>
          <p class="person-meta">{{ reviewDepartment }}</p>
          <p class="person-meta">{{ reviewPerson?.role }}</p>
          <p class="person-meta" v-if="reviewSupervisor">上级：{{ reviewSupervisor }}</p>
          <p class="person-meta">联系方式：{{ reviewPerson?.contact || reviewPerson?.phone || '-' }}</p>
        </div>
      </div>
      <div class="field-row" v-if="reviewPerson?.domains?.length">
        <span v-for="tag in reviewPerson.domains" :key="tag" class="tag">{{ tag }}</span>
      </div>
      <p class="person-meta person-portrait" v-if="reviewPerson?.selfPortrait">{{ reviewPerson.selfPortrait }}</p>
      <p class="review-new-tag">本次画像：{{ action.nextReview.text || action.nextReview.tag }}（{{ action.nextReview.date }}）</p>
    </div>
    <div class="thread-card-actions review-card-actions" @click.stop>
      <button v-if="isConfirmed" class="primary-button small-button" @click="$emit('profile', action.nextReview.personId)">
        查看画像对象
      </button>
      <button v-else class="primary-button small-button" @click="$emit('confirm', confirmKey)">确认保存画像</button>
      <button class="secondary-button small-button" @click="$emit('edit', action)">
        {{ isConfirmed ? '继续补充' : '继续修改' }}
      </button>
    </div>
  </article>

  <!-- ── 内容发布（默认） ── -->
  <article
    v-else
    :class="['thread-card', 'action-card', latest ? 'is-pending' : '', 'is-clickable']"
    @click="$emit('detail', isConfirmed
      ? { type: 'content', contentId: action.nextContent.id }
      : (card || { type: 'contentDraft', draft: action.nextContent })
    )"
  >
    <div class="thread-card-head">
      <span class="intent-pill">{{ analysis.intent }}</span>
      <strong>{{ action.title }}</strong>
    </div>
    <p>{{ action.description }}</p>
    <div class="publish-preview">
      <strong>{{ action.nextContent.title }}</strong>
      <span v-if="action.nextContent.tags && action.nextContent.tags.length">{{ action.nextContent.tags.join('、') }}</span>
      <p v-if="action.nextContent.summary">{{ action.nextContent.summary }}</p>
    </div>
    <div class="thread-card-actions" @click.stop>
      <button v-if="isConfirmed" class="primary-button small-button" @click="$emit('content', action.nextContent.id)">
        查看内容
      </button>
      <button v-else class="primary-button small-button" @click="$emit('confirm', confirmKey)">确认发布</button>
      <button class="secondary-button small-button" @click="$emit('publish', action.nextContent)">
        {{ isConfirmed ? '继续编辑' : '手动补充' }}
      </button>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue';
import { useDirectoryStore } from '../stores/directory.js';

const props = defineProps({
  /** 问答匹配结果对象 */
  result: Object,
  /** AGUI confirmation card */
  card: Object,
  /** 全部人员列表 */
  people: Array,
  /** 是否为最新一轮对话 */
  latest: Boolean,
});
defineEmits(['confirm', 'edit', 'publish', 'profile', 'content', 'detail']);

const action = computed(() => props.card?.action || props.result?.action || {});
const analysis = computed(() => props.card?.analysis || props.result?.analysis || {});
const isConfirmed = computed(() => action.value.confirmed || props.card?.status === 'confirmed');
const confirmKey = computed(() => props.card?.id || action.value.type);
const hasProfilePatch = computed(() => Object.keys(action.value.nextProfilePatch || {}).length > 0);

/** 画像对象的人员信息(名录 store 为准,含上级/领域/自我介绍,与查人卡片对齐) */
const directory = useDirectoryStore();
const reviewPerson = computed(() => {
  if (action.value.type !== 'review') return null;
  const personId = action.value.nextReview.personId;
  return directory.getPerson(personId)
    || props.people?.find((item) => item.id === personId)
    || null;
});
const reviewDepartment = computed(() =>
  reviewPerson.value?.departmentPath?.join(' / ') || reviewPerson.value?.department || '');
const reviewSupervisor = computed(() => {
  const personId = action.value?.nextReview?.personId;
  if (!personId) return '';
  return directory.getPersonSupervisor(personId)?.person?.name || '';
});
</script>

<style scoped>
.review-new-tag {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--line, #e5ebf3);
  font-size: 13px;
  font-weight: 700;
  color: var(--muted, #667085);
}

.review-card-actions {
  margin-top: 10px;
}
</style>
