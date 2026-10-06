<template>
  <el-form class="form-grid compact" :model="form" @submit.prevent>
    <label>标题<el-input v-model="form.title" /></label>
    <label>关联领域<el-input v-model="form.tagsText" placeholder="例如 大模型、Key 申请" /></label>
    <label>
      发布人
      <el-input :model-value="publisher" disabled />
    </label>
    <label class="wide">内容摘要<el-input v-model="form.summary" type="textarea" :rows="3" /></label>
    <label class="wide">发布内容<el-input v-model="form.body" type="textarea" :rows="8" /></label>
    <div class="form-actions wide">
      <el-button v-if="form.editingId" class="secondary-button" @click="$emit('delete')">删除内容</el-button>
      <el-button class="secondary-button" @click="$emit('save', 'draft')">保存草稿</el-button>
      <el-button class="primary-button" type="primary" @click="$emit('save', 'submit')">提交审核</el-button>
      <span role="status">{{ status }}</span>
    </div>
  </el-form>
</template>

<script setup>
defineProps({
  form: { type: Object, required: true },
  publisher: { type: String, required: true },
  status: { type: String, default: "" },
});
defineEmits(["save", "delete"]);
</script>
