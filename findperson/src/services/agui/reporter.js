import { reportAguiEvent } from "../api/agui.js";
import { loadJson, saveJson, STORAGE_KEYS } from "../../state.js";

export function buildInteractionEvent(payload = {}) {
  return {
    sessionId: payload.sessionId || "",
    messageId: payload.messageId || "",
    eventType: payload.eventType || payload.type || "interaction",
    targetType: payload.targetType || "",
    targetId: payload.targetId || "",
    value: payload.value || "",
    reason: payload.reason || "",
    traceId: payload.traceId || "",
    context: payload.context || {},
    timestamp: new Date().toISOString(),
  };
}

export async function reportInteractionEvent(payload = {}) {
  const event = buildInteractionEvent(payload);
  const stored = loadJson(STORAGE_KEYS.interactions, []);
  saveJson(STORAGE_KEYS.interactions, stored.concat(event).slice(-200));
  if (import.meta.env.VITE_AGUI_MODE !== "server") return event;
  try {
    await reportAguiEvent(event);
  } catch (error) {
    console.warn("AGUI interaction report failed", error);
  }
  return event;
}
