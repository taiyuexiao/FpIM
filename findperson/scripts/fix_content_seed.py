#!/usr/bin/env python3
"""
首问责任平台 — 发布内容种子数据生成脚本
────────────────────────────────────────
背景：seed.sql 里 593 篇合成文章（A00001~A00593）的标题/标签/摘要/正文是
      自动生成的口径，标题带「总体负责人与接口-总体负责人-双层校验」冗余后缀，
      摘要以「## 背景与目标」开头，正文是反复套模板的空话，展示时不正经。

处理：只重写 public.contents 的合成文章行（state.js 的 14 篇 A00594~A00607 不动）。
      1. 标题  -> 「{领域}{主题}：{定位}」；重复时追加「（{技术词}）」去重
      2. 标签  -> 去掉末尾含「双层校验」的冗余标签
      3. 摘要  -> 一句面向该领域/定位的摘要
      4. 正文  -> 四段式正文，按「领域 × 定位 × 主题 × 技术词」组合生成，
                  贴合该岗位职责，不是通用空话

用法：python scripts/fix_content_seed.py [seed.sql 路径 ...]
      默认为 scripts/seed.sql（唯一的 seed 文件，不再往 database/ 复制副本）。
"""

import collections
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = [BASE / "scripts" / "seed.sql"]

# 合成文章 ID 上限（含），之后是 state.js 导入的 14 篇，保持原样
SYN_ID_MAX = 593

# 主题词（每个前缀末尾 4 字），用于把「领域+主题」拆开
TOPICS = ["性能治理", "接入规范", "故障排查", "安全控制", "容量规划", "运维手册", "架构设计", "实践复盘"]

# 定位（concept）→ (职责聚焦, 落地要点)
CONCEPT_FOCUS = {
    "总体负责人": ("统筹协调与责任划分", "明确首问责任人与协助方，建立协同链路并统一口径"),
    "研发负责人": ("技术方案与研发流程把关", "制定技术规范，把控关键设计评审与交付节奏"),
    "部署运维": ("环境部署与运行保障", "规范发布流程，做好变更记录与灰度验证"),
    "性能优化": ("性能分析与瓶颈治理", "建立性能基线，结合压测定位瓶颈并验证优化效果"),
    "安全权限": ("权限管控与安全合规", "落实最小权限原则，定期审计并跟进漏洞修复"),
    "监控排障": ("监控体系与故障定位", "完善监控指标与告警阈值，缩短故障定位时间"),
    "资源成本": ("资源规划与成本核算", "建立资源台账，定期评估容量并推进降本"),
    "接入集成": ("接口对接与系统集成", "统一接口契约，规范联调流程与兼容性验证"),
}

# 主题 → (方法论标题, 具体方法)
TOPIC_METHOD = {
    "性能治理": ("建立性能指标体系", "覆盖关键环节的时延、吞吐与错误率，结合压测与线上监控持续跟踪"),
    "接入规范": ("统一接入标准", "规范申请、审批与联调流程，确保接入可追溯、可回滚"),
    "故障排查": ("形成结构化排查路径", "按现象、指标、日志逐层定位，先隔离再修复，避免凭经验误判"),
    "安全控制": ("识别关键风险点", "落实最小权限与审计留痕，整改闭环并定期复评"),
    "容量规划": ("建立容量评估机制", "基于历史趋势与峰值预估资源，制定扩容与降本方案"),
    "运维手册": ("沉淀标准化操作", "形成日常运维与应急预案，降低人工误操作风险"),
    "架构设计": ("遵循架构设计原则", "坚持高内聚低耦合，关键决策评审并记录取舍依据"),
    "实践复盘": ("还原问题全链路", "定位根因并形成可复用的处置经验，纳入知识沉淀"),
}


def parse_title(title):
    """拆分合成文章标题 -> (prefix, domain, topic, concept, tech)。"""
    prefix, tail = (title.split("：", 1) + [""])[:2] if "：" in title else (title, "")
    domain, topic = "", ""
    for t in TOPICS:
        if prefix.endswith(t):
            domain, topic = prefix[:-len(t)], t
            break
    if not domain:
        domain, topic = prefix, ""
    concept, tech = "", ""
    if tail:
        concept, _, rest = tail.partition("与")
        tech = rest.split("-", 1)[0] if rest else ""
    return prefix, domain.strip(), topic, concept.strip(), tech.strip()


