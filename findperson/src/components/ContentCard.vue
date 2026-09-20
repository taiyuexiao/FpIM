<!-- 内容卡片：用于个人中心、人员主页和问答关联内容展示 -->
<template>
  <article class="content-hit-card clickable-card" @click="$emit('open')">
    <div class="content-hit-head">
      <div>
        <h3>{{ item.title }}</h3>
        <p class="person-meta">{{ owner?.name || '未知发布人' }} · {{ item.publishedAt }}</p>
      </div>
      <span v-if="item.pinned" class="pin-badge">置顶</span>
    </div>
    <div class="field-row">
      <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
    </div>
    <p>{{ item.summary }}</p>
    <div class="content-hit-actions" @click.stop>
      <button class="secondary-button small-button" type="button" @click="$emit('open')">查看详情</button>
      <button v-if="manage" class="secondary-button small-button" type="button" @click="$emit('edit')">编辑</button>
      <button v-if="manage" class="secondary-button small-button" type="button" @click="$emit('delete')">删除</button>
      <button v-if="manage || showPin" class="secondary-button small-button" type="button" @click="$emit('pin')">
        {{ item.pinned ? '取消置顶' : '置顶' }}
      </button>
    </div>
  </article>
</template>

<script setup>
defineProps({
  /** 内容对象 */
  item: Object,
  /** 发布人对象 */
  owner: Object,
  /** 全局反馈数据 */
  feedback: Object,
  /** 是否显示管理按钮（编辑、删除） */
  manage: Boolean,
  /** 是否显示置顶按钮 */
  showPin: Boolean,
});
defineEmits(['open', 'edit', 'delete', 'pin']);
</script>
