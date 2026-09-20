/** IM WebSocket 客户端：握手 / 心跳 / 指数退避重连 / 未读增量补齐。
 *
 * 设计要点（详见 docs/modules/im-core.md）：
 * - 断线重连后靠 `afterSeq` 增量补齐，不依赖服务端推送补发
 * - 发送用 clientMsgId 幂等键，重发不会产生重复消息
 * - 连接态与业务态分离：这里只管"通道活着"，消息落库由 api/im.js 兜底
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/** 从 API 基址推导 WS 地址（可用 VITE_IM_WS_URL 覆盖） */
export function resolveWsUrl() {
  if (import.meta.env.VITE_IM_WS_URL) return import.meta.env.VITE_IM_WS_URL;
  if (/^https?:/.test(API_BASE)) {
    return `${API_BASE.replace(/^http/, "ws").replace(/\/$/, "")}/ws/im`;
  }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${API_BASE}/ws/im`;
}

const HEARTBEAT_MS = 25000;   // 服务端/中间代理通常 60s 断空闲连接
const MAX_BACKOFF_MS = 30000;

export function createImSocket({ getToken, handlers = {} } = {}) {
  let ws = null;
  let closedByUser = false;
  let retries = 0;
  let heartbeatTimer = null;
  let reconnectTimer = null;

  const emit = (name, payload) => {
    const fn = handlers[name];
    if (fn) {
      try {
        fn(payload);
      } catch (err) {
        console.error(`[im] handler ${name} 抛错`, err);
      }
    }
  };

  function clearTimers() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    heartbeatTimer = null;
    reconnectTimer = null;
  }

  function scheduleHeartbeat() {
    heartbeatTimer = setTimeout(() => {
      send({ type: "ping" });
      scheduleHeartbeat();
    }, HEARTBEAT_MS);
  }

  function scheduleReconnect() {
    if (closedByUser) return;
    // 指数退避：1s → 2s → 4s … 上限 30s，避免服务重启时雪崩
    const delay = Math.min(1000 * 2 ** retries, MAX_BACKOFF_MS);
    retries += 1;
    emit("status", { state: "reconnecting", retryIn: delay });
    reconnectTimer = setTimeout(connect, delay);
  }

  function connect() {
    const token = getToken && getToken();
    if (!token) {
      emit("status", { state: "unauthorized" });
      return;
    }
    const url = `${resolveWsUrl()}?token=${encodeURIComponent(token)}`;
    emit("status", { state: "connecting" });

    try {
      ws = new WebSocket(url);
    } catch (err) {
      emit("error", err);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      retries = 0;
      emit("status", { state: "open" });
      scheduleHeartbeat();
    };

    ws.onmessage = (event) => {
      let frame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        return;
      }
      switch (frame.type) {
        case "ready":    emit("ready", frame); break;
        case "ack":      emit("ack", frame); break;
        case "message":  emit("message", frame.message); break;
        case "read":     emit("read", frame); break;
        case "typing":   emit("typing", frame); break;
        case "presence": emit("presence", frame); break;
        case "error":    emit("error", frame); break;
        default: break;
      }
    };

    ws.onerror = () => emit("status", { state: "error" });

    ws.onclose = () => {
      clearTimers();
      ws = null;
      if (closedByUser) {
        emit("status", { state: "closed" });
        return;
      }
      scheduleReconnect();
    };
  }

  function send(payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }

  return {
    connect,
    close() {
      closedByUser = true;
      clearTimers();
      if (ws) ws.close();
      ws = null;
    },
    isOpen: () => !!ws && ws.readyState === WebSocket.OPEN,
    send,
    /** 发消息：WS 通就走 WS，否则返回 false 由调用方走 HTTP 兜底
     *  clientMsgId 必须由调用方传入并与本地乐观消息一致，否则 ack 对不上会产生重复气泡 */
    sendMessage({ conversationId, text, msgType = "text", content, issueId, clientMsgId }) {
      return send({
        type: "send",
        conversationId,
        msgType,
        content: content || { text },
        clientMsgId: clientMsgId || newClientMsgId(),
        issueId: issueId || null,
      });
    },
    sendRead({ conversationId, seq, issueId }) {
      return send({ type: "read", conversationId, seq, issueId: issueId || null });
    },
    sendTyping(conversationId) {
      return send({ type: "typing", conversationId });
    },
  };
}

/** 幂等键：时间戳 + 随机后缀，同一次发送重试要复用同一个值（由调用方持有） */
export function newClientMsgId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
