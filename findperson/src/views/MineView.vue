<template>
  <section class="view active">
    <div class="page-heading"><div><h1>个人中心</h1></div></div>
    <div v-if="!isEditing" class="profile-detail">
      <ProfileSummary :person="profile" :supervisor="supervisor" @supervisor="openSupervisor">
        <template #actions>
          <el-button class="secondary-button small-button" @click="openReview">为他人画像</el-button>
          <el-button class="primary-button small-button" type="primary" :icon="EditPen" @click="openPublish">发布</el-button>
          <el-button class="secondary-button small-button" @click="startEdit">编辑</el-button>
        </template>
      </ProfileSummary>

      <!-- 数据画像：与他人主页同源同构（PRD F2 合并的第一步：数据同源、视觉同构） -->
      <ProfileStats :person-id="auth.userId" />

      <!-- ── 我的问题(问题跟踪:未联系/处理中/已解决/未解决;IM 化后从「进会话」继续推进) ── -->
      <section class="profile-block issues-block">
        <div class="content-section-head">
          <div>
            <h2>我的问题</h2>
            <p v-if="!issuesCollapsed" class="person-meta">把问答里问过的事归档到这里，跟进到有人负责、有结果</p>
          </div>
          <div class="issues-head-actions">
            <span v-if="issues.total" class="issues-stat">共 {{ issues.total }} 条 · 已解决 {{ issues.counts.resolved }}</span>
            <el-button class="secondary-button small-button" :loading="issues.syncing" @click="syncIssues">
              {{ issues.syncing ? '同步中…' : '从对话同步' }}
            </el-button>
            <el-button class="secondary-button small-button" @click="toggleIssuesCollapsed">
              {{ issuesCollapsed ? '展开 ▾' : '收起 ▴' }}
            </el-button>
          </div>
        </div>
        <template v-if="!issuesCollapsed">
          <div class="issues-tabs">
            <button v-for="tab in ISSUE_TABS" :key="tab.value" type="button"
                    class="issues-tab" :class="{ 'is-active': issues.filter === tab.value }"
                    @click="issues.setFilter(tab.value)">
              {{ tab.label }}<em v-if="tab.value && issues.counts[tab.value]"> {{ issues.counts[tab.value] }}</em>
            </button>
          </div>
          <p v-if="issues.loading" class="empty-state">加载中…</p>
          <p v-else-if="!issues.items.length" class="empty-state">
            还没有归档的问题。点「从对话同步」，系统会把你问过的问题筛一遍后放进来。
          </p>
          <div v-else class="issues-list">
          <article v-for="item in issues.items" :key="item.id" class="issue-item">
            <div class="issue-line">
              <p class="issue-question">{{ item.summary || item.question }}</p>
              <span class="issue-status" :class="`is-${item.status}`">{{ issues.statusText(item.status) }}</span>
            </div>
            <p class="issue-meta">
              <span v-if="item.assigneeName">责任人：{{ item.assigneeName }}</span>
              <span v-if="item.repeatedCount > 1">被问 {{ item.repeatedCount }} 次</span>
              <span v-if="item.resolutionNote">结果：{{ item.resolutionNote }}</span>
              <span>{{ formatIssueTime(item.lastActionAt) }}</span>
            </p>
            <div class="issue-actions">
              <el-button v-if="item.status !== 'processing'" class="secondary-button small-button" @click="markIssue(item, 'processing')">处理中</el-button>
              <el-button v-if="item.status !== 'resolved'" class="secondary-button small-button" @click="markIssue(item, 'resolved')">已解决</el-button>
              <el-button v-if="item.status !== 'unresolved'" class="secondary-button small-button" @click="markIssue(item, 'unresolved')">未解决</el-button>
              <el-button class="primary-button small-button" type="primary" @click="openIssueChat(item)">进会话</el-button>
              <el-button class="secondary-button small-button" @click="toggleIssueDetail(item)">
                {{ expandedIssueId === item.id ? '收起' : '处理过程' }}
              </el-button>
            </div>
            <div v-if="expandedIssueId === item.id" class="issue-timeline">
              <p v-if="replySuggestion(item)" class="issue-suggestion">
                对方已回复，系统判断<span class="sug-strong">{{ replySuggestion(item).seems_resolved ? '可能已解决' : '需要继续跟进' }}</span>
                ：{{ replySuggestion(item).summary }}
                <span class="sug-actions">
                  <el-button class="primary-button small-button" type="primary" @click="markIssue(item, 'resolved')">确认已解决</el-button>
                  <el-button class="secondary-button small-button" @click="markIssue(item, 'processing')">继续跟进</el-button>
                </span>
              </p>
              <div v-for="ev in issueDetail(item.id).events" :key="ev.id" class="issue-event">
                <span class="issue-event-type">{{ eventText(ev.eventType) }}</span>
                <span class="issue-event-detail">{{ ev.detail }}</span>
                <span class="issue-event-time">{{ formatIssueTime(ev.createdAt) }}</span>
              </div>
              <p v-if="!issueDetail(item.id).events.length" class="empty-state">暂无记录。</p>
            </div>
          </article>
          </div>
        </template>
      </section>

      <section v-if="department && isLeader" class="profile-block department-responsibility-block">
        <div class="content-section-head"><div><h2>部门职责</h2><p class="person-meta">{{ canManageResponsibilities ? '负责部门及下级部门职责' : department.name }}</p></div></div>
        <div v-if="canManageResponsibilities" class="responsibility-manager">
          <div class="responsibility-filter-row">
            <el-select v-model="responsibilityFilter" class="responsibility-filter" clearable placeholder="筛选部门">
              <el-option label="全部负责部门" value="" />
              <el-option v-for="item in responsibilityOptions" :key="item.id" :label="item.path.join(' / ')" :value="item.id" />
            </el-select>
          </div>
          <div class="responsibility-list">
            <article v-for="item in visibleResponsibilities" :key="item.id" class="responsibility-item">
              <div class="responsibility-item-head"><div><h3>{{ item.name }}</h3><p>{{ item.path.join(' / ') }}</p></div><el-button class="secondary-button small-button" @click="startResponsibilityEdit(item)">{{ editingResponsibilityId === item.id ? '取消' : '编辑' }}</el-button></div>
              <template v-if="editingResponsibilityId === item.id">
                <el-input v-model="responsibilityDrafts[item.id]" type="textarea" :rows="3" placeholder="请输入部门职责" />
                <div class="responsibility-item-actions"><el-button class="primary-button small-button" type="primary" @click="saveResponsibility(item)">保存职责</el-button></div>
              </template>
              <p v-else class="responsibility-copy">{{ item.responsibility || '暂未维护部门职责。' }}</p>
            </article>
          </div>
        </div>
        <p v-else>{{ department.responsibility || '暂未维护部门职责。' }}</p>
      </section>

      <div class="portrait-split-grid profile-portrait-split-grid">
        <section class="profile-block self-portrait-block">
          <h2>自画像</h2>
          <p>{{ profile.selfPortrait }}</p>
        </section>
        <section class="profile-block peer-portrait-block">
          <h2>他画像</h2>
          <PeerReviewList :reviews="myPeerReviews" empty-text="暂时还没有收到他画像评价。" />
        </section>
      </div>

      <section class="profile-block">
        <div class="content-section-head">
          <h2>发布内容</h2>
          <el-button class="secondary-button small-button" @click="toggleSearch">{{ isSearchOpen ? '收起搜索' : '搜索' }}</el-button>
        </div>
        <div v-if="isSearchOpen" class="search-field mine-search-field mine-search-bar">
          <el-icon><Search /></el-icon>
          <el-input v-model="keyword" placeholder="搜索本人发布内容" clearable />
        </div>
        <div class="content-card-grid">
          <article v-for="item in content.filteredMyContent(keyword)" :key="item.id" class="content-mini-card clickable-card" @click="openContent(item.id)">
            <div class="content-mini-head">
              <h3>{{ item.title }}</h3>
              <span v-if="item.pinned" class="pin-badge">置顶</span>
              <span class="status-chip" :class="statusClass(item.status)">{{ item.status }}</span>
            </div>
            <p>{{ item.summary }}</p>
            <div class="field-row">
              <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <div class="content-mini-actions" @click.stop>
              <el-button class="secondary-button small-button" @click="editContent(item.id)">编辑</el-button>
              <el-button class="secondary-button small-button" @click="deleteContent(item.id)">删除</el-button>
              <el-button v-if="item.status === '已发布'" class="secondary-button small-button" @click="content.toggleContentPin(item.id)">{{ item.pinned ? '取消置顶' : '置顶' }}</el-button>
            </div>
          </article>
          <div v-if="!content.filteredMyContent(keyword).length" class="empty-state">暂时还没有匹配的本人发布内容。</div>
        </div>
      </section>
    </div>

    <ProfileEditor v-else :form="form" :person="profile" :department="department" :status="status" @cancel="cancelEdit" @save="saveProfile" />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { EditPen, Search } from "@element-plus/icons-vue";