def clean_tags(tags_field):
    """去掉含「双层校验」的冗余标签，返回 JSON 字符串。"""
    try:
        tags = json.loads(tags_field)
    except Exception:
        return tags_field
    if not isinstance(tags, list):
        return tags_field
    return json.dumps([t for t in tags if "双层校验" not in t], ensure_ascii=False)


def build_summary(domain, topic, concept, tech):
    concept = concept or "相关"
    return f"本文面向{domain}方向的{concept}，围绕{topic}梳理关键要点、常见问题与落地方法，供相关岗位同事参考。"


def build_body(domain, topic, concept, tech):
    concept = concept or "相关"
    focus, method = CONCEPT_FOCUS.get(concept, ("相关工作", "规范操作流程、做好过程留痕"))
    method_title, method_detail = TOPIC_METHOD.get(topic, ("持续跟踪", "结合实际情况持续优化"))
    tech_part = f"，重点关注{tech}相关的配置、监控与异常处置" if tech else ""

    return (
        f"本文面向{domain}方向的{concept}，梳理{topic}工作中的关键要点与落地方法。\n\n"
        f"一、职责边界\n"
        f"{concept}需牵头{focus}，{method}，避免出现责任空白或口径不一的情况。\n\n"
        f"二、治理方法\n"
        f"围绕{topic}，建议{method_title}{tech_part}，并结合实际场景持续优化。\n\n"
        f"三、常见问题与处置\n"
        f"常见问题集中在流程衔接、口径确认与异常处置。遇到边界不清或口径不一致的情况，应及时向上游确认，先隔离再修复，避免凭经验直接下结论。\n\n"
        f"四、经验沉淀\n"
        f"将高频问题与处置方法沉淀为操作手册，并在每次变更后复盘，持续更新责任边界与协作链路。"
    )


def escape_copy(value):
    """把普通文本转成 COPY 格式字面量（\\n/\\r/\\t/\\\\ 转义）。"""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def transform_file(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    start = None
    for i, line in enumerate(lines):
        if line.startswith("COPY public.contents "):
            start = i
            break
    if start is None:
        print(f"  [skip] {path}: 未找到 COPY public.contents")
        return

    end = start
    while end < len(lines) and not lines[end].startswith("\\."):
        end += 1

    title_dup = collections.Counter()
    parsed = []

    for i in range(start + 1, end):
        line = lines[i]
        if not line.strip():
            parsed.append((i, None, None, None, None, None))
            continue
        fields = line.split("\t")
        if len(fields) != 18:
            parsed.append((i, None, None, None, None, None))
            continue
        try:
            idnum = int(fields[0][1:])
        except ValueError:
            parsed.append((i, None, None, None, None, None))
            continue
        if idnum > SYN_ID_MAX:
            parsed.append((i, None, None, None, None, None))
            continue
        prefix, domain, topic, concept, tech = parse_title(fields[2])
        parsed.append((i, fields, domain, topic, concept, tech))
        title_dup[f"{prefix}：{concept}"] += 1

    changed = 0
    for i, fields, domain, topic, concept, tech in parsed:
        if fields is None:
            continue
        prefix = f"{domain}{topic}"
        base = f"{prefix}：{concept}"
        new_title = base
        if title_dup[base] > 1:
            new_title = f"{base}（{tech}）" if tech else f"{base}（{title_dup[base]}）"

        fields[2] = escape_copy(new_title)
        fields[3] = clean_tags(fields[3])
        fields[4] = escape_copy(build_summary(domain, topic, concept, tech))
        fields[5] = escape_copy(build_body(domain, topic, concept, tech))

        lines[i] = "\t".join(fields)
        changed += 1

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [ok] {path}: 生成 {changed} 篇合成文章")


def main():
    targets = [Path(p) for p in (sys.argv[1:] or DEFAULT_TARGETS)]
    for t in targets:
        if t.exists():
            transform_file(t)
        else:
            print(f"  [skip] 不存在: {t}")


if __name__ == "__main__":
    main()
