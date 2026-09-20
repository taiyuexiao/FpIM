# -*- coding: utf-8 -*-
"""
部门职责写入脚本（独立可运行，不依赖项目其他代码）。

把 L2/L3 共 9 个部门的职责说明写入 departments.responsibility 字段，
供数据库团队 / 服务端同学在任意环境直接运行，减少手动改库的改动成本。

数据库连接优先级（任选其一）：
  1. DATABASE_URL 环境变量（完整连接串）
  2. PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE 标准 PG 环境变量
  3. 默认：postgresql://swzr_admin@localhost:5432/shouwenzeren（口令由 PGPASSWORD 提供，不入库）

按部门 name 匹配（跨环境 id 可能不同），幂等（UPDATE 覆盖，可重复执行）。

用法示例：
  # 本地默认库
  python update_department_responsibility.py

  # 指定服务端库（如 shouwenzeren_newdb）
  DATABASE_URL=postgresql://postgres:<密码>@localhost:5432/shouwenzeren_newdb \
      python update_department_responsibility.py
  # 或走标准 PG 环境变量
  PGDATABASE=shouwenzeren_newdb PGUSER=postgres PGPASSWORD=<密码> \
      python update_department_responsibility.py

  # 先预览不落库
  python update_department_responsibility.py --dry-run
"""
import os
import sys

import psycopg2

sys.stdout.reconfigure(encoding="utf-8")

# 部门名 -> 职责说明（L2 数据管理与应用部 + L3 总经理室 / 7 科室）
RESPONSIBILITY = {
    "数据管理与应用部": "负责全行数据战略规划与数据资产管理，统筹数据治理、数据平台建设、数据开发应用、监管报送与智能创新等工作，为全行业务经营、风险管理与监管合规提供数据支撑。",
    "总经理室": "负责部门整体经营与管理，统筹党建、项目管理、数据架构与数据安全等专项工作，协调各科室业务分工，保障部门各项工作的有序推进与目标达成。",
    "综合管理部": "负责部门人事、薪酬考核、招聘培训、党建文化与合规内控等综合行政事务，统筹测试管理与项目管理工作，为部门日常运转提供行政与流程保障。",
    "数据治理部": "负责全行数据治理体系建设，统筹数据标准、数据安全与数据资产管理，推动数据分类分级、安全管控与架构规范的落地执行，保障数据质量与合规。",
    "信息管理部": "面向分行、零售、对公（非零）等业务条线提供数据应用支持，负责数据需求受理、数据分析与模型建设，推动数据赋能一线经营与客户服务。",
    "数据平台部": "负责数据平台工具与服务的建设与运营，承担数据采集调度、数据服务、数据应用开发及大数据平台运维保障，为全行数据应用提供稳定可靠的技术底座。",
    "数据开发部": "负责全行数据模型设计与数据开发，承担整合模型、数据仓库集市建设、监管报送、经营管理与风险管理数据支撑，以及数据需求接入与批量治理工作。",
    "信息统计部": "负责全行管理信息分析与监管报送工作，承担产品客户分析、管理数据分析、监管数据质量治理与监管统计报送，为经营决策与监管合规提供数据支撑。",
    "智能创新部": "负责全行人工智能与智能创新应用，承担大模型基础研发、智能体平台建设、风险模型与反电诈、AI 产品运营等工作，推动人工智能技术在业务场景的落地应用。",
}


def build_conn():
    """按 DATABASE_URL → PG 环境变量 → 默认 的优先级建立连接。"""
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)

    kwargs = {}
    if os.environ.get("PGHOST"):
        kwargs["host"] = os.environ["PGHOST"]
    if os.environ.get("PGPORT"):
        kwargs["port"] = int(os.environ["PGPORT"])
    if os.environ.get("PGUSER"):
        kwargs["user"] = os.environ["PGUSER"]
    if os.environ.get("PGPASSWORD"):
        kwargs["password"] = os.environ["PGPASSWORD"]
    if os.environ.get("PGDATABASE"):
        kwargs["dbname"] = os.environ["PGDATABASE"]

    if not kwargs:
        # 默认：本地开发库（口令由 PGPASSWORD 提供）
        return psycopg2.connect(
            "postgresql://swzr_admin@localhost:5432/shouwenzeren"
        )
    kwargs.setdefault("host", "localhost")
    kwargs.setdefault("port", 5432)
    return psycopg2.connect(**kwargs)


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("== DRY-RUN 模式：只预览匹配结果，不落库 ==\n")

    conn = build_conn()
    conn.autocommit = False
    cur = conn.cursor()
    updated, missed = 0, []
    try:
        for name, text in RESPONSIBILITY.items():
            cur.execute(
                "SELECT id, level FROM public.departments WHERE name = %s ORDER BY id",
                (name,),
            )
            rows = cur.fetchall()
            if not rows:
                missed.append(name)
                print(f"  ⚠ 未匹配到部门：{name}")
                continue
            for did, level in rows:
                if dry_run:
                    print(f"  [预览] {name} (id={did}, L{level})")
                else:
                    cur.execute(
                        "UPDATE public.departments SET responsibility = %s WHERE id = %s",
                        (text, did),
                    )
                    print(f"  ✅ {name} (id={did}, L{level}) 职责已写入")
                updated += 1

        if not dry_run:
            conn.commit()
            print(f"\n共写入 {updated} 个部门的职责说明")
        else:
            print(f"\n共匹配 {updated} 个部门（未落库）")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ 失败，已回滚：{e}")
        raise
    finally:
        cur.close()
        conn.close()

    if missed:
        print(
            f"\n⚠ 有 {len(missed)} 个部门未匹配（服务端库的部门 name 可能不同，请核对）："
        )
        for name in missed:
            print(f"    - {name}")


if __name__ == "__main__":
    main()
