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

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status;
    const messageMap = {
      401: "登录状态已失效，请重新登录",
      403: "当前账号没有权限执行该操作",
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
