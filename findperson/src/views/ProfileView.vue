<template>
  <section class="view active">
    <ProfileDetail
      v-if="person"
      :person="person"
      :content="content.contentByOwner(person.id)"
      :reviews="reviews.reviewsForPerson(person.id)"
      :department="directory.getDepartment(person.department)"
      :supervisor="supervisor"
      :managed-departments="managedDepartments"
      @back="goBack"
      @content="openContent"
      @supervisor="openSupervisor"
    />
    <div v-else class="empty-state">没有找到该人员主页。</div>
  </section>
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ProfileDetail from "../components/ProfileDetail.vue";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useReviewsStore } from "../stores/reviews.js";
import { returnToSource } from "../utils/navigation.js";

const route = useRoute();
const router = useRouter();
const directory = useDirectoryStore();
const content = useContentStore();
const reviews = useReviewsStore();
const person = computed(() => directory.getPerson(route.params.id));
const supervisor = computed(() => directory.getPersonSupervisor(person.value?.id));
const managedDepartments = computed(() => directory.managedDepartments(person.value?.id));

// 他画像数据源修复:进入主页时拉取该人员收到的全部评价(任何访问者可见)
watch(person, (p) => { if (p?.id) reviews.loadPersonReviews(p.id); }, { immediate: true });

function goBack() {
  returnToSource(router, route, { name: "directory" });
}

function openContent(id) {
  router.push({ name: "contentDetail", params: { id }, query: { redirect: route.fullPath } });
}

function openSupervisor(id) {
  router.push({ name: "profile", params: { id }, query: { redirect: route.fullPath } });
}
</script>
