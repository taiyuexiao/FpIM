<template>
  <div class="app-shell">
    <AppSidebar />
    <main class="main-panel">
      <MainTopbar :display-name="auth.displayName" @command="handleAvatarCommand" />
      <div class="main-content">
        <RouterView />
      </div>
    </main>

    <ChangePasswordDialog v-model="isPasswordDialogOpen" :form="passwordForm" :status="passwordStatus" @submit="changePassword" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import AppSidebar from "../components/layout/AppSidebar.vue";
import ChangePasswordDialog from "../components/layout/ChangePasswordDialog.vue";
import MainTopbar from "../components/layout/MainTopbar.vue";
import { useAuthStore } from "../stores/auth.js";
import { useImStore } from "../stores/im.js";
import { useIssuesStore } from "../stores/issues.js";

const router = useRouter();
const auth = useAuthStore();
const im = useImStore();
const issues = useIssuesStore();
const isPasswordDialogOpen = ref(false);
const passwordStatus = ref("");
const passwordForm = reactive({ currentPassword: "", nextPassword: "", confirmPassword: "" });

// IM 长连接挂在布局层（而非会话页）：这样不论在哪个页面，未读角标都能实时更新
let todoTimer = null;
onMounted(() => {
  im.init();
  // 「待办」红点：我名下未结问题的数量，30s 轮询（问题变更频次低，不值得长连接）
  issues.loadAssigned();
  todoTimer = setInterval(() => issues.loadAssigned(), 30000);
});
onUnmounted(() => {
  im.teardown();
  if (todoTimer) clearInterval(todoTimer);
});

async function handleAvatarCommand(command) {
  if (command === "logout") {
    await auth.logout();
    router.push({ name: "login" });
    return;
  }
  if (command === "password") {
    passwordStatus.value = "";
    isPasswordDialogOpen.value = true;
    return;
  }
  router.push({ name: command });
}

async function changePassword() {
  const message = await auth.changePassword(passwordForm);
  passwordStatus.value = message || "密码已修改";
  if (!message) {
    passwordForm.currentPassword = "";
    passwordForm.nextPassword = "";
    passwordForm.confirmPassword = "";
  }
}
</script>
