<!-- 邮件编辑弹窗:打开即请求后端(DeepSeek)按推荐上下文代拟草稿,可编辑后经 SMTP 发送 -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="`给 ${person?.name || ''} 写邮件`"
    width="560px"
    append-to-body
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" element-loading-text="智能体正在撰写邮件...">
      <div class="mail-field">
        <label>收件人</label>
        <div class="mail-recipient">{{ person?.name }} &lt;{{ person?.email || '未配置邮箱' }}&gt;</div>
      </div>
      <div class="mail-field">
        <label>主题</label>
        <input v-model="subject" class="mail-input" :disabled="loading" placeholder="邮件主题" />
      </div>
      <div class="mail-field">
        <label>正文</label>
        <textarea v-model="body" class="mail-input mail-body" rows="12" :disabled="loading"
                  :placeholder="autoDraft ? '邮件正文(智能体将根据你的问题自动撰写)' : '请输入邮件正文'"></textarea>
      </div>
      <p v-if="errorText" class="mail-error">{{ errorText }}</p>
    </div>
    <template #footer>
      <div class="mail-footer">
        <el-button v-if="autoDraft" size="small" :disabled="loading || sending" @click="generateDraft">重新生成</el-button>
        <span class="mail-footer-spacer"></span>
        <el-button size="small" :disabled="loading || sending" @click="$emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" size="small" :loading="sending"
                   :disabled="loading || !person?.email || !subject.trim() || !body.trim()"
                   @click="send">{{ sending ? '发送中...' : '发送' }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { draftMail, sendMail } from "../../services/api/mail.js";

const props = defineProps({
  modelValue: Boolean,
  person: Object,   // 名片对象(需含 name/email)
  question: String, // 触发本次推荐的问题(草稿上下文)
  autoDraft: { type: Boolean, default: true }, // false=个人主页进入,不生成 AI 草稿,用户自写
  issueId: { type: Number, default: null },    // 关联的问题 id(发出后该问题自动置「处理中」,回信可自动归档)
});
const emit = defineEmits(["update:modelValue"]);

const loading = ref(false);
const sending = ref(false);
const subject = ref("");
const body = ref("");
const errorText = ref("");

// 弹窗打开 → 生成草稿(仅 autoDraft 模式);同一人+同一问题只生成一次(关闭重开不重复请求)
let draftKey = "";
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    if (!props.autoDraft) return;
    const key = `${props.person?.id || ""}::${props.question || ""}`;
    if (key === draftKey && body.value) return;
    draftKey = key;
    generateDraft();
  }
);

async function generateDraft() {
  if (!props.person?.id) return;
  loading.value = true;
  errorText.value = "";
  try {
    const draft = await draftMail({ personId: props.person.id, question: props.question || "" });
    subject.value = draft.subject || "";
    body.value = draft.body || "";
    if (draft.fallback) ElMessage.warning("智能体暂不可用，已填入通用草稿，可直接编辑");
  } catch (error) {
    errorText.value = error.message || "草稿生成失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

async function send() {
  sending.value = true;
  errorText.value = "";
  try {
    await sendMail({ to: props.person.email, subject: subject.value.trim(), body: body.value, issueId: props.issueId });
    ElMessage.success(`邮件已发送至 ${props.person.email}`);
    draftKey = "";
    emit("update:modelValue", false);
  } catch (error) {
    errorText.value = error.message || "发送失败，请稍后重试";
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped>
.mail-field {
  margin-bottom: 12px;
  font-size: 13px;
}
.mail-field > label {
  display: block;
  margin-bottom: 4px;
  color: #606266;
}
.mail-recipient {
  padding: 6px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #f5f7fa;
  color: #303133;
}
.mail-input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
}
.mail-input:focus {
  outline: none;
  border-color: #2563eb;
}
.mail-body {
  resize: vertical;
  line-height: 1.7;
}
.mail-error {
  margin: 4px 0 0;
  color: #f56c6c;
  font-size: 12px;
}
.mail-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mail-footer-spacer {
  flex: 1;
}
</style>
