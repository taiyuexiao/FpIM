<template>
  <el-dialog :model-value="modelValue" title="修改密码" width="540px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form class="form-grid compact-form" :model="form" @submit.prevent>
      <label class="wide">原密码<el-input v-model="form.currentPassword" type="password" show-password /></label>
      <label class="wide">新密码<el-input v-model="form.nextPassword" type="password" show-password /></label>
      <label class="wide">确认新密码<el-input v-model="form.confirmPassword" type="password" show-password /></label>
      <div class="form-actions wide">
        <el-button class="secondary-button" @click="$emit('update:modelValue', false)">取消</el-button>
        <el-button class="primary-button" type="primary" @click="$emit('submit')">确认修改</el-button>
        <span role="status">{{ status }}</span>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup>
defineProps({
  modelValue: Boolean,
  form: { type: Object, required: true },
  status: { type: String, default: "" },
});
defineEmits(["update:modelValue", "submit"]);
</script>
