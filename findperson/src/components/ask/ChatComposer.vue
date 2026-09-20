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
        <el-button class="primary-button composer-send-button" type="primary" :disabled="disabled" @click="$emit('send')">
          <el-icon><Right /></el-icon>
          发送
        </el-button>
      </div>
      <div class="composer-actions">
        <span class="composer-helper">支持问题找人、信息维护、内容发布、画像补充</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { Right } from "@element-plus/icons-vue";

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
