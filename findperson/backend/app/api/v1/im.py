"""IM REST 接口（历史 / 建会话 / 上传 / 兜底发消息）。

分工：实时收发走 WebSocket（/api/v1/ws/im），本路由负责
历史拉取、会话创建、附件上传下载、以及 WS 不可用时的 HTTP 兜底发送。

  GET    /im/conversations                          我的会话列表
  POST   /im/conversations/direct                   取或建单聊（免加好友）
  POST   /im/conversations/group                    建群（≤100 人）
  GET    /im/conversations/{cid}                    会话详情（含成员）
  POST   /im/conversations/{cid}/members            群聊拉人
  GET    /im/conversations/{cid}/messages           历史/增量消息
  POST   /im/conversations/{cid}/messages           HTTP 兜底发消息（WS 断线时）
  POST   /im/conversations/{cid}/read               推进已读游标（红点）
  GET    /im/conversations/{cid}/issues             会话关联的问题 + 时间线
  DELETE /im/messages/{mid}                         撤回（2 分钟内）
  POST   /im/upload                                 上传附件（内容寻址）
  GET    /im/files/{rel_path:path}                  读取附件
  POST   /im/issues/{iid}/read                      问题首次已读留痕（不可覆盖）
"""
from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.user import User
from ...services import im as im_service

