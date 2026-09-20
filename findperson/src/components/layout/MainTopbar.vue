<template>
  <div class="main-topbar">
    <el-popover placement="bottom-end" :width="360" trigger="click">
      <template #reference>
        <button class="topbar-icon-button notify-bell" type="button" aria-label="通知">
          <el-icon><Bell /></el-icon>
          <span v-if="pendingCount" class="notify-badge">{{ pendingCount }}</span>
        </button>
      </template>
      <div class="notify-panel">
        <div class="notify-title">通知</div>
        <div v-if="!reviews.pendingTags.length" class="empty-state compact">暂无新通知</div>
        <article v-for="item in reviews.pendingTags" :key="item.id" class="notify-item">
          <p class="notify-text">
            <strong>{{ item.reviewer }}</strong> 为你添加了新画像
            <span class="tag">{{ item.tag }}</span>
            <span class="notify-date">{{ item.date }}</span>
          </p>
          <div class="notify-actions">
            <el-button size="small" type="primary" @click="approve(item.id)">接受</el-button>
            <el-button size="small" @click="ignore(item.id)">忽略</el-button>
          </div>
        </article>
      </div>
    </el-popover>
    <el-dropdown trigger="click" @command="$emit('command', $event)">
      <button class="operator avatar-button" type="button" aria-label="用户菜单">
        <span class="avatar">{{ displayName.slice(0, 1) }}</span>
        <span class="operator-copy"><strong>{{ displayName }}</strong></span>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="mine">个人中心</el-dropdown-item>
          <el-dropdown-item command="password">修改密码</el-dropdown-item>
          <el-dropdown-item command="manual">操作手册</el-dropdown-item>
          <el-dropdown-item command="logout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { ElMessage } from "element-plus";
import { Bell } from "@element-plus/icons-vue";
import { useReviewsStore } from "../../stores/reviews.js";

defineProps({ displayName: { type: String, required: true } });
defineEmits(["command"]);

// 信任分级:铃铛弹窗展示"谁对你做了什么",支持就地放行/忽略
const reviews = useReviewsStore();
const pendingCount = computed(() => reviews.pendingTags.length);

async function approve(id) {
  await reviews.approveTag(id);
  ElMessage.success("已接受");
}
async function ignore(id) {
  await reviews.ignoreTag(id);
  ElMessage.success("已忽略");
}
</script>

<style scoped>
.notify-title { font-weight: 700; margin-bottom: 8px; }
.notify-item { padding: 8px 0; border-bottom: 1px solid #eef2f7; }
.notify-item:last-child { border-bottom: 0; }
.notify-text { margin: 0 0 6px; font-size: 13px; }
.notify-date { color: #94a3b8; font-size: 12px; margin-left: 6px; }
.notify-actions { display: flex; gap: 8px; }
</style>
