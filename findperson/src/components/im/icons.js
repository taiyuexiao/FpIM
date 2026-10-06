/** 飞书风线性图标（20px、1.6 描边），消息操作条与输入框工具栏共用。 */
const wrap = (paths) =>
  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

export const ICON_REPLY = wrap('<path d="M9 7L4 12l5 5"/><path d="M4 12h9a6 6 0 016 6v1"/>');            // 回复
export const ICON_COPY = wrap('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h8"/>'); // 复制
export const ICON_LIKE = wrap('<path d="M7 10v10H4V10h3zm3 10V10l3.2-6a2 2 0 013.7 1.3L16 10h3.5a1.5 1.5 0 011.5 1.7l-1.2 7A2 2 0 0117.8 21H10z"/>'); // 点赞
export const ICON_EMOJI = wrap('<circle cx="12" cy="12" r="9"/><path d="M8.5 14a4 4 0 007 0"/><path d="M9 9.5h.01M15 9.5h.01"/>'); // 表情
export const ICON_EDIT = wrap('<path d="M4 20h4L19 9a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M14.5 6.5l3 3"/>'); // 编辑
export const ICON_FORWARD = wrap('<path d="M14 5l6 5-6 5v-3c-5 0-8 1.5-10 5 .8-5 3.5-9 10-10V5z"/>');      // 转发
export const ICON_PIN = wrap('<path d="M12 17v5"/><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6z"/>');            // 置顶
export const ICON_TRASH = wrap('<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>'); // 删除
export const ICON_REVOKE = wrap('<path d="M21 12a9 9 0 11-3-6.7"/><path d="M21 3v6h-6"/><path d="M12 8v5l3 2"/>'); // 撤回
export const ICON_MORE = wrap('<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>'); // 更多
export const ICON_SEND = wrap('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>');              // 发送（纸飞机）
export const ICON_CLIP = wrap('<path d="M21 11l-8.5 8.5a5 5 0 01-7-7L14 4a3.5 3.5 0 015 5l-8.5 8.5a2 2 0 01-3-3L15 6"/>'); // 附件
export const ICON_IMAGE = wrap('<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 16l-5-5-9 9"/>'); // 图片
export const ICON_CARD = wrap('<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16c.6-1.4 1.7-2 3-2s2.4.6 3 2"/><path d="M15 10h3M15 13h3"/>'); // 名片
export const ICON_BOLT = wrap('<path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z"/>');                              // 快捷短语
export const ICON_BOT = wrap('<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 8V4"/><circle cx="12" cy="3.5" r="1"/><path d="M9 13h.01M15 13h.01"/><path d="M9.5 16h5"/><path d="M3 12v3M21 12v3"/>'); // 机器人
