"""各类业务数据 → OKF 文档的构建器(V1.2 §10.4 / §10.5)。

PersonProfile 字段白名单(§10.4):
  进 OKF/RAG:正式职责描述、负责领域叙述性正文、自我介绍正文、项目经历正文、他人评价聚合正文(低权重)
  不进:raw_tags、person_tags、动态 concept_ids、动态推断标签、Agent 内部权重
"""
from __future__ import annotations

import json

from app.contracts.okf import OkfDocument, OkfMetadata, OkfStatus, OkfType, Visibility


def _as_list(value) -> list:
    """JSONB 字段经 asyncpg 读出时是字符串,统一还原成 list(否则会被逐字拆开)。"""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return list(parsed) if isinstance(parsed, list) else []
    return list(value)


def build_responsibility_doc(ra: dict, *, intake_department: str,
                             owner_department: str, owner_name: str) -> OkfDocument:
    """责任事项 → OKF ResponsibilityItem(§10.5 发布链)。"""
    body = (
        f"{ra['title']}由{owner_department}负责。\n\n"
        f"主要职责包括:\n{ra['description']}\n\n"
        f"- 受理部门:{intake_department}\n"
        f"- 责任部门:{owner_department}\n"
        f"- 责任人:{owner_name}({ra['owner_role']})\n"
        f"- 时限:{ra['time_limit']}\n"
        f"- 转办条件:{ra['transfer_condition']}\n"
        f"- 升级路径:{ra['escalation_path']}\n"
    )
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.RESPONSIBILITY,
            id=f"responsibility-{ra['id']}",
            title=ra["title"],
            status=OkfStatus.DRAFT,
            visibility=Visibility.INTERNAL,
            sensitivity=0,
            source_type="public.responsibility_assignments",
            source_id=str(ra["id"]),
            source_uri=f"public.responsibility_assignments/{ra['id']}",
            owner_department_id=str(ra["owner_department_id"]) if ra["owner_department_id"] is not None else "",
        ),
        body=body,
        extra={
            "intake_department": intake_department,
            "owner_department": owner_department,
            "owner_person_id": ra["owner_person_id"] or "",
            "owner_role": ra["owner_role"],
            "time_limit": ra["time_limit"],
            "transfer_condition": ra["transfer_condition"],
            "escalation_path": ra["escalation_path"],
        },
    )


# PersonProfile 允许进入正文的字段白名单(§10.4)
PERSON_PROFILE_ALLOWED = ("name", "department", "role", "self_portrait")


def build_person_profile_doc(person: dict, *, reviews_text: str = "") -> OkfDocument:
    """人员 → PersonProfile OKF(§10.4 字段白名单过滤)。

    只取白名单字段组织叙述性正文;raw_tags/person_tags/concept_ids 等动态
    数据留在 agent schema,绝不写入(§10.4 红线)。
    """
    filtered = {k: person[k] for k in PERSON_PROFILE_ALLOWED if k in person}
    parts = [
        f"{filtered.get('name','')},{filtered.get('department','')}{filtered.get('role','')}。",
    ]
    portrait = (filtered.get("self_portrait") or "").strip()
    if portrait:
        parts.append(f"\n自我介绍:\n{portrait}")
    if reviews_text.strip():
        # 他人评价聚合正文:可进入,低权重(§10.4)
        parts.append(f"\n同事评价(聚合):\n{reviews_text.strip()}")
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.PEOPLE,
            id=f"person-{person['id']}",
            title=f"{person['name']}({person['role']})",
            status=OkfStatus.DRAFT,
            visibility=Visibility.INTERNAL,
            sensitivity=0,
            source_type="public.people",
            source_id=person["id"],
            source_uri=f"public.people/{person['id']}",
            owner_department_id=person.get("department_id"),
        ),
        body="\n".join(parts),
        extra={"has_review_narrative": bool(reviews_text.strip())},
    )


def build_content_doc(content: dict, *, owner_name: str,
                      owner_department_id: int | None) -> OkfDocument:
    """文章/内容 → OKF Content。owner_department 取作者所属部门(§10.1 必备字段)。"""
    tags = "、".join(_as_list(content.get("tags")))
    body = f"{content['title']}\n\n{content['body']}"
    if tags:
        body += f"\n\n主题:{tags}"
    body += f"\n\n作者:{owner_name}"
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.CONTENT,
            id=f"content-{content['id']}",
            title=content["title"],
            status=OkfStatus.DRAFT,
            visibility=Visibility.INTERNAL,
            sensitivity=0,
            source_type="public.contents",
            source_id=content["id"],
            source_uri=f"public.contents/{content['id']}",
            owner_department_id=owner_department_id,
        ),
        body=body,
        extra={"author_person_id": content.get("owner_id") or "",
               "tags": _as_list(content.get("tags"))},
    )


def build_faq_doc(faq: dict, *, owner_name: str = "",
                  owner_department_id: int | None = None) -> OkfDocument:
    """用户提问沉淀的 FAQ → OKF Faq。

    模板必备字段(frontmatter/extra):question / answer / owner / scope / tags / source。
    来源:public.faqs(问题跟踪的沉淀候选经人工确认后写入)。
    """
    tags = "、".join(_as_list(faq.get("tags")))
    body = f"问题:{faq['question']}\n\n答案:{faq['answer']}"
    if tags:
        body += f"\n\n主题:{tags}"
    if owner_name:
        body += f"\n\n责任人:{owner_name}"
    if faq.get("asked_count"):
        body += f"\n\n被问次数:{faq['asked_count']}"
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.FAQ,
            id=f"faq-{faq['id']}",
            title=(faq["question"] or "")[:120],
            status=OkfStatus.DRAFT,          # publish() 写入前会置为 published
            visibility=Visibility.INTERNAL,  # 可见范围由 scope_department_ids 控制(空=全公司)
            sensitivity=0,
            source_type="public.faqs",
            source_id=str(faq["id"]),
            source_uri=f"public.faqs/{faq['id']}",
            owner_department_id=owner_department_id,
        ),
        body=body,
        extra={"question": faq["question"], "answer": faq["answer"],
               "owner_person_id": faq.get("owner_person_id") or "",
               "owner_name": owner_name,
               "tags": _as_list(faq.get("tags")),
               "scope_department_ids": _as_list(faq.get("scope_department_ids")),
               "source": faq.get("source") or "",
               "asked_count": faq.get("asked_count") or 0},
    )


def build_department_doc(dept: dict, *, member_count: int) -> OkfDocument:
    """部门 → OKF Department。"""
    body = f"{dept['name']},组织路径:{dept['path'] or dept['name']},在编 {member_count} 人。"
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.DEPARTMENT,
            id=f"department-{dept['id']}",
            title=dept["name"],
            status=OkfStatus.DRAFT,
            visibility=Visibility.INTERNAL,
            sensitivity=0,
            source_type="public.departments",
            source_id=str(dept["id"]),
            source_uri=f"public.departments/{dept['id']}",
            owner_department_id=dept["id"],
        ),
        body=body,
        extra={"path": dept["path"], "member_count": member_count},
    )
