"""SMTP 发信(个人邮箱中继投递 @bosc.cn)。

465=SSL 直连;587/25=STARTTLS(服务器不支持时回退明文,内网中继常见)。
From 必须与 SMTP 认证账号一致(否则服务器 553 拒发);凭据放 .env,投产切行内中继只改配置。
"""
from __future__ import annotations

import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from ..core.config import settings


class MailSendError(Exception):
    """SMTP 发送异常(连接/认证/投递失败统一抛出,带原因)"""


def send(to: str, subject: str, body: str) -> str:
    """发送纯文本邮件到单个收件人;返回 Message-ID(用于把回信关联回问题)。"""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise MailSendError("SMTP 未配置(缺发件邮箱或授权码)")

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = (
        f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>" if settings.SMTP_FROM_NAME else settings.SMTP_USER
    )
    msg["To"] = to
    msg["Subject"] = Header(subject, "utf-8")
    msg["Date"] = formatdate(localtime=True)
    message_id = make_msgid()
    msg["Message-ID"] = message_id

    context = ssl.create_default_context()
    try:
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30, context=context)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
            try:
                server.starttls(context=context)
            except (smtplib.SMTPException, ssl.SSLError):
                pass
        try:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, [to], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError as exc:
        raise MailSendError(f"SMTP 认证失败(检查授权码): {exc}") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailSendError(f"SMTP 发送失败: {exc}") from exc
    return message_id
