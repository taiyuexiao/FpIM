import { defineStore } from "pinia";
import { currentUserId, loadJson, normalize, saveJson, STORAGE_KEYS } from "../state.js";
import { getMe, login as serverLogin, logout as serverLogout, updateMyProfile, changeMyPassword } from "../services/api/auth.js";
import { isServerMode } from "../services/mode.js";
import { useDirectoryStore } from "./directory.js";

const storedAuth = loadJson(STORAGE_KEYS.auth, {});

/** 切换登录态后重置各数据 store 的 loaded 标记,确保重新拉取新用户数据 */
async function resetDataStores() {
  const [{ useContentStore }, { useReviewsStore }, { useSessionsStore }, { useDirectoryStore }] = await Promise.all([
    import("./content.js"), import("./reviews.js"), import("./sessions.js"), import("./directory.js"),
  ]);
  useDirectoryStore().loaded = false;
  useContentStore().loaded = false;
  useReviewsStore().loaded = false;
  useSessionsStore().loaded = false;
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    isLoggedIn: Boolean(storedAuth.isLoggedIn),
    userId: storedAuth.userId || currentUserId,
    name: storedAuth.name || "",
    initialized: false,
    mockPassword: "123456",
  }),
  getters: {
    user() {
      return useDirectoryStore().getPerson(this.userId);
    },
    displayName() {
      return this.user?.name || this.name || "用户";
    },
    isAdmin() {
      return this.user?.systemRole === "管理员";
    },
  },
  actions: {
    persist() {
      saveJson(STORAGE_KEYS.auth, {
        isLoggedIn: this.isLoggedIn,
        userId: this.userId,
        name: this.name,
      });
    },
    clearSession() {
      this.isLoggedIn = false;
      this.name = "";
      localStorage.removeItem("firstResponsibilityDemo.token");
      this.persist();
    },
    async bootstrap() {
      if (this.initialized) return this.isLoggedIn;
      if (!isServerMode()) {
        this.initialized = true;
        this.persist();
        return this.isLoggedIn;
      }
      try {
        const user = await getMe();
        if (!user?.id) throw new Error("登录状态无效");
        this.userId = user.id;
        this.name = user.name || "";
        this.isLoggedIn = true;
        useDirectoryStore().setCurrentUser(user.id);
        this.persist();
      } catch {
        this.clearSession();
      } finally {
        this.initialized = true;
      }
      return this.isLoggedIn;
    },
    async loadMe() {
      if (!isServerMode()) return this.user;
      const user = await getMe();
      if (user?.id) {
        this.userId = user.id;
        this.name = user.name;
        this.isLoggedIn = true;
        useDirectoryStore().setCurrentUser(user.id);
        this.persist();
      }
      return user;
    },
    async login({ account, password }) {
      if (isServerMode()) {
        let result;
        try {
          result = await serverLogin({ account, password });
        } catch (error) {
          return { ok: false, message: error.message || "登录失败，请稍后重试" };
        }
        if (result?.token) localStorage.setItem("firstResponsibilityDemo.token", result.token);
        this.isLoggedIn = true;
        this.userId = result?.user?.id || currentUserId;
        this.name = result?.user?.name || this.displayName;
        useDirectoryStore().setCurrentUser(this.userId);
        this.persist();
        this.initialized = true;
        await resetDataStores();
        return { ok: true };
      }
      const key = normalize(account);
      const demoAccounts = {
        linzhixia: currentUserId, "林知夏": currentUserId, "13800001206": currentUserId,
        wangke: "p-clerk-1", "王珂": "p-clerk-1", "13800001301": "p-clerk-1",
      };
      const userId = demoAccounts[key];
      if (!userId || password !== this.mockPassword) return { ok: false, message: "账号或密码不正确" };
      if (useDirectoryStore().getPerson(userId)?.active === false) return { ok: false, message: "当前账号已停用" };
      this.isLoggedIn = true;
      this.userId = userId;
      this.name = useDirectoryStore().getPerson(userId)?.name || "用户";
      useDirectoryStore().setCurrentUser(userId);
      this.persist();
      this.initialized = true;
      return { ok: true };
    },
    async logout() {
      if (isServerMode()) await serverLogout().catch(console.warn);
      this.clearSession();
      useDirectoryStore().setCurrentUser(currentUserId);
      await resetDataStores();
    },
    async changePassword({ currentPassword, nextPassword, confirmPassword }) {
      if (!nextPassword || nextPassword.length < 6) return "新密码至少 6 位";
      if (nextPassword !== confirmPassword) return "两次输入不一致";
      if (isServerMode()) {
        try {
          await changeMyPassword({ old_password: currentPassword, new_password: nextPassword });
          return "";
        } catch (error) {
          return error.message || "修改密码失败";
        }
      }
      // mock 模式：只改本地
      if (currentPassword !== this.mockPassword) return "原密码不正确";
      this.mockPassword = nextPassword;
      return "";
    },
    async updateProfile(patch) {
      const allowed = ["contact", "domainsText", "selfPortrait", "addDomains", "removeDomains"];
      const profilePatch = Object.fromEntries(allowed.filter((key) => patch[key] !== undefined).map((key) => [key, patch[key]]));
      const person = useDirectoryStore().updatePerson(this.userId, profilePatch);
      if (!person) return { ok: false, message: "本地名录未同步到当前用户,请刷新页面后重试" };
      this.name = person.name;
      this.persist();
      if (isServerMode()) {
        try {
          await updateMyProfile(person);
        } catch (error) {
          console.warn("资料同步失败:", error);
          return { ok: false, message: "资料同步到服务器失败，请重试" };
        }
      }
      return person;
    },
  },
});
