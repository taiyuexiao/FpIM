<template>
  <div class="sent-review-list">
    <article v-for="review in reviews" :key="review.id" class="sent-review-item">
      <div class="sent-review-meta">
        <strong>{{ personName(review.personId) }}</strong>
        <time>{{ review.date }}</time>
      </div>
      <p class="sent-review-tag">{{ review.tag || review.text }}</p>
      <div class="form-actions">
        <el-button class="secondary-button small-button" @click="$emit('continue', review)">继续补充</el-button>
        <el-button class="secondary-button small-button" @click="$emit('delete', review.id)">删除</el-button>
      </div>
    </article>
    <div v-if="!reviews.length" class="empty-state">暂时还没有添加事项。</div>
  </div>
</template>

<script setup>
const props = defineProps({
  reviews: { type: Array, required: true },
  people: { type: Array, required: true },
});
defineEmits(["continue", "delete"]);

function personName(personId) {
  return props.people.find((person) => person.id === personId)?.name || "未知人员";
}
</script>
