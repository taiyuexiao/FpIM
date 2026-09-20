<template>
  <section class="view active vue-login-shell">
    <div class="login-shell">
      <div class="login-panel">
        <div class="login-brand">
          <span class="brand-mark" aria-hidden="true">
            <img :src="logoUrl" alt="">
          </span>
          <div>
            <h1>欢迎进入首问必答平台</h1>
            <!-- 测试账号:默认收起,点击小三角展开 -->
            <button type="button" class="demo-toggle" @click="showDemo = !showDemo">
              <span class="demo-triangle" :class="{ open: showDemo }">▶</span>测试账号
            </button>
            <div v-if="showDemo" class="demo-account-list">
              <p v-for="item in demoAccounts" :key="item.account">
                {{ item.name }}（{{ item.roleLabel }}）　账号：{{ item.account }}　密码：{{ item.password }}
              </p>
            </div>
          </div>
        </div>
        <el-form class="login-form" :model="form" @submit.prevent>
          <label>
            工号
            <el-input v-model="form.account" placeholder="请输入工号，如 P0001" />
          </label>
          <label>
            密码
            <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
          </label>
          <div class="login-actions">
            <el-button class="primary-button" type="primary" @click="login">登录</el-button>
            <span role="status">{{ status }}</span>
          </div>
        </el-form>
      </div>
    </div>
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

async function login() {
  const result = await auth.login(form);
  if (!result.ok) {
    status.value = result.message;
    return;
  }
  router.push(route.query.redirect || { name: "ask" });
}
</script>

<style scoped>
.demo-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--muted, #94a3b8);
  font-size: 14px;
  cursor: pointer;
}
.demo-toggle:hover { color: var(--blue, #1e63d6); }
.demo-triangle {
  display: inline-block;
  font-size: 10px;
  transition: transform 0.2s;
}
.demo-triangle.open { transform: rotate(90deg); }
.demo-account-list { margin-top: 6px; }
.demo-account-list p {
  margin: 2px 0;
  color: var(--muted, #94a3b8);
  font-size: 13px;
}
/* 登录按钮居中,状态文字移到下一行 */
.login-actions {
  flex-direction: column;
  justify-content: center;
  align-items: center;
}
</style>
