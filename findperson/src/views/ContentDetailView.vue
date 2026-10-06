<template>
  <section class="view active">
    <div class="page-heading detail-heading">
      <button class="secondary-button back-button" type="button" @click="goBack">返回</button>
      <div><h1>内容详情</h1></div>
    </div>
    <article v-if="visibleItem" class="content-detail content-detail-single">
      <div class="content-detail-head-single">
        <div class="content-hit-head">
          <div>
            <h1>{{ visibleItem.title }}</h1>
            <p class="content-detail-owner">{{ owner?.name || '未知发布人' }} · {{ visibleItem.publishedAt }}</p>
          </div>
          <div class="content-detail-status"><span class="status-chip" :class="statusClass(visibleItem.status)">{{ visibleItem.status }}</span><span v-if="visibleItem.pinned" class="pin-badge">置顶</span></div>
        </div>
        <div class="field-row">
          <span v-for="tag in visibleItem.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
      <div class="content-body content-body-merged">
        <h3>摘要</h3>
        <p>{{ visibleItem.summary }}</p>
        <h3>正文</h3>
        <p class="content-body-plain">{{ visibleItem.body }}</p>
        <div v-if="latestAudit" class="content-audit-note">
          <strong>审核信息</strong>
          <p>审核人：{{ latestAudit.reviewer }} · {{ latestAudit.auditedAt }}</p>
          <p v-if="latestAudit.reason">驳回原因：{{ latestAudit.reason }}</p>
        </div>
      </div>
      <div v-if="content.isOwnContent(visibleItem) && visibleItem.status === '已发布'" class="content-hit-actions">
        <el-button class="secondary-button small-button" @click="content.toggleContentPin(visibleItem.id)">
          {{ visibleItem.pinned ? '取消置顶' : '置顶' }}
        </el-button>
      </div>
    </article>
    <div v-else class="empty-state">没有找到内容，或当前账号无权查看。</div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useAuthStore } from "../stores/auth.js";
import { returnToSource } from "../utils/navigation.js";

const route = useRoute();
const router = useRouter();
const content = useContentStore();
const directory = useDirectoryStore();
const auth = useAuthStore();
const item = computed(() => content.getContent(route.params.id));
const visibleItem = computed(() => content.visibleContent(item.value, auth.userId, auth.isAdmin));
const owner = computed(() => directory.getPerson(visibleItem.value?.ownerId));
const latestAudit = computed(() => visibleItem.value?.auditTrail?.at(-1) || null);

function statusClass(status) {
  return status === "已发布" ? "status-published" : status === "待审核" ? "status-pending" : status === "草稿" ? "status-draft" : "status-rejected";
}

function goBack() {
  returnToSource(router, route, { name: "mine" });
}
</script>