import PeerReviewList from "../components/profile/PeerReviewList.vue";
import ProfileEditor from "../components/profile/ProfileEditor.vue";
import ProfileStats from "../components/profile/ProfileStats.vue";
import ProfileSummary from "../components/profile/ProfileSummary.vue";
import { getActiveUserId } from "../state.js";
import { useAuthStore } from "../stores/auth.js";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useReviewsStore } from "../stores/reviews.js";
import { useDraftsStore } from "../stores/drafts.js";
import { ISSUE_TABS, useIssuesStore } from "../stores/issues.js";
import { useImStore } from "../stores/im.js";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const directory = useDirectoryStore();
const content = useContentStore();
const reviews = useReviewsStore();
const drafts = useDraftsStore();
const issues = useIssuesStore();

// ── 我的问题(问题跟踪) ──
const ISSUES_COLLAPSE_KEY = "mine.issuesCollapsed";
// 默认收起(占地方);用户展开过就记住选择
const issuesCollapsed = ref(localStorage.getItem(ISSUES_COLLAPSE_KEY) !== "0");
function toggleIssuesCollapsed() {
  issuesCollapsed.value = !issuesCollapsed.value;
  localStorage.setItem(ISSUES_COLLAPSE_KEY, issuesCollapsed.value ? "1" : "0");
}
const expandedIssueId = ref(null);
const im = useImStore();
const EVENT_TEXTS = {
  created: "归档",
  synced: "重复提问",
  status_changed: "状态变更",
  mail_sent: "发出邮件",
  mail_received: "收到回信",
  note: "备注",
  candidate_created: "进入沉淀",
};
const eventText = (type) => EVENT_TEXTS[type] || type;
function formatIssueTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}
async function syncIssues() {
  try {
    const result = await issues.sync();
    ElMessage.success(`同步完成：新增 ${result.created} 条，合并重复 ${result.merged} 条，过滤无效 ${result.invalid} 条`);
  } catch (error) {
    ElMessage.error(error?.message || "同步失败，请稍后重试");
  }
}
async function markIssue(item, status) {
  try {
    await issues.setStatus(item.id, status);
    ElMessage.success(status === "resolved" ? "已标记解决，并进入知识沉淀候选" : `已标记为「${issues.statusText(status)}」`);
  } catch (error) {
    ElMessage.error(error?.message || "更新失败");
  }
}
async function toggleIssueDetail(item) {
  if (expandedIssueId.value === item.id) {
    expandedIssueId.value = null;
    return;
  }
  expandedIssueId.value = item.id;
  try {
    await issues.loadDetail(item.id);
  } catch {
    // 详情拉取失败保持展开，用户可重试
  }
}
const issueDetail = (id) => issues.details[id] || { events: [], mails: [] };
function replySuggestion(item) {
  const mail = (issues.details[item.id]?.mails || []).find((m) => m.direction === "in" && m.analysis);
  return mail?.analysis || null;
}
/** 进入会话：取或建与责任人的单聊，并把该问题挂到会话上（IM 化后取代原「发邮件」） */
async function openIssueChat(item) {
  if (!item.assigneePersonId) {
    ElMessage.warning("该问题还没有责任人。先在智能问答里搜到人、从他的名片发起会话。");
    return;
  }
  try {
    await im.openWith(item.assigneePersonId, item.id);
    router.push({ name: "chat" });
  } catch (error) {
    ElMessage.error(error?.message || "进入会话失败");
  }
}
const isEditing = ref(false);
const isSearchOpen = ref(false);
const keyword = ref("");
const status = ref("");
const form = reactive({ contact: "", domainsText: "", selfPortrait: "" });
const formBaseline = ref("");
const isFormDirty = computed(() => isEditing.value && JSON.stringify(form) !== formBaseline.value);
const profile = computed(() => directory.currentUser);
const supervisor = computed(() => directory.getPersonSupervisor(profile.value?.id));
const department = computed(() => directory.getDepartment(profile.value?.department));
const managedRoots = computed(() => directory.managedDepartments(auth.userId));
const canManageResponsibilities = computed(() => managedRoots.value.length > 0);
/** 领导判定:管理的部门中有"xx部"(L2/L3部负责人),或本人属总经理室;L4组长与普通成员不显示部门职责栏目 */
const isLeader = computed(() =>
  managedRoots.value.some((d) => d.name.endsWith("部"))
  || profile.value?.department === "总经理室"
);
const responsibilityFilter = ref("");
const responsibilityDrafts = reactive({});
const responsibilityOptions = computed(() => directory.manageableDepartments(auth.userId));
const visibleResponsibilities = computed(() => responsibilityFilter.value
  ? responsibilityOptions.value.filter((item) => item.id === responsibilityFilter.value)
  : responsibilityOptions.value);
