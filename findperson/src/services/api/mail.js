import http from "./http.js";

/** 智能体按问题上下文代拟邮件草稿(DeepSeek) */
export const draftMail = (payload) => http.post("/mail/draft", payload);

/** 发送邮件(SMTP 中继投递 @bosc.cn) */
export const sendMail = (payload) => http.post("/mail/send", payload);
