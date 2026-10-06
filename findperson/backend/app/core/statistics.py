"""统计口径刷新（P3 ADM-05）：遍历 statistics_definitions 执行 formula，结果写 statistics_data"""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import text

from .database import SessionLocal
from ..models.admin import StatisticsDefinition, StatisticsData

logger = logging.getLogger(__name__)


def refresh_statistics() -> dict:
    """执行一次统计刷新：对每条 metric 执行 formula（仅允许 SELECT），
    把结果 upsert 到 statistics_data。返回 {metric_key: value}。

    单个口径失败不阻塞其他口径（捕获后跳过），便于逐步修正口径 SQL。
    """
    results: dict = {}
    db = SessionLocal()
    try:
        definitions = (
            db.query(StatisticsDefinition)
            .order_by(StatisticsDefinition.sort_order)
            .all()
        )
        today = date.today()
        for d in definitions:
            if not d or not d.formula:
                continue
            formula = d.formula.strip()
            # 安全校验：仅执行 SELECT，拒绝任意写 SQL
            if not formula.upper().startswith("SELECT"):
                logger.warning("skip non-SELECT formula for %s", d.metric_key)
                continue
            try:
                value = db.execute(text(formula)).scalar()
            except Exception as e:
                logger.warning("formula failed for %s: %s", d.metric_key, e)
                continue

            record = (
                db.query(StatisticsData)
                .filter(
                    StatisticsData.metric_key == d.metric_key,
                    StatisticsData.dimension.is_(None),
                    StatisticsData.stat_date == today,
                )
                .first()
            )
            if record:
                record.value = value
                record.updated_at = datetime.now(timezone.utc)
            else:
                db.add(StatisticsData(
                    metric_key=d.metric_key,
                    value=value,
                    stat_date=today,
                ))
            results[d.metric_key] = value

        db.commit()
    finally:
        db.close()
    return results