const editingResponsibilityId = ref("");
const myPeerReviews = computed(() => reviews.reviewsForPerson(getActiveUserId()));
watch(visibleResponsibilities, (items) => items.forEach((item) => {
  if (responsibilityDrafts[item.id] === undefined) responsibilityDrafts[item.id] = item.responsibility || "";
}), { immediate: true });
function startEdit() {
  Object.assign(form, {
    contact: profile.value.contact,
    domainsText: profile.value.domains.join("、"),
    selfPortrait: profile.value.selfPortrait,
  });
  status.value = "";
  formBaseline.value = JSON.stringify(form);
  isEditing.value = true;
}

function saveProfile() {
  auth.updateProfile(form);
  status.value = "已保存";
  formBaseline.value = JSON.stringify(form);
  drafts.remove(route.query.draftId);
  isEditing.value = false;
}

function cancelEdit() {
  drafts.remove(route.query.draftId);
  isEditing.value = false;
}

function saveResponsibility(item) {
  directory.updateDepartment(item.id, { responsibility: (responsibilityDrafts[item.id] || "").trim() });
  editingResponsibilityId.value = "";
}

function startResponsibilityEdit(item) {
  if (editingResponsibilityId.value === item.id) {
    editingResponsibilityId.value = "";
    return;
  }
  responsibilityDrafts[item.id] = item.responsibility || "";
  editingResponsibilityId.value = item.id;
}

