<template>
  <div v-if="portraitTags.length" class="portrait-tag-list" aria-label="他画像事项">
    <span
      v-for="item in portraitTags"
      :key="item.tag"
      class="portrait-tag"
      :class="{ 'portrait-tag-pending': item.status === 'pending' }"
      :title="item.tooltip"
    >
      {{ item.tag }}<i v-if="item.status === 'pending'" class="pending-dot" title="待放行" />
    </span>
  </div>
  <div v-else class="empty-state">{{ emptyText }}</div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  reviews: { type: Array, required: true },
  emptyText: { type: String, default: "暂无他画像。" },
});

// 他画像只展示标签;鼠标移上去显示是谁打的(待放行的标注状态)
const portraitTags = computed(() => {
  const grouped = new Map();
  props.reviews.forEach((review) => {
    const tag = String(review.tag || "").trim();
    if (!tag) return;
    const entry = grouped.get(tag) || { tag, status: review.status || "approved", reviewers: new Set(), latestDate: review.date };
    if (review.status === "pending") entry.status = "pending";
    if (review.reviewer) entry.reviewers.add(review.reviewer);
    if (String(review.date) > String(entry.latestDate)) entry.latestDate = review.date;
    grouped.set(tag, entry);
  });
  return [...grouped.values()]
    .map((entry) => ({
      ...entry,
      tooltip: `${[...entry.reviewers].join("、")} 打的标签${entry.status === "pending" ? "(待放行)" : ""}`,
    }))
    .sort((left, right) => String(right.latestDate).localeCompare(String(left.latestDate)));
});
</script>

<style scoped>
.portrait-tag-pending {
  border-style: dashed;
  opacity: 0.75;
}
.pending-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 4px;
  border-radius: 50%;
  background: #f59e0b;
  vertical-align: middle;
}
</style>
