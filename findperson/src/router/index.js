import { createRouter, createWebHistory } from "vue-router";
import ImLayout from "../layouts/ImLayout.vue";
import MainLayout from "../layouts/MainLayout.vue";
import { useAuthStore } from "../stores/auth.js";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useReviewsStore } from "../stores/reviews.js";
import { useSessionsStore } from "../stores/sessions.js";

const routes = [
  { path: "/", redirect: "/im/chat" },
  { path: "/login", name: "login", component: () => import("../views/LoginView.vue") },
  {
    // ── 原生 IM 应用壳（产品形态；不复用 findperson 的 OA 壳）──
    path: "/im",
    component: ImLayout,
    children: [
      { path: "", redirect: { name: "im-chat" } },
      { path: "chat", name: "im-chat", component: () => import("../views/ChatView.vue") },
      { path: "todo", name: "im-todo", component: () => import("../views/TodoView.vue") },
      { path: "board", name: "im-board", component: () => import("../views/BoardView.vue") },
    ],
  },
  {
    // ── findperson 旧 web 壳（保留作测试对照：智能问答/名片库/个人中心等）──
    path: "/",
    component: MainLayout,
    children: [
      { path: "ask", name: "ask", component: () => import("../views/AskView.vue") },
      { path: "chat", name: "chat", component: () => import("../views/ChatView.vue") },
      { path: "todo", name: "todo", component: () => import("../views/TodoView.vue") },
      { path: "board", name: "board", component: () => import("../views/BoardView.vue") },
      { path: "directory", name: "directory", component: () => import("../views/DirectoryView.vue") },
      { path: "mine", name: "mine", component: () => import("../views/MineView.vue") },
      { path: "knowledge", name: "knowledge", component: () => import("../views/KnowledgeView.vue") },
      { path: "manual", name: "manual", component: () => import("../views/ManualView.vue") },
      { path: "profile/:id", name: "profile", component: () => import("../views/ProfileView.vue") },
      { path: "review", name: "review", component: () => import("../views/ReviewView.vue") },
      { path: "publish", name: "publish", component: () => import("../views/PublishView.vue") },
      { path: "content/:id", name: "contentDetail", component: () => import("../views/ContentDetailView.vue") },
      { path: "admin", name: "admin", component: () => import("../views/AdminView.vue") },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  document.body.classList.toggle("is-login-view", to.name === "login");
  await auth.bootstrap();
  if (to.name !== "login" && !auth.isLoggedIn) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  // 登录后默认进原生 IM 壳（产品形态）；旧 web 壳的页面仍可从 rail「问答」进入
  if (to.name === "login" && auth.isLoggedIn) return { name: "im-chat" };
  if (to.name === "login") return true;
  const sessions = useSessionsStore();
  sessions.init();
  // allSettled:任一数据接口失败不阻塞导航(仅 401 跳登录),避免页面假死
  const results = await Promise.allSettled([
    useDirectoryStore().loadPeople(),
    useContentStore().loadContents(),
    useReviewsStore().loadReviews(),
    useReviewsStore().loadPendingTags(),
    sessions.loadSessions(),
  ]);
  const authFailure = results.find(
    (r) => r.status === "rejected" && r.reason?.status === 401,
  );
  if (authFailure) {
    auth.clearSession();
    return { name: "login", query: { redirect: to.fullPath } };
  }
  results.forEach((r) => {
    if (r.status === "rejected") console.warn("数据加载失败(已放行导航):", r.reason);
  });
  if (to.name === "admin" && !auth.isAdmin) return { name: "ask" };
  return true;
});

export default router;
