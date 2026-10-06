<template>
  <section class="view active">
    <div class="page-heading detail-heading">
      <button class="secondary-button back-button" type="button" @click="goBack">返回</button>
      <div><h1>内容发布</h1></div>
    </div>
    <div class="publish-layout">
      <ContentForm :form="form" :publisher="auth.displayName" :status="status" @save="saveContent" @delete="deleteCurrent" />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import { useAuthStore } from "../stores/auth.js";
import ContentForm from "../components/content/ContentForm.vue";
import { useContentStore } from "../stores/content.js";
import { useDraftsStore } from "../stores/drafts.js";
import { returnToSource } from "../utils/navigation.js";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const content = useContentStore();
const drafts = useDraftsStore();
const status = ref("");
const form = reactive({ editingId: "", title: "", tagsText: "", summary: "", body: "" });
const formBaseline = ref("");
const isDirty = computed(() => JSON.stringify(form) !== formBaseline.value);

onMounted(() => {
  if (route.query.id) {
    const item = content.getContent(route.query.id);
    if (item && content.isOwnContent(item)) {
      Object.assign(form, {
        editingId: item.id,
        title: item.title,
        tagsText: item.tags.join("、"),
        summary: item.summary,
        body: item.body,
      });
    }
  }
  const savedDraft = drafts.get(route.query.draftId, "content");
  if (savedDraft) {
    const draft = savedDraft.payload || {};
    Object.assign(form, {
      editingId: "",
      title: draft.title || "",
      tagsText: (draft.tags || []).join("、"),
      summary: draft.summary || "",
      body: draft.body || "",
    });
  } else if (route.query.draft) {
    try {
      const draft = JSON.parse(decodeURIComponent(route.query.draft));
      Object.assign(form, {
        editingId: "",
        title: draft.title || "",
        tagsText: (draft.tags || []).join("、"),
        summary: draft.summary || "",
        body: draft.body || "",
      });
    } catch {
      // Ignore malformed draft query; user can fill manually.
    }
  }
  formBaseline.value = JSON.stringify(form);
});

async function saveContent(mode = "submit") {
  if (!form.title.trim() || (mode === "submit" && (!form.summary.trim() || !form.body.trim()))) {
    status.value = "请补齐标题、摘要和正文";
    return;
  }
  const record = await content.saveContent(form, mode);
  status.value = mode === "draft" ? "草稿已保存" : (form.editingId ? "修改已提交审核" : "内容已提交审核");
  form.editingId = record.id;
  formBaseline.value = JSON.stringify(form);
  drafts.remove(route.query.draftId);
}

async function deleteCurrent() {
  try {
    await ElMessageBox.confirm("删除后该内容将无法恢复，确认删除？", "删除内容", { type: "warning" });
    if (await content.deleteContent(form.editingId)) {
      formBaseline.value = JSON.stringify(form);
      returnToSource(router, route, { name: "mine" });
    }
  } catch {
    return;
  }
}

function goBack() {
  returnToSource(router, route, { name: "mine" });
}

onBeforeRouteLeave(async () => {
  if (!auth.isLoggedIn || !isDirty.value) return true;
  try {
    await ElMessageBox.confirm("当前内容尚未保存，确认离开？", "未保存修改", { type: "warning" });
    return true;
  } catch {
    return false;
  }
});
</script>
