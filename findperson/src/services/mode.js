export function isServerMode() {
  return import.meta.env.VITE_API_MODE === "server";
}

export function isAguiServerMode() {
  return import.meta.env.VITE_AGUI_MODE === "server";
}
