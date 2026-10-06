<template>
  <section class="view active">
    <div class="page-heading"><div><h1>操作手册</h1></div></div>
    <div class="manual-grid">
      <article v-for="item in manualSections" :key="item.title" class="manual-card">
        <h3>{{ item.title }}</h3>
        <p>{{ item.body }}</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { manualSections } from "../state.js";
</script>
