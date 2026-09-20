"""内容发布/变更事件信号（P5）

后端在内容「审核通过发布 / 编辑已发布内容 / 删除已发布内容」后，向
`rag.publish_events` 写一条事件，供 RAG 服务（knowledge-service）消费后触发
`generate-from-db` + `index` 重新索引。

只发事件信号，不重复实现 RAG 的切片 / 向量化 / 入库逻辑。
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# 事件类型
CONTENT_PUBLISHED = "content_published"
CONTENT_CHANGED = "content_changed"
CONTENT_DELETED = "content_deleted"
PERSON_CHANGED = "person_changed"  # 资料/负责领域/画像变更,resource_id=人员ID


def emit_publish_event(
    db: Session,
    event_type: str,
    resource_id: str,
    created_by: str | None = None,
) -> None:
    """写入一条发布/变更事件（与调用方同一事务，随 db.commit 一并提交）。"""
    db.execute(
        text(
            "INSERT INTO rag.publish_events (event_type, resource_id, status, created_by) "
            "VALUES (:event_type, :resource_id, 'pending', :created_by)"
        ),
        {"event_type": event_type, "resource_id": resource_id, "created_by": created_by},
    )