function toggleSearch() {
  isSearchOpen.value = !isSearchOpen.value;
  if (!isSearchOpen.value) keyword.value = "";
}

function statusClass(status) {
  return status === "已发布" ? "status-published" : status === "待审核" ? "status-pending" : status === "草稿" ? "status-draft" : "status-rejected";
}

function openContent(id) {
  router.push({ name: "contentDetail", params: { id }, query: { redirect: route.fullPath } });
}

function openSupervisor(id) {
  router.push({ name: "profile", params: { id }, query: { redirect: route.fullPath } });
}

async function deleteContent(id) {
  try {
    await ElMessageBox.confirm("删除后该内容将无法恢复，确认删除？", "删除内容", { type: "warning" });
    await content.deleteContent(id);
  } catch {
    return;
  }
}

function openReview() {
  router.push({ name: "review", query: { redirect: route.fullPath } });
}

function openPublish() {
  router.push({ name: "publish", query: { redirect: route.fullPath } });
}

function editContent(id) {
  router.push({ name: "publish", query: { id, redirect: route.fullPath } });
}

onMounted(() => {
  issues.load();  // 我的问题:归档列表(IM 化后已恢复显示)
  reviews.loadPendingTags();  // 信任分级:待放行标签通知
  reviews.loadPersonReviews(getActiveUserId());  // 他画像:拉我收到的全部评价
  const draft = drafts.get(route.query.draftId, "profile");
  if (route.query.edit !== "profile" || !draft) return;
  startEdit();
  const patch = draft.payload || {};
  if (patch.contact !== undefined) form.contact = patch.contact;
  if (patch.domainsText !== undefined) form.domainsText = patch.domainsText;
  if (patch.addDomains?.length) form.domainsText = Array.from(new Set([...profile.value.domains, ...patch.addDomains])).join("、");
  if (patch.selfPortrait !== undefined) form.selfPortrait = patch.selfPortrait;
});

