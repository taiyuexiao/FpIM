<template>
  <div class="chat-composer-wrap">
    <div class="ask-composer chat-composer" role="search">
      <div class="composer-input-row">
        <el-input
          :model-value="modelValue"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 5 }"
          placeholder="例如：我想申请大模型 Key，应该找谁？"
          @update:model-value="$emit('update:modelValue', $event)"
          @compositionstart="composing = true"
          @compositionend="composing = false"
          @keydown.enter.exact="onEnter"
        />
        <button class="composer-send-icon" type="button" title="发送" :disabled="disabled" @click="$emit('send')">
          <span v-html="ICON_SEND"></span>
        </button>
      </div>
      <div class="composer-actions">
        <span class="composer-helper">支持问题找人、信息维护、内容发布、画像补充</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { ICON_SEND } from "../im/icons.js";

defineProps({
  modelValue: { type: String, default: "" },
  disabled: Boolean,
});
const emit = defineEmits(["update:modelValue", "send"]);

// 中文输入法组合态防护:组合期间/组合刚结束的回车是"上屏原文"(macOS 会以真实 Enter 送达),
// 不得触发发送;只有确认不在组合态时才 preventDefault + 发送。
const composing = ref(false);

function onEnter(event) {
  if (composing.value || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  emit("send");
}
</script>

<style scoped>
/* 发送按钮（飞书式纸飞机） */
.composer-send-icon {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: var(--blue, #3370ff);
  color: #fff;
  cursor: pointer;
}
.composer-send-icon:hover {
  background: var(--blue-strong, #2860e1);
}
.composer-send-icon:disabled {
  background: var(--blue-soft, #e8efff);
  color: var(--muted, #8f959e);
  cursor: default;
}
</style>
