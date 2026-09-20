<template>
  <el-form class="form-grid" :model="form" @submit.prevent>
    <label>姓名<el-input :model-value="person.name" disabled /></label>
    <label>部门<el-input :model-value="department?.path?.join(' / ') || person.department" disabled /></label>
    <label>职务<el-input :model-value="person.role" disabled /></label>
    <label>联系方式<el-input v-model="form.contact" /></label>
    <label class="wide">负责领域<el-input v-model="form.domainsText" placeholder="用顿号或逗号分隔" /></label>
    <label class="wide">自画像<el-input v-model="form.selfPortrait" type="textarea" :rows="5" /></label>
    <div class="form-actions wide">
      <el-button class="secondary-button" @click="$emit('cancel')">取消编辑</el-button>
      <el-button class="primary-button" type="primary" @click="$emit('save')">保存主页</el-button>
      <span role="status">{{ status }}</span>
    </div>
  </el-form>
</template>

<script setup>
defineProps({
  form: { type: Object, required: true },
  person: { type: Object, required: true },
  department: { type: Object, default: null },
  status: { type: String, default: "" },
});
defineEmits(["cancel", "save"]);
</script>