router = APIRouter(prefix="/im", tags=["即时通讯"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024          # 单文件上限 200MB
ALLOWED_EXT_HINT = (
    "txt md csv json log pdf doc docx xls xlsx ppt pptx "
    "png jpg jpeg gif webp bmp svg heic mp3 wav m4a amr mp4 mov avi mkv zip rar 7z"
)


class DirectIn(BaseModel):
    peerId: str = Field(min_length=1)
    issueId: int | None = None


class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    memberIds: list[str] = Field(default_factory=list)
    issueId: int | None = None


class MembersIn(BaseModel):
    memberIds: list[str] = Field(min_length=1)


class SendIn(BaseModel):
    text: str = Field(default="", max_length=8000)
    msgType: str = Field(default="text")
    content: dict | None = None
    clientMsgId: str | None = Field(default=None, max_length=64)
    issueId: int | None = None


class ReadIn(BaseModel):
    seq: int = Field(ge=0)
    issueId: int | None = None


class IssueCreateIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    assigneePersonId: str | None = None   # 单聊默认对方；群聊必填（集体负责=无人负责）
    summary: str | None = Field(default=None, max_length=200)


# ── 会话 ──────────────────────────────────────────────────────────

@router.get("/conversations", summary="我的会话列表")
def list_conversations(limit: int = Query(default=50, ge=1, le=200),
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    return {"items": im_service.list_conversations(db, user.id, limit)}


@router.post("/conversations/direct", summary="取或建单聊（免加好友）")
def create_direct(body: DirectIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    try:
        conv = im_service.get_or_create_direct(db, user.id, body.peerId, body.issueId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 问题 → 会话 反向指针，便于从「我的问题」一键跳回聊天
    if body.issueId:
        im_service.link_issue_conversation(db, body.issueId, conv["id"])

    detail = im_service.get_conversation(db, conv["id"], user.id)
    return detail or conv


@router.post("/conversations/group", summary="建群（上限 100 人）")
def create_group(body: GroupIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    try:
        conv = im_service.create_group(db, user.id, body.memberIds, body.title, body.issueId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.issueId:
        im_service.link_issue_conversation(db, body.issueId, conv["id"])
    return im_service.get_conversation(db, conv["id"], user.id) or conv


@router.get("/conversations/{cid}", summary="会话详情")
def get_conversation(cid: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    conv = im_service.get_conversation(db, cid, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在或你不是成员")
    return conv


@router.post("/conversations/{cid}/members", summary="群聊拉人")
def add_members(cid: int, body: MembersIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if not im_service.is_member(db, cid, user.id):
        raise HTTPException(status_code=403, detail="不是该会话成员")
    try:
        added = im_service.add_members(db, cid, body.memberIds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"added": added}


# ── 消息 ──────────────────────────────────────────────────────────

@router.get("/conversations/{cid}/messages", summary="历史 / 增量消息")
def list_messages(cid: int,
                  beforeSeq: int | None = None,
                  afterSeq: int | None = None,
                  limit: int = Query(default=30, ge=1, le=100),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    try:
        items = im_service.list_messages(db, cid, user.id, beforeSeq, afterSeq, limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"items": items}


@router.post("/conversations/{cid}/messages", summary="HTTP 兜底发消息")
def send_message(cid: int, body: SendIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    content = body.content if body.content is not None else {"text": body.text}
    try:
        msg, created = im_service.send_message(
            db, cid, user.id, body.msgType, content, body.clientMsgId, None, body.issueId)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": msg, "created": created}


@router.post("/conversations/{cid}/read", summary="推进已读游标")
def mark_read(cid: int, body: ReadIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    try:
        result = im_service.mark_read(db, cid, user.id, body.seq)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if body.issueId:
        # 只认责任人的首次已读；重复调用由唯一索引兜底忽略
        im_service.record_issue_read(db, body.issueId, user.id)
    return result


@router.delete("/messages/{mid}", summary="撤回消息（2 分钟内）")
def revoke(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not im_service.revoke_message(db, mid, user.id):
        raise HTTPException(status_code=400, detail="撤回失败：超出 2 分钟或非本人消息")
    return {"ok": True}


# ── 问题联动 ──────────────────────────────────────────────────────

@router.get("/conversations/{cid}/issues", summary="会话关联的问题 + 时间线")
def conversation_issues(cid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not im_service.is_member(db, cid, user.id):
        raise HTTPException(status_code=403, detail="不是该会话成员")
    issues = im_service.conversation_issue_brief(db, cid)
    for issue in issues:
        issue["timeline"] = im_service.issue_timeline(db, issue["id"])
    return {"items": issues}


@router.post("/conversations/{cid}/issues", summary="在会话内立项")
async def create_issue(cid: int, body: IssueCreateIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """会话里直接立项：建问题 + 挂会话锚点 + 插 issue_card 消息（广播给其他成员）。"""
    try:
        result = im_service.create_issue_in_conversation(
            db, cid, user.id, body.question, body.assigneePersonId, body.summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 立项卡实时推给会话其他成员（发起方前端用返回值直接刷新）
    from ...ws.im_gateway import _load_member_ids, hub
    member_ids = await asyncio.to_thread(_load_member_ids, cid)
    await hub.send_to_users(
        [m for m in member_ids if m != user.id],
        {"type": "message", "message": result["message"]},
    )
    # 小管家给责任人的立项通知也实时推
    notify = result.get("notify")
    if notify:
        await hub.send_to_users(
            [notify["toUserId"]],
            {"type": "message", "message": notify["message"]},
        )
    return result


@router.post("/issues/{iid}/read", summary="问题首次已读留痕（不可覆盖）")
def record_issue_read(iid: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return {"recorded": im_service.record_issue_read(db, iid, user.id)}


# ── 附件 ──────────────────────────────────────────────────────────

def _file_root() -> Path:
    root = Path(getattr(settings, "FPIM_FILE_ROOT", "/data/fpim/files")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/upload", summary="上传附件（内容寻址）")
async def upload(file: UploadFile = File(...),
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """按 sha256 落盘：天然去重 + 秒传；同名同内容只存一份，ref_count 累加。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限")

    digest = im_service.sha256_of(data)
    original = file.filename or "unnamed"
    ext = os.path.splitext(original)[1].lstrip(".").lower()[:12]
    rel_dir = f"{digest[:4]}/{digest[4:6]}"
    rel_path = f"{rel_dir}/{digest}" + (f".{ext}" if ext else "")

    target = _file_root() / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        # 先写临时文件再改名，避免半截文件被当成完整附件
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)

    mime = file.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream"
    meta = im_service.register_attachment(
        db, digest, ext, mime, len(data), original, rel_path, user.id)
    meta["sizeHuman"] = _human(len(data))
    return meta


@router.get("/files/{rel_path:path}", summary="读取附件")
def download(rel_path: str, download: bool = False):
    root = _file_root().resolve()
    target = (root / rel_path).resolve()
    # 目录穿越防护：解析后必须仍在根目录内
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = target.name
    return FileResponse(
        target,
        filename=filename if download else None,
        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"