onBeforeRouteLeave(async () => {
  if (!auth.isLoggedIn || !isFormDirty.value) return true;
  try {
    await ElMessageBox.confirm("当前资料修改尚未保存，确认离开？", "未保存修改", { type: "warning" });
    return true;
  } catch {
    return false;
  }
});
</script>

<style scoped>
/* ── 我的问题(问题跟踪) ── */
.issues-block { position: relative; }
.issues-head-actions { display: inline-flex; align-items: center; gap: 10px; }
.issues-stat { color: var(--text-secondary, #666); font-size: 13px; }
.issues-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 12px; }
.issues-tab {
  padding: 4px 12px; border: 1px solid var(--border-color, #dcdfe6); border-radius: 14px;
  background: transparent; color: var(--text-secondary, #666); font-size: 13px; cursor: pointer;
  transition: all 0.15s ease;
}
.issues-tab.is-active { border-color: #4a7dff; color: #4a7dff; background: #f0f4ff; }
.issues-tab em { font-style: normal; margin-left: 4px; }
.issues-list { display: flex; flex-direction: column; gap: 10px; }
.issue-item { border: 1px solid var(--border-color, #eef2f7); border-radius: 8px; padding: 10px 12px; }
.issue-line { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.issue-question { margin: 0; font-weight: 600; color: #303133; }
.issue-status {
  flex: 0 0 auto; padding: 2px 8px; border-radius: 10px; font-size: 12px; line-height: 1.6;
  background: #f2f3f5; color: #606266;
}
.issue-status.is-processing { background: #eef3ff; color: #4a7dff; }
.issue-status.is-resolved { background: #eafaf0; color: #1f9d55; }
.issue-status.is-unresolved { background: #fdf0f0; color: #d64545; }
.issue-meta {
  display: flex; flex-wrap: wrap; gap: 12px; margin: 6px 0 8px;
  color: var(--text-secondary, #909399); font-size: 12px;
}
.issue-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.issue-timeline {
  margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--border-color, #e4e7ed);
  display: flex; flex-direction: column; gap: 6px;
}
.issue-suggestion {
  margin: 0 0 4px; padding: 8px 10px; border-radius: 6px; background: #f7f9ff;
  color: #303133; font-size: 13px; line-height: 1.6;
}
.sug-strong { color: #4a7dff; font-weight: 600; margin: 0 2px; }
.sug-actions { display: inline-flex; gap: 6px; margin-left: 8px; vertical-align: middle; }
.issue-event { display: flex; gap: 10px; font-size: 12px; color: var(--text-secondary, #606266); }
.issue-event-type { flex: 0 0 auto; color: #303133; font-weight: 600; }
.issue-event-detail { flex: 1 1 auto; }
.issue-event-time { flex: 0 0 auto; color: #c0c4cc; }

.pending-tags-block { width: 100%; }
.pending-tag-item {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 0; border-bottom: 1px solid #eef2f7;
}
.pending-tag-item:last-child { border-bottom: 0; }
.pending-tag-actions { display: inline-flex; gap: 8px; flex: 0 0 auto; }
</style>
