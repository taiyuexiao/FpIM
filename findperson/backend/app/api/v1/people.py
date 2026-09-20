"""人员管理"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import hash_password
from ...middleware.deps import require_admin
from ...models.user import User
from ...schemas.people import PersonCreateRequest, PersonResponse, PersonUpdateRequest
from ...services.publish_event import emit_publish_event, PERSON_CHANGED
from ...services.tag_sync import sync_person_domain_tags

router = APIRouter(prefix="/people", tags=["人员"])

# ── 拼音搜索缓存：user_id → (全拼, 首字母)。人员变化频率极低，进程内缓存即可 ──
_PINYIN_CACHE: dict[str, tuple[str, str]] = {}


def _pinyin_keys(user: User) -> tuple[str, str]:
    """姓名的拼音全拼 + 首字母缩写（如 张三 → zhangsan / zs），带进程内缓存。"""
    hit = _PINYIN_CACHE.get(user.id)
    if hit:
        return hit
    from pypinyin import Style, lazy_pinyin
    name = user.name or ""
    full = "".join(lazy_pinyin(name))
    abbr = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER))
    _PINYIN_CACHE[user.id] = (full, abbr)
    return full, abbr


def _matches_pinyin(user: User, kw: str) -> bool:
    full, abbr = _pinyin_keys(user)
    return kw in full or abbr.startswith(kw)


@router.get("", summary="List People", description="人员列表（分页 + 搜索）")
def list_people(
    keyword: str | None = Query(None, description="姓名/账号/拼音搜索（全拼包含、首字母前缀）"),
    department_id: int | None = None,
    domain: str | None = None,
    active: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),  # 名片库/详情一次性拉全量(当前数据量级 252)
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if active:
        q = q.filter(User.active == True)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter((User.name.ilike(kw)) | (User.account.ilike(kw)))
        # 纯字母输入（拼音）：SQL 查不到中文名的拼音，补一遍内存匹配（数据量 ~250，代价可忽略）
        if re.fullmatch(r"[a-z]+", keyword.strip().lower()):
            py_kw = keyword.strip().lower()
            sql_ids = {u.id for u in q}
            extra = [u for u in db.query(User).filter(User.active == True).all()
                     if u.id not in sql_ids and _matches_pinyin(u, py_kw)]
            if extra:
                items = list(q.order_by(User.id).all()) + sorted(extra, key=lambda u: u.id)
                start = (page - 1) * page_size
                return [PersonResponse.model_validate(u).model_dump(by_alias=True)
                        for u in items[start:start + page_size]]
    if department_id:
        q = q.filter(User.department_id == department_id)
    total = q.count()
    items = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    # 直接返回数组（前端需要平铺列表）；by_alias 输出 camelCase 字段名
    return [PersonResponse.model_validate(u).model_dump(by_alias=True) for u in items]


@router.post("", response_model=PersonResponse, status_code=201, summary="Create Person", description="新增成员(仅管理员)")
def create_person(body: PersonCreateRequest, request: Request, db: Session = Depends(get_db)):
    require_admin(request)  # v4 §十:成员管理仅管理员
    if body.account and db.query(User).filter(User.account == body.account).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号已存在")
    # 生成 id/账号:沿用 p-XXXX / PXXXX 序列
    max_num = 0
    for (uid,) in db.query(User.id).all():
        m = re.fullmatch(r"P(\d+)", uid or "")
        if m:
            max_num = max(max_num, int(m.group(1)))
    new_id = f"P{max_num + 1:04d}"
    # 登录账号 = 工号 PXXXX（与 id 一致），密码统一默认 123456
    account = body.account or new_id
    # 默认上级 = 部门负责人
    manager_id = body.managerId
    if not manager_id and body.departmentId:
        from ...models.department import Department
        dept = db.query(Department).filter(Department.id == body.departmentId).first()
        manager_id = dept.leader_id if dept else None
    user = User(
        id=new_id,
        account=account,
        name=body.name,
        password_hash=hash_password(body.password or "123456"),
        phone=body.phone,
        system_role=body.systemRole or "普通成员",
        department_id=body.departmentId,
        role=body.role,
        contact=body.contact,
        active=body.active if body.active is not None else True,
        manager_id=manager_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    emit_publish_event(db, PERSON_CHANGED, user.id, created_by=getattr(request.state, "user_id", None))
    db.commit()
    return user


@router.get("/{person_id}", response_model=PersonResponse, summary="Get Person", description="人员详情")
def get_person(person_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == person_id).first()
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")
    return user


@router.patch("/{person_id}", response_model=PersonResponse, summary="Update Person", description="更新人员信息(仅管理员)")
def update_person(person_id: str, body: PersonUpdateRequest, request: Request, db: Session = Depends(get_db)):
    require_admin(request)  # v4 §十:成员管理仅管理员(本人改资料走 /me/profile)
    user = db.query(User).filter(User.id == person_id).first()
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")
    update_data = body.model_dump(exclude_unset=True)
    field_map = {
        "departmentId": "department_id",
        "selfPortrait": "self_portrait",
        "systemRole": "system_role",
        "managerId": "manager_id",
    }
    for camel, snake in field_map.items():
        if camel in update_data:
            update_data[snake] = update_data.pop(camel)

    # 部门变更且未显式指定上级时,默认上级 = 新部门负责人
    if "department_id" in update_data and "manager_id" not in update_data:
        from ...models.department import Department
        new_dept = db.query(Department).filter(Department.id == update_data["department_id"]).first()
        update_data["manager_id"] = new_dept.leader_id if new_dept else None

    for key, value in update_data.items():
        setattr(user, key, value)
    # 负责领域变更 → 同步进标签检索体系(与 me.py 本人修改同一机制;backend 分支缺口补齐)
    if "domains" in update_data:
        sync_person_domain_tags(db, person_id=user.id, domains=user.domains or [])
    db.commit()
    db.refresh(user)
    emit_publish_event(db, PERSON_CHANGED, user.id, created_by=getattr(request.state, "user_id", None))
    db.commit()
    return user


@router.get("/{person_id}/profile-stats", summary="Profile Stats",
            description="个人数据画像（被问/解决/帮助榜排名/知识沉淀/首响时长）；公开字段，全员可见")
def profile_stats(person_id: str, db: Session = Depends(get_db)):
    """数据画像（PRD F2）：个人主页的"被问与解决情况"数据源。

    - 被问/解决：来自 issues（assignee_person_id = 本人）
    - 帮助榜排名：全公司按「解决数降序 → 被问数降序」排名，只排进有数据的人
    - 知识沉淀数：faqs.owner_person_id = 本人（已发布的知识条目）
    - 首响时长：first_response_at - created_at 的均值（小时，只算已响应的）
    - 统计周期：累计 + 近 30 天两组；since 取库里最早的问题创建时间
    """
    from sqlalchemy import text as _text

    exists = db.query(User.id).filter(User.id == person_id).first()
    if not exists:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")

    row = db.execute(_text(
        """
        SELECT count(*) AS asked,
               count(*) FILTER (WHERE status = 'resolved') AS resolved,
               count(*) FILTER (WHERE created_at >= now() - interval '30 days') AS asked_30d,
               count(*) FILTER (WHERE status = 'resolved'
                                AND resolved_at >= now() - interval '30 days') AS resolved_30d,
               avg(EXTRACT(EPOCH FROM (first_response_at - created_at)) / 3600.0)
                   FILTER (WHERE first_response_at IS NOT NULL) AS avg_first_resp_hours,
               min(created_at) AS since
          FROM public.issues
         WHERE assignee_person_id = :pid
        """
    ), {"pid": person_id}).fetchone()

    faq_count = db.execute(_text(
        "SELECT count(*) FROM public.faqs WHERE owner_person_id = :pid AND status = 'published'"
    ), {"pid": person_id}).scalar() or 0

    # 帮助榜：按 解决数 desc → 被问数 desc 排全员名次（只排进有数据的）
    lb = db.execute(_text(
        """
        SELECT assignee_person_id,
               count(*) AS asked,
               count(*) FILTER (WHERE status = 'resolved') AS resolved
          FROM public.issues
         WHERE assignee_person_id IS NOT NULL
         GROUP BY assignee_person_id
        """
    )).fetchall()
    ordered = sorted(lb, key=lambda r: (-r[2], -r[1]))
    rank = None
    for i, r in enumerate(ordered):
        if r[0] == person_id:
            rank = i + 1
            break

    since = row[5].date().isoformat() if row[5] else None
    asked, resolved = int(row[0] or 0), int(row[1] or 0)
    return {
        "personId": person_id,
        "period": {
            "label": f"累计（自 {since} 起）" if since else "累计",
            "since": since,
            "window30d": "近 30 天",
        },
        "askedCount": asked,
        "resolvedCount": resolved,
        "resolveRate": round(resolved / asked, 2) if asked else None,
        "helpRank": rank,
        "helpRankTotal": len(ordered),
        "faqCount": int(faq_count),
        "avgFirstResponseHours": round(float(row[4]), 1) if row[4] is not None else None,
        "last30d": {"askedCount": int(row[2] or 0), "resolvedCount": int(row[3] or 0)},
    }


@router.get("/{person_id}/reviews", summary="Get Person Reviews", description="某人的标签历史")
def get_person_reviews(
    person_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from ...models.review import PeerReview
    from ...schemas.reviews import ReviewResponse
    from ...schemas.sessions import PaginatedResponse

    q = db.query(PeerReview).filter(PeerReview.person_id == person_id)
    total = q.count()
    items = q.order_by(PeerReview.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = []
    for r in items:
        result.append(ReviewResponse(
            id=r.id,
            personId=r.person_id,
            personName=r.person_user.name if r.person_user else None,
            reviewerId=r.reviewer_id,
            reviewer=r.reviewer_user.name if r.reviewer_user else None,
            tag=r.tag_name,
            date=str(r.created_at.date()) if r.created_at else "",
        ))
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(items=result, total=total, page=page, page_size=page_size, pages=pages)
