<template>
  <article class="thread-bubble assistant-bubble">
    <span class="thread-role">首问助手</span>
    <p>{{ message.text }}</p>
    <div v-if="message.streaming" class="answer-skeleton"><span></span><span></span><span></span></div>
    <div v-if="message.analysis?.tokens?.length" class="thread-tags">
      <span v-for="tag in message.analysis.tokens.slice(0, 6)" :key="tag" class="tag">{{ tag }}</span>
    </div>
  </article>
</template>

<script setup>
defineProps({
  message: { type: Object, required: true },
});
</script>
