<template>
  <div v-if="cards.length" class="inline-card-group">
    <div class="inline-card-rail">
      <RecommendationCard
        v-for="card in cards"
        :key="card.id"
        :card="card"
        @profile="$emit('profile', $event)"
        @detail="$emit('detail', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import RecommendationCard from "./RecommendationCard.vue";

defineProps({
  cards: { type: Array, required: true },
});
defineEmits(["profile", "detail"]);
</script>
