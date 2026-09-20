<template>
  <!-- FpIM 原生应用壳：极左导航栏 + 内容区。不复用 findperson 的 OA 侧栏/顶栏。
       旧 web 壳（MainLayout + /ask 等）保留作测试对照，本壳是产品形态（将来套 Electron）。 -->
  <div class="im-app">
    <!-- ── 极左导航栏（飞书桌面端形态）── -->
    <nav class="im-rail">
      <button class="im-rail-avatar" :title="auth.name || auth.userId" @click="go('/mine')">
        {{ avatarText(auth.name || auth.userId) }}
      </button>

      <div class="im-rail-nav">
        <RouterLink v-for="item in railItems" :key="item.name" :to="{ name: item.name }" custom v-slot="{ isActive }">
          <button
            class="im-rail-btn"
            :class="{ active: isActive }"
            :title="item.label"
            @click="router.push({ name: item.name })"
          >
            <span class="im-rail-icon" v-html="item.icon"></span>
            <span class="im-rail-label">{{ item.label }}</span>
            <em v-if="item.name === 'im-chat' && unread" class="im-rail-badge">{{ unread > 99 ? "99+" : unread }}</em>
            <em v-else-if="item.name === 'im-todo' && todoOpen" class="im-rail-badge">{{ todoOpen > 99 ? "99+" : todoOpen }}</em>
          </button>
        </RouterLink>
      </div>

      <div class="im-rail-bottom">
        <button class="im-rail-btn" title="智能问答（旧 web 壳）" @click="go('/ask')">
          <span class="im-rail-icon">✦</span>
          <span class="im-rail-label">问答</span>
        </button>
        <button class="im-rail-btn" title="退出登录" @click="logout">
          <span class="im-rail-icon">⏻</span>
          <span class="im-rail-label">退出</span>
        </button>
      </div>
    </nav>

    <!-- ── 内容区：消息 / 待办 / 看板 ── -->
    <main class="im-app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";

import { avatarText } from "../services/im/format.js";
import { useAuthStore } from "../stores/auth.js";
import { useImStore } from "../stores/im.js";
import { useIssuesStore } from "../stores/issues.js";

const router = useRouter();
const auth = useAuthStore();
const im = useImStore();
const issues = useIssuesStore();

// IM 长连接与待办红点都挂在这个壳上（原生应用的全局生命周期）
let todoTimer = null;
onMounted(() => {
  im.init();
  issues.loadAssigned();
  todoTimer = setInterval(() => issues.loadAssigned(), 30000);
});
onUnmounted(() => {
  im.teardown();
  if (todoTimer) clearInterval(todoTimer);
});

const unread = computed(() => im.totalUnread);
const todoOpen = computed(() => issues.assignedOpen);

// 内联 SVG 图标（飞书风：线性、1.5px 描边感）
const ICON_CHAT = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12c0 4.4-4 8-9 8-1.2 0-2.3-.2-3.3-.5L3 21l1.6-3.6C3.6 16 3 14.1 3 12c0-4.4 4-8 9-8s9 3.6 9 8z"/></svg>`;
const ICON_TODO = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h9"/></svg>`;
const ICON_BOARD = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/></svg>`;

const railItems = [
  { name: "im-chat", label: "消息", icon: ICON_CHAT },
  { name: "im-todo", label: "待办", icon: ICON_TODO },
  { name: "im-board", label: "看板", icon: ICON_BOARD },
];

function go(path) {
  router.push(path);
}

async function logout() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<style>
/* 非 scoped：壳布局是全局性的 */
.im-app {
  height: 100vh;
  display: flex;
  background: #fff;
  overflow: hidden;
}
.im-app-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
}
.im-app-main > * {
  flex: 1;
  min-width: 0;
}

/* ── 极左导航栏 ── */
.im-rail {
  width: 64px;
  flex: 0 0 64px;
  background: var(--im-bg-rail, #f2f3f5);
  border-right: 0.5px solid var(--im-line, rgba(31, 35, 41, 0.08));
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0 10px;
  gap: 4px;
  /* Electron 桌面壳预留：顶部留拖拽区 */
  -webkit-app-region: drag;
}
.im-rail > * {
  -webkit-app-region: no-drag;
}
.im-rail-avatar {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: none;
  background: var(--im-primary, #3370ff);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 10px;
}
.im-rail-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.im-rail-bottom {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.im-rail-btn {
  position: relative;
  width: 52px;
  border: none;
  background: transparent;
  border-radius: 8px;
  padding: 7px 0 5px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  color: var(--im-text-2, #646a73);
  cursor: pointer;
  font-family: inherit;
}
.im-rail-btn:hover {
  background: rgba(31, 35, 41, 0.05);
}
.im-rail-btn.active {
  background: var(--im-primary-weak, #e8efff);
  color: var(--im-primary, #3370ff);
}
.im-rail-icon {
  display: inline-flex;
  line-height: 1;
  font-size: 18px;
}
.im-rail-label {
  font-size: 10px;
  line-height: 1.2;
  transform: scale(0.92);
}
.im-rail-badge {
  position: absolute;
  top: 2px;
  right: 4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #f54a45;
  color: #fff;
  font-size: 10px;
  font-style: normal;
  font-weight: 500;
  line-height: 16px;
  text-align: center;
}
</style>
