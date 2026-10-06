<template>
  <section class="view active">
    <div class="page-heading detail-heading">
      <button class="secondary-button back-button" type="button" @click="goBack">返回</button>
      <div><h1>为他人画像</h1></div>
    </div>
    <el-form class="form-grid" :model="form" @submit.prevent>
      <label>
        同事
        <el-select v-model="form.personId">
          <el-option v-for="person in reviewablePeople" :key="person.id" :label="person.name" :value="person.id" />
        </el-select>
      </label>
      <label>日期<el-input v-model="form.date" type="date" /></label>
      <label class="wide">
        事项
        <el-select v-model="form.tag" filterable placeholder="搜索或选择事项">
          <el-option v-for="item in personTags" :key="item.tag" :label="item.tag" :value="item.tag" />
          <el-option label="其他" :value="OTHER_TAG" />
        </el-select>
      </label>
      <label v-if="form.tag === OTHER_TAG" class="wide">
        填写事项
        <el-input v-model="form.customTag" maxlength="20" show-word-limit placeholder="请输入事项" />
      </label>
      <div class="form-actions wide">
        <el-button class="primary-button" type="primary" @click="saveReview">添加事项</el-button>
        <el-button class="secondary-button" @click="goBack">取消</el-button>
        <span role="status">{{ status }}</span>
      </div>
    </el-form>
    <div class="profile-detail review-history-panel">
      <section>
        <h2>我添加的事项</h2>
        <SentReviewList :reviews="reviews.sentReviews" :people="directory.people" @continue="continueReview" @delete="deleteReview" />
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import { getActiveUserId, getTodayText } from "../state.js";
import SentReviewList from "../components/profile/SentReviewList.vue";
import { useDirectoryStore } from "../stores/directory.js";
import { useReviewsStore } from "../stores/reviews.js";
import { useDraftsStore } from "../stores/drafts.js";
import { useAuthStore } from "../stores/auth.js";
import { returnToSource } from "../utils/navigation.js";

const router = useRouter();
const route = useRoute();
const directory = useDirectoryStore();
const reviews = useReviewsStore();
const drafts = useDraftsStore();
const auth = useAuthStore();
const reviewablePeople = computed(() => directory.activePeople.filter((person) => person.id !== getActiveUserId()));
const OTHER_TAG = "__other__";
const form = reactive({ personId: reviewablePeople.value[0]?.id || "", date: getTodayText(), tag: "", customTag: "", id: "" });
const status = ref("");
const formBaseline = ref("");
const hydrating = ref(false);
const isDirty = computed(() => JSON.stringify(form) !== formBaseline.value);
const personTags = computed(() => {
  const person = directory.getPerson(form.personId);
  const selfTags = (person?.domains || []).map((tag) => ({ tag }));
  const existingTags = reviews.tagsForPerson(form.personId)
    .filter((item) => !selfTags.some((selfTag) => selfTag.tag === item.tag));
  return [...selfTags, ...existingTags];
});

watch(() => form.personId, () => {
  if (hydrating.value) return;
  form.tag = "";
  form.customTag = "";
});

async function saveReview() {
  if (!form.personId) {
    status.value = "请选择同事";
    return;
  }
  if (!form.date) {
    status.value = "请选择日期";
    return;
  }
  const tag = form.tag === OTHER_TAG ? form.customTag : form.tag;
  const result = await reviews.saveReview({ ...form, tag });
  status.value = result.ok ? "事项已添加" : result.message;
  if (result.ok) {
    form.id = "";
    form.tag = "";
    form.customTag = "";
    form.date = getTodayText();
    formBaseline.value = JSON.stringify(form);
    drafts.remove(route.query.draftId);
  }
}

function continueReview(review) {
  Object.assign(form, {
    id: review.id,
    personId: review.personId,
    date: review.date,
    tag: reviews.tagFor(review),
    customTag: "",
  });
  status.value = "";
}

async function deleteReview(id) {
  try {
    await ElMessageBox.confirm("确认删除这条他画像事项？", "删除事项", { type: "warning" });
    await reviews.deleteReview(id);
  } catch {
    return;
  }
}

function goBack() {
  returnToSource(router, route, { name: "mine" });
}

onMounted(async () => {
  const draft = drafts.get(route.query.draftId, "review");
  if (draft) {
    const payload = draft.payload || {};
    hydrating.value = true;
    form.personId = payload.personId || form.personId;
    await nextTick();
    const tag = String(payload.tag || payload.text || "").trim();
    const knownTag = personTags.value.some((item) => item.tag === tag);
    Object.assign(form, {
      date: payload.date || form.date,
      tag: knownTag ? tag : (tag ? OTHER_TAG : ""),
      customTag: knownTag ? "" : tag,
      id: payload.id || "",
    });
    hydrating.value = false;
  }
  formBaseline.value = JSON.stringify(form);
});

onBeforeRouteLeave(async () => {
  if (!auth.isLoggedIn || !isDirty.value) return true;
  try {
    await ElMessageBox.confirm("当前他画像事项尚未保存，确认离开？", "未保存修改", { type: "warning" });
    return true;
  } catch {
    return false;
  }
});
</script>
