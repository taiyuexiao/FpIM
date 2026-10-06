<template>
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <img :src="logoUrl" alt="">
      </span>
      <div>
        <strong>首问必答平台</strong>
        <span>展示型交互 Demo</span>
      </div>
    </div>
    <nav class="sidebar-nav" aria-label="页面导航">
      <RouterLink v-for="item in visibleNavItems" :key="item.name" :to="{ name: item.name }" custom v-slot="{ href, navigate, isActive }">
        <a class="nav-button" :class="{ active: isActive }" :href="href" @click="navigate">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
          <em v-if="item.name === 'chat' && unread" class="nav-badge">{{ unread > 99 ? '99+' : unread }}</em>
          <em v-else-if="item.name === 'todo' && todoOpen" class="nav-badge">{{ todoOpen > 99 ? '99+' : todoOpen }}</em>
        </a>
      </RouterLink>
    </nav>
  </aside>
</template>

<script setup>
import { computed } from "vue";
import { ChatDotRound, ChatLineRound, Collection, DataAnalysis, Histogram, List } from "@element-plus/icons-vue";
import logoUrl from "../../../assets/logo.png";
import { useAuthStore } from "../../stores/auth.js";
import { useImStore } from "../../stores/im.js";
import { useIssuesStore } from "../../stores/issues.js";

const navItems = [
  { name: "chat", label: "消息", icon: ChatLineRound },
  { name: "todo", label: "待办", icon: List },
  { name: "board", label: "看板", icon: Histogram },
  { name: "ask", label: "智能问答", icon: ChatDotRound },
  { name: "directory", label: "名片库", icon: Collection },
  // { name: "knowledge", label: "知识库", icon: Reading },  // 按要求暂时隐藏(恢复时取消注释;路由 /knowledge 仍保留)
  { name: "admin", label: "后台管理", icon: DataAnalysis },
];
const auth = useAuthStore();
const im = useImStore();
const issues = useIssuesStore();
const unread = computed(() => im.totalUnread);
const todoOpen = computed(() => issues.assignedOpen);
const ADMIN_ONLY = ["admin"];
const visibleNavItems = computed(() => navItems.filter((item) => !ADMIN_ONLY.includes(item.name) || auth.isAdmin));
</script>
