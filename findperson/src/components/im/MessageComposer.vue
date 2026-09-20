<template>
  <div class="fpim-composer">
    <div class="fpim-composer-tools">
      <button class="fpim-iconbtn" title="发送文件（支持任意类型）" @click="pickFile">📎</button>
      <button class="fpim-iconbtn" title="发送图片" @click="pickImage">🖼</button>
      <span class="fpim-hint">Enter 发送 · Shift+Enter 换行 · 可直接粘贴截图</span>
    </div>

    <textarea
      ref="box"
      v-model="text"
      rows="1"
      :placeholder="`发给 ${peerName}…`"
      :disabled="sending"
      @keydown.enter.exact.prevent="submit"
      @input="autoGrow"
      @paste="onPaste"
    ></textarea>

    <div class="fpim-composer-foot">
      <span class="fpim-hint" v-if="errorText" style="color: var(--im-danger)">{{ errorText }}</span>
      <span class="fpim-hint" v-else>消息与问题同库留痕，发送后不可悄然删除</span>
      <button class="fpim-btn prim" :disabled="!canSend" @click="submit">
        {{ sending ? "发送中…" : "发送" }}
      </button>
    </div>

    <input ref="fileInput" type="file" style="display: none" @change="onFilePicked" />
    <input ref="imageInput" type="file" accept="image/*" style="display: none" @change="onFilePicked" />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";

import { useImStore } from "../../stores/im.js";

const store = useImStore();

const box = ref(null);
const fileInput = ref(null);
const imageInput = ref(null);
const text = ref("");
const sending = ref(false);
const errorText = ref("");

const peerName = computed(() => store.active?.title || store.active?.peer?.name || "对方");
const canSend = computed(() => !!text.value.trim() && !sending.value);

watch(() => store.activeId, () => {
  text.value = store.draft[store.activeId] || "";
  nextTick(autoGrow);
});

function autoGrow() {
  const el = box.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
}

async function submit() {
  if (!canSend.value) return;
  sending.value = true;
  errorText.value = "";
  const body = text.value;
  try {
    await store.sendText(body);
    text.value = "";
    store.draft[store.activeId] = "";
    nextTick(autoGrow);
  } catch (err) {
    errorText.value = err.message || "发送失败，请重试";
    text.value = body;                       // 失败保留内容，不让人白写
  } finally {
    sending.value = false;
  }
}

function pickFile() { fileInput.value?.click(); }
function pickImage() { imageInput.value?.click(); }

async function onFilePicked(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (file) await upload(file);
}

/** 截图直接粘进输入框（Web 端覆盖 80% 的截图场景，剩下的交给桌面壳） */
async function onPaste(event) {
  const items = Array.from(event.clipboardData?.items || []);
  const image = items.find((it) => it.type.startsWith("image/"));
  if (!image) return;
  const file = image.getAsFile();
  if (!file) return;
  event.preventDefault();
  await upload(file);
}

async function upload(file) {
  sending.value = true;
  errorText.value = "";
  try {
    await store.sendFile(file);
  } catch (err) {
    errorText.value = err.message || "上传失败";
  } finally {
    sending.value = false;
  }
}
</script>
