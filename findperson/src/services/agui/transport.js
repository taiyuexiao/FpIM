import { normalizeAguiEvent } from "./normalizer.js";

// 会话历史回拉(直连 agent-service;后端 /api/v1 无此路由)
export async function fetchAguiSessionState(sessionId) {
  const baseUrl = import.meta.env.VITE_AGUI_BASE_URL || "/api/agui";
  const response = await fetch(`${baseUrl}/sessions/${sessionId}/state`, {
    headers: { Accept: "application/json" },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`AGUI state request failed: ${response.status}`);
  return response.json();
}

export async function* connectAguiStream({ sessionId, payload, signal, timeoutMs = 30000, retry = 1 }) {
  const baseUrl = import.meta.env.VITE_AGUI_BASE_URL || "/api/agui";
  const timeout = AbortSignal.timeout ? AbortSignal.timeout(timeoutMs) : null;
  const combinedSignal = signal || timeout;
  let lastError;
  for (let attempt = 0; attempt <= retry; attempt += 1) {
    // 已开始收到事件后不再重发整个 POST(避免服务端重复落库同一消息)
    let established = false;
    try {
      for await (const event of requestAguiStream({ baseUrl, sessionId, payload, signal: combinedSignal })) {
        established = true;
        yield event;
      }
      return;
    } catch (error) {
      lastError = error;
      if (established || attempt >= retry || error.name === "AbortError") break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw lastError;
}

async function* requestAguiStream({ baseUrl, sessionId, payload, signal }) {
  const response = await fetch(`${baseUrl}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream, application/x-ndjson, application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    throw new Error(`AGUI request failed: ${response.status}`);
  }
  if (!response.body) {
    const json = await response.json();
    const events = Array.isArray(json) ? json : [json];
    for (const event of events) yield normalizeAguiEvent(event);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    for (const line of lines) {
      const text = line.replace(/^data:\s*/, "").trim();
      if (!text || text === "[DONE]") continue;
      yield normalizeAguiEvent(JSON.parse(text));
    }
  }
  if (buffer.trim()) yield normalizeAguiEvent(JSON.parse(buffer.trim().replace(/^data:\s*/, "")));
}
