<template>
  <!-- FpIM 登录页（简洁版）：只换皮不改逻辑 -->
  <section class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="login-logo">Fp</div>
        <h1 class="login-title">FpIM</h1>
        <p class="login-sub">让每一次沟通，都成为解决问题的证据</p>
      </div>

      <div class="login-form">
        <label class="login-field">
          <span>工号</span>
          <input v-model="form.account" placeholder="请输入工号，如 P0004" autocomplete="username" />
        </label>
        <label class="login-field">
          <span>密码</span>
          <input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            @keydown.enter="login"
          />
        </label>
        <button class="login-btn" type="button" :disabled="!form.account || !form.password" @click="login">
          登录
        </button>
        <p v-if="status" class="login-status" role="status">{{ status }}</p>
      </div>

      <!-- 测试账号：仅开发模式；默认收起 -->
      <div v-if="demoAccounts.length" class="login-demo">
        <button type="button" class="login-demo-toggle" @click="showDemo = !showDemo">
          <span class="login-demo-caret" :class="{ open: showDemo }">▶</span>测试账号
        </button>
        <div v-if="showDemo" class="login-demo-list">
          <button
            v-for="item in demoAccounts"
            :key="item.account"
            type="button"
            class="login-demo-item"
            @click="quickFill(item)"
          >
            <strong>{{ item.name }}</strong>
            <span>{{ item.roleLabel }} · {{ item.account }}</span>
          </button>
        </div>
      </div>
    </div>
    <p class="login-foot">FpIM · 企业协作与问题闭环平台</p>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import logoUrl from "../../assets/logo.png";
import { useAuthStore } from "../stores/auth.js";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const form = reactive({ account: "", password: "" });
const status = ref("");

const showDemo = ref(false);
// 快捷登录：口令不入库，且只在开发模式生效（生产构建不读取 .env.fpim.local，不会把口令编进 bundle）
const demoPassword = import.meta.env.DEV ? (import.meta.env.VITE_DEMO_PASSWORD || "") : "";
const demoAccounts = demoPassword ? [
  { name: "冉紫萱", roleLabel: "管理员", account: "P0002", password: demoPassword },
  { name: "胡申民", roleLabel: "领导", account: "P0186", password: demoPassword },
  { name: "陈晨", roleLabel: "普通用户", account: "P0143", password: demoPassword },
] : [];

function quickFill(item) {
  form.account = item.account;
  form.password = item.password;
}

async function login() {
  const result = await auth.login(form);
  if (!result.ok) {
    status.value = result.message;
    return;
  }
  router.push(route.query.redirect || { name: "im-chat" });
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  gap: 20px;
}
.login-card {
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.login-logo {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--im-primary, #3370ff);
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}
.login-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 2px;
  color: var(--im-text-1, #1f2329);
}
.login-sub {
  margin: 0;
  font-size: 13px;
  color: var(--im-text-3, #8f959e);
}
.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.login-field span {
  font-size: 13px;
  color: var(--im-text-2, #646a73);
}
.login-field input {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--im-line-strong, rgba(31, 35, 41, 0.14));
  border-radius: 8px;
  font: inherit;
  font-size: 14px;
  color: var(--im-text-1, #1f2329);
  outline: none;
  background: #fff;
}
.login-field input::placeholder {
  color: var(--im-text-4, #bbbfc4);
}
.login-field input:focus {
  border-color: var(--im-primary, #3370ff);
}
.login-btn {
  height: 40px;
  border: none;
  border-radius: 8px;
  background: var(--im-primary, #3370ff);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.login-btn:hover {
  background: var(--im-primary-hover, #2860e1);
}
.login-btn:disabled {
  background: var(--im-primary-weak, #e8efff);
  color: var(--im-text-4, #bbbfc4);
  cursor: default;
}
.login-status {
  margin: 0;
  font-size: 12px;
  color: var(--im-danger, #f54a45);
  text-align: center;
}
.login-demo {
  border-top: 0.5px solid var(--im-line, rgba(31, 35, 41, 0.08));
  padding-top: 12px;
}
.login-demo-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 12px;
  color: var(--im-text-3, #8f959e);
  cursor: pointer;
}
.login-demo-caret {
  font-size: 9px;
  transition: transform 0.15s;
}
.login-demo-caret.open {
  transform: rotate(90deg);
}
.login-demo-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}
.login-demo-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: none;
  background: var(--im-bg-side, #f7f8fa);
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  color: var(--im-text-1, #1f2329);
}
.login-demo-item:hover {
  background: var(--im-hover, #f2f3f5);
}
.login-demo-item span {
  color: var(--im-text-3, #8f959e);
}
.login-foot {
  margin: 0;
  font-size: 12px;
  color: var(--im-text-4, #bbbfc4);
}
</style>
