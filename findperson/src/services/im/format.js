/** IM 展示层格式化工具（头像 / 时间 / 预览 / 文件大小）。 */

const PALETTE = [
  "#3370FF", "#00A8A8", "#F5822B", "#7F5CE0",
  "#D93A6E", "#2BA471", "#C86400", "#5A6BC7",
];

export function avatarColor(seed = "") {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) % 9973;
  return PALETTE[hash % PALETTE.length];
}

/** 中文取后两字（姓名通常 2~3 字，取末两字比取首字更易区分），英文取首字母 */
export function avatarText(name = "") {
  const text = String(name).trim();
  if (!text) return "?";
  if (/[\u4e00-\u9fa5]/.test(text)) return text.slice(-2);
  return text.slice(0, 2).toUpperCase();
}

export function shortTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return "昨天";
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日`;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}

export function fullTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 是否需要插入时间分隔条（相邻两条间隔超过 5 分钟） */
export function needTimeDivider(prev, curr) {
  if (!prev) return true;
  const a = new Date(prev.createdAt).getTime();
  const b = new Date(curr.createdAt).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return false;
  return b - a > 5 * 60 * 1000;
}

export function humanSize(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let n = Number(bytes);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${i === 0 ? n : n.toFixed(1)}${units[i]}`;
}

export function fileExt(name = "") {
  const m = String(name).match(/\.([a-z0-9]+)$/i);
  return m ? m[1] : "file";
}

const TYPE_LABEL = {
  image: "[图片]",
  file: "[文件]",
  audio: "[语音]",
  video: "[视频]",
  system: "[系统消息]",
  issue_card: "[问题卡]",
  resolve_confirm: "[解决确认]",
  report_card: "[报表]",
};

/** 会话列表第二行的消息预览 */
export function previewOf(msg) {
  if (!msg) return "暂无消息";
  if (msg.revoked) return "消息已撤回";
  if (TYPE_LABEL[msg.msgType]) {
    return msg.msgType === "file" ? `[文件] ${msg.content?.name || ""}`.trim()
      : TYPE_LABEL[msg.msgType];
  }
  const text = msg.content?.text || "";
  return text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

/** 问题状态 → 中文标签 + chip 样式类（必须带文字，不能只用色点） */
export const ISSUE_STATUS = {
  not_contacted: { label: "未联系", cls: "new" },
  processing: { label: "处理中", cls: "doing" },
  resolved: { label: "已解决", cls: "done" },
  unresolved: { label: "未解决", cls: "failed" },
};

export function issueStatusMeta(status) {
  return ISSUE_STATUS[status] || { label: status || "未知", cls: "" };
}

/** issue_events.event_type → 时间线可读文案 */
export const EVENT_LABEL = {
  created: "问题创建",
  status_changed: "状态变更",
  read: "首次已读",
  responded: "首次响应",
  mail_sent: "发出邮件",
  mail_received: "收到回信",
  mail_analyzed: "AI 分析回信",
  note: "备注",
  resolved: "标记已解决",
  reopened: "重新打开",
  knowledged: "沉淀为知识",
  rated: "评价",
};

export function eventLabel(type) {
  return EVENT_LABEL[type] || type;
}
