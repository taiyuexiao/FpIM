import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 30000,
  withCredentials: true,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("firstResponsibilityDemo.token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 静默续期（04-方案 §3.1）：401 → 用当前 token 换发新 token → 重放原请求一次；
// 刷新本身失败（token_version 已递增等）才登出。
let refreshing = null;

function refreshTokenOnce() {
  if (!refreshing) {
    const token = localStorage.getItem("firstResponsibilityDemo.token");
    refreshing = axios
      .post(`${import.meta.env.VITE_API_BASE_URL || "/api"}/auth/refresh`, null, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      .then((r) => {
        localStorage.setItem("firstResponsibilityDemo.token", r.data.token);
        return r.data.token;
      })
      .finally(() => {
        setTimeout(() => { refreshing = null; }, 50);
      });
  }
  return refreshing;
}

http.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status;
    const config = error.config || {};
    if (status === 401 && !config.__retried && !String(config.url || "").includes("/auth/")) {
      config.__retried = true;
      try {
        await refreshTokenOnce();
        return http(config);   // 重放一次
      } catch {
        /* 刷新失败 → 走登出 */
      }
    }
    const messageMap = {
      401: "登录状态已失效，请重新登录",
      403: "当前账号没有权限执行该操作",
      429: "操作太频繁，请稍后再试",
      500: "服务端处理异常，请稍后重试",
    };
    const serverMessage = error.response?.data?.detail || error.response?.data?.message;
    const normalized = new Error(serverMessage || messageMap[status] || error.message || "网络请求失败");
    normalized.status = status;
    normalized.payload = error.response?.data;
    if (status === 401) {
      localStorage.removeItem("firstResponsibilityDemo.token");
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    return Promise.reject(normalized);
  }
);

export default http;
