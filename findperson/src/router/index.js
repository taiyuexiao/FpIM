import { createRouter, createWebHistory } from "vue-router";
import ImLayout from "../layouts/ImLayout.vue";
import { useAuthStore } from "../stores/auth.js";
import { useContentStore } from "../stores/content.js";
import { useDirectoryStore } from "../stores/directory.js";
import { useReviewsStore } from "../stores/reviews.js";
import { useSessionsStore } from "../stores/sessions.js";

// 单壳结构（ui-shell.md）：所有页面挂在 ImLayout 下；
// 旧页面 reparent 时【路由 name 不变】，全仓 push({name}) 无须改动。
// "chat" / "todo" / "board" 旧名与旧路径做重定向兼容。
const routes = [
  { path: "/", redirect: "/im/chat" },
  { path: "/login", name: "login", component: () => import("../views/LoginView.vue") },
  {
    path: "/im",
    component: ImLayout,
    children: [
      { path: "", redirect: { name: "im-chat" } },
      { path: "chat", name: "im-chat", component: () => import("../views/ChatView.vue") },
      { path: "contacts", name: "im-contacts", component: () => import("../views/ContactsView.vue") },
      { path: "todo", name: "im-todo", component: () => import("../views/TodoView.vue") },
      { path: "board", name: "im-board", component: () => import("../views/BoardView.vue") },
      // ── 旧 findperson 页面（内容不动，只换壳与皮肤；name 保持不变）──
      { path: "ask", name: "ask", component: () => import("../views/AskView.vue") },
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
  // ── 兼容：旧路由名（跨页代码仍可能 push({name:"chat"}) 等）──
  { path: "/chat", name: "chat", redirect: { name: "im-chat" } },
  { path: "/todo", name: "todo", redirect: { name: "im-todo" } },
  { path: "/board", name: "board", redirect: { name: "im-board" } },
  // ── 兼容：旧路径（书签 / 文档里的链接不失效）──
  { path: "/ask", redirect: "/im/ask" },
  { path: "/directory", redirect: "/im/directory" },
  { path: "/mine", redirect: "/im/mine" },
  { path: "/knowledge", redirect: "/im/knowledge" },
  { path: "/manual", redirect: "/im/manual" },
  { path: "/review", redirect: "/im/review" },
  { path: "/publish", redirect: "/im/publish" },
  { path: "/admin", redirect: "/im/admin" },
  {
    path: "/profile/:id",
    redirect: (to) => ({ path: `/im/profile/${to.params.id}`, query: to.query }),
  },
  {
    path: "/content/:id",
    redirect: (to) => ({ path: `/im/content/${to.params.id}`, query: to.query }),
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
  // 登录后默认进 IM 壳
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
