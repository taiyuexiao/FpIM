import { createApp } from "vue";
import { createPinia } from "pinia";
import {
  ElButton,
  ElCheckbox,
  ElDialog,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLoading,
  ElOption,
  ElPopover,
  ElRadio,
  ElRadioGroup,
  ElSelect,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTooltip,
  ElTree,
} from "element-plus";
import "element-plus/dist/index.css";
import "../assets/main.css";
import "./styles/element-theme.css";
import "./styles/im.css";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth.js";

const app = createApp(App);
[
  ElButton, ElCheckbox, ElDialog, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElForm, ElFormItem, ElIcon, ElInput, ElOption, ElPopover, ElRadio,
  ElRadioGroup, ElSelect, ElSwitch, ElTabPane, ElTable, ElTableColumn,
  ElTabs, ElTooltip, ElTree,
].forEach((component) => app.component(component.name, component));
app.use(ElLoading); // v-loading 指令(邮件弹窗等场景的加载态)
app
app
  .use(createPinia())
  .use(router)
  .mount("#app");

window.addEventListener("auth:unauthorized", () => {
  useAuthStore().clearSession();
  if (router.currentRoute.value.name !== "login") router.push({ name: "login" });
});
