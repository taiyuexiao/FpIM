"""写操作动作草稿(edit 意图 → confirmation_card,V1.2 §5.2 + 实施方案v3 §3.3)。

三类写操作:
- profile:资料维护(联系方式/负责领域/自画像等当前用户可维护字段)
- review :他人画像(为同事添加事项评价)
- content:内容发布(确认后进入待审核,不得表述为已公开发布)

职责边界:
- Agent 只产出「确认卡片草稿」,不直接写业务表;确认后的写执行由前端确认链路
  调用业务后端 API 完成(v4 §五:确认更新主页/保存评价/确认发布);
- 卡片必须含:卡片标识/动作类型/待写入字段/状态/提交目标/draftId(手动补充回填用);
- 字段不足时不编造,转为澄清追问(§18:不编造事实)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.contracts.agent_state import UserContext
from app.core import db
from app.core.llm_client import LLMPort, get_llm

ACTION_PROFILE = "profile"
ACTION_REVIEW = "review"
ACTION_CONTENT = "content"

# 他人画像事项上限(v4 §五:事项不超过 20 个字符)
REVIEW_TAG_MAX_LEN = 20

# 提交目标(前端确认后调用的业务后端 API;仅作展示与审计,不由 Agent 调用)
SUBMIT_TARGETS = {
    ACTION_PROFILE: "/api/v1/me",
    ACTION_REVIEW: "/api/v1/reviews",
    ACTION_CONTENT: "/api/v1/contents",
}

# ---------------------------------------------------------------- 多轮续接(零 LLM)
# 省略式追问:「再加一句 X」「换成 X」「再加一个 X」——有待确认草稿时直接合并,
# 不再走意图识别(A/B 实验:多轮续接准确率 72.7% → 100%,续接轮零 LLM 调用)

_CONT_MARK = re.compile(r"^(再|还|也|顺便|继续|接着|外加|加上|加|补|补充|再来|帮我把)")
_REPLACE_MARK = re.compile(r"^(改成|换成|改为|变为|变成|更新为|设置为)")


def _targets_same_field(pending_card: dict, text: str) -> bool:
    """续接文本与待确认草稿是否指向同一字段(加一句/补充到画像、再加标签、换联系方式等)。"""
    action = pending_card.get("action") or {}
    patch = action.get("nextProfilePatch") or {}
    if "selfPortrait" in patch and re.search(r"自画像|字画像|画像|简介|自我介绍", text):
        return True
    if "addDomains" in patch and re.search(r"标签|领域", text):
        return True
    if "contact" in patch and re.search(r"联系方式|电话|手机|邮箱", text):
        return True
    if action.get("type") == ACTION_REVIEW and re.search(r"标签|评价", text):
        return True
    if action.get("type") == ACTION_CONTENT and re.search(r"补充|添加|再加|加上|正文|摘要", text):
        return True
    return False


def is_continuation(text: str, pending_card: dict | None = None) -> bool:
    """判断是否为对上一轮写操作的续接(省略/追加/替换式追问)。

    三类判定:
    1. 句首续接词(再/还/也/加一句/换成…);
    2. 短句且无疑问/检索/发布词;
    3. 含追加动词且与待确认草稿指向同一字段(如已有自画像草稿时说「在我的自画像后面加一句X」)。
    """
    t = text.strip()
    # 防误判:新的写操作指令(发布/发表/投稿/删去/删除等)或长文本永远不算续接——
    # 长文里只要含「补充/添加」就会被规则3误判(如正文提到『补充新的Skill』)
    if re.match(r"^(发布|发表|投稿|写一?篇|发一?篇|删去|删除|移除|去掉)", t) or len(t) > 50:
        return False
    if _CONT_MARK.search(t) or _REPLACE_MARK.search(t):
        return True
    if len(t) <= 12 and not re.search(r"谁|怎么|怎样|什么|哪|吗|呢|找|查|请问|发布|文章", t):
        return True
    if pending_card and re.search(r"再加|加一?句|加一?个|补充|追加|加上|添加", t) \
            and _targets_same_field(pending_card, t):
        return True
    return False


def _extract_delta(text: str) -> tuple[str, str]:
    """返回 (模式, 增量内容)。replace=替换, append=追加。"""
    t = text.strip()
    m = _REPLACE_MARK.match(t)
    if m:
        return "replace", re.sub(r"^[：:，,。\s]+", "", t[m.end():]).strip()
    # 循环剥掉句首的续接标记(「再加一句」「加一句」「再补充一个」等组合)
    prev = None
    while prev != t:
        prev = t
        t = _CONT_MARK.sub("", t, count=1)
        t = re.sub(r"^(一[句个条局段次遍]|一句|一个|一局|一次|标签|领域)", "", t)
        t = t.lstrip("：:，,。\s")
    # 句中形态:「在我的自画像后面加一句 X」→ 取标记之后的内容
    m = re.search(r"(?:再加|加|补充|追加|加上|添加)(?:一[句个条]|一句|一个)?[：:，,。\s]*(.+)$", t)
    if m and re.search(r"自画像|字画像|画像|简介|自我介绍|标签|领域", t[:m.start(1)]):
        t = m.group(1)
    return "append", re.sub(r"^[：:，,。\s]+", "", t).strip()


def merge_draft(card: dict, text: str) -> dict:
    """把续接增量合并进待确认草稿(深拷贝,不改原卡)。"""
    import copy
    merged = copy.deepcopy(card)
    action = merged["action"]
    mode, delta = _extract_delta(text)
    if not delta:
        return merged
    if action["type"] == ACTION_PROFILE:
        patch = action.setdefault("nextProfilePatch", {})
        if "selfPortrait" in patch:
            patch["selfPortrait"] = (delta if mode == "replace"
                                     else f"{patch['selfPortrait']} {delta}".strip())
        elif "addDomains" in patch:
            patch["addDomains"] = [*patch["addDomains"], delta]
        elif "contact" in patch:
            patch["contact"] = delta  # 联系方式单值字段:替换
        else:
            patch["selfPortrait"] = delta
        action["changes"] = [f"{k}将更新为 {'、'.join(v) if isinstance(v, list) else v}"
                             for k, v in patch.items() if not k.startswith("_")]
    elif action["type"] == ACTION_REVIEW:
        nr = action.get("nextReview") or {}
        nr["tag"] = delta[:REVIEW_TAG_MAX_LEN]
        nr["text"] = nr["tag"]
        action["changes"] = [f"评价对象:{nr.get('personName', '')}", f"事项:{nr['tag']}"]
    elif action["type"] == ACTION_CONTENT:
        nc = action.setdefault("nextContent", {})
        nc["body"] = f"{nc.get('body', '')}\n{delta}".strip()
        action["changes"] = [f"标题:{nc.get('title', '')}", "正文已追加补充"]
    return merged


def build_continuation_card(card: dict, text: str, *, run_id: str) -> dict:
    """基于上一张待确认卡 + 续接文本,生成合并后的新确认卡(新 id/draftId)。"""
    merged = merge_draft(card, text)
    merged["id"] = f"confirm-{run_id}"
    merged["status"] = "active"
    action = merged["action"]
    action["draftId"] = f"draft-{run_id}"
    summary = "、".join(action.get("changes") or [])[:60]
    merged["analysis"] = {"intent": "edit", "actionType": action["type"],
                          "summary": f"续接合并:{summary}"}
    return merged

# 资料字段中文名(changes 展示用)
# 注意:键名必须落前端确认白名单(auth store updateProfile):contact/addDomains/selfPortrait
FIELD_LABELS = {
    "contact": "联系方式", "addDomains": "负责领域", "selfPortrait": "自画像",
    "removeDomains": "负责领域(删除)",
}

# LLM/规则提取键 → 前端可维护键(不在白名单内的键确认时会被前端丢弃)
_PATCH_KEY_MAP = {"phone": "contact", "domains": "addDomains"}
_PATCH_DROP_KEYS = {"role", "name", "phone", "domains"}  # role/name 非本人可维护项

_EXTRACT_PROMPT = """你是写操作草稿提取器。用户想在首问必答平台执行一个写操作,动作类型为 {action_type}。
从用户的话里提取草稿字段,提取不到就留空,严禁编造。

动作类型说明:
- profile(资料维护):提取 nextProfilePatch,可含 contact(联系方式)/phone(手机号)/role(岗位)/domains(负责领域,即标签,数组)/selfPortrait(自画像)
  用户说「增加/添加标签X」「增加领域X」时,把 X 原样放入 domains 数组,不要判断 X 是否合理;X 照抄原文。
  用户说「删去/删除/移除/去掉(我的)标签X」「删去(我的)领域X」时,把 X 原样放入 removeDomains 数组;X 照抄原文。
  字段归属规则:用户明确点名字段时,必须放在点名的字段——说「自画像/画像/简介」放 selfPortrait、说「负责领域/标签/领域」放 domains、说「联系方式/电话」放 contact;不要根据内容长相自行改放其他字段(即使内容看起来像职责描述,只要用户说的是自画像就放 selfPortrait)。
- review(他人画像):提取 personName(被评价人姓名)与 tag(事项标签,不超过20字)
- content(内容发布):提取 title(标题)/tags(关联领域,数组)/summary(摘要)。
  body 一律输出空字符串"":正文由系统按标题位置从原文截取,不经过你,不要在 body 里复述原文;
  summary 与 tags 的规则(默认留空,严禁自行生成):
  - 「摘要为:X」→ summary 照抄 X;「你给总结摘要/帮我总结摘要」→ 你根据 body 生成一句摘要;
  - 「关联领域为:X」→ tags 照抄拆分 X;「你给总结关联领域/帮我总结关联领域」→ 你根据 body 归纳 1-3 个领域词;
  - 用户未出现上述明确要求时,summary 与 tags 必须留空;
  - 用户可同时提出多个要求,每个要求都要处理,不得遗漏。

示例1(组合要求): 用户说「发布文章《月度复盘》,你给总结摘要,你给总结关联领域。正文:本月完成三项数据质量核查。」
输出: {{"title": "月度复盘", "tags": ["数据治理", "质量核查"], "summary": "本月完成三项数据质量核查。", "body": ""}}
示例2(未要求): 用户说「发布文章《月度复盘》,正文:本月完成三项数据质量核查。」
输出: {{"title": "月度复盘", "tags": [], "summary": "", "body": ""}}

严格输出 JSON(不要输出其他内容)。字段格式如下,值必须是从问题中提取的内容,严禁照抄示例中的空值:
{schema}

用户问题: {query}"""

_EXTRACT_SCHEMAS = {
    ACTION_PROFILE: '{"nextProfilePatch": {"contact": "", "phone": "", "role": "", "domains": [], "removeDomains": [], "selfPortrait": ""}}',
    ACTION_REVIEW: '{"personName": "", "tag": ""}',
    ACTION_CONTENT: '{"title": "", "tags": [], "summary": "", "body": ""}',
}

# 二级分流 LLM 分类兜底(规则未命中时使用;长尾说法不再依赖补规则)
_CLASSIFY_PROMPT = """你是首问必答平台的写操作分类器。判断用户想执行的写操作属于哪一类:

- profile:维护本人资料(修改自己的联系方式/负责领域/自画像/岗位等,对象是本人)
- review:为他人画像/打标签/写评价(对象必须是别人)
- content:发布/撰写内容(文章、经验、制度说明等)
- unclear:无法判断是写操作,或类型不明

严格输出 JSON(不要输出任何其他内容):
{{"action_type": "profile|review|content|unclear"}}

用户问题: {query}"""


@dataclass
class ActionDraftResult:
    """动作草稿构建结果。card 为 None 时表示字段不足需澄清/引导手动编辑。"""

    action_type: str = ""
    card: dict[str, Any] | None = None
    reply_text: str = ""
    missing: list[str] = field(default_factory=list)
    degraded: bool = False


class ActionDraftService:
    """edit 意图的动作分类与草稿提取。"""

    def __init__(self, llm: LLMPort | None = None) -> None:
        self._llm = llm

    # ---------------- 动作分类 ----------------

    @staticmethod
    def classify(query: str) -> str | None:
        """对象驱动的确定性分类(优先级:本人资料 > 内容发布 > 他人画像);不命中返回 None。

        设计要点:三类写操作的区别在【动作对象】而非动词——动词枚举永远有长尾,
        对象词表有限且稳定:
        - 对象是本人(我的资料/画像/领域/联系方式…/给我自己加标签)→ profile
        - 对象是他人(给/为/帮某人,或含 评价/画像 动作且不指向本人)→ review
        - 对象是内容(发布/文章/《》)→ content
        """
        q = query.strip()
        # 0) 内容发布强信号优先:发布动词+内容对象词(正文里常含“资料/领域/介绍”等词,
        #    若先走本人资料规则会被误判为 profile)
        if re.search(r"(发布|发表|投稿|写一?篇|发一?篇|发内容|发文章)", q) and re.search(
                r"(文章|内容|一篇|《|标题|正文|稿|帖子|推文)", q):
            return ACTION_CONTENT
        # 1) 本人资料维护:自我指代 + 资料类对象词(动词不限,防长尾)
        if re.search(r"(我的?|自己|本人)", q) and re.search(
                r"(资料|信息|联系方式|电话|手机|邮箱|负责领域|领域|自画像|字画像|画像|岗位|主页|简介|自我介绍|签名)", q):
            return ACTION_PROFILE
        # 「删去/删除/移除我的标签X」→ 本人负责领域删除
        if re.search(r"(删去|删除|移除|去掉).{0,8}(标签|领域)", q):
            return ACTION_PROFILE
        # 「给我自己/本人 添加X标签/领域」→ 本人负责领域
        if re.search(r"(为|给|帮)?(我自己|本人|我).{0,4}(添加|增加|加|补).{0,8}(标签|领域)", q):
            return ACTION_PROFILE
        # 「我现在/目前负责 X」→ 负责领域变更(核心业务原话用例)
        if re.search(r"我(现在|目前|如今)?负责", q):
            return ACTION_PROFILE
        # 2) 内容发布
        if re.search(r"(发布|发一?篇|投稿|写一?篇|发内容|发文章)", q):
            return ACTION_CONTENT
        # 3) 他人画像:「给/为/帮/替 XX 添加标签/评价/画像」
        if re.search(r"(为|给|帮|替).{1,8}(添加|增加|加|写|补).{0,4}(标签|评价|画像)", q):
            return ACTION_REVIEW
        # 含 评价/画像 动作但对象不是本人资料(防"自画像"误入)
        if re.search(r"(评价|点评|打标签|写标签|画像)", q) and not re.search(
                r"我的?(自画像|字画像|画像|资料|领域|联系方式|电话|岗位|主页|简介|自我介绍)", q):
            return ACTION_REVIEW
        return None

    # ---------------- 草稿构建 ----------------

    async def build(self, query: str, user_context: UserContext, *,
                    run_id: str, history: list[dict] | None = None) -> ActionDraftResult:
        action_type = self.classify(query)
        if action_type is None:
            # 规则快速路径未命中:LLM 分类兜底(带会话记忆,省略式追问也能分流)
            action_type = await self._classify_with_llm(query, history=history)
        if action_type is None:
            return ActionDraftResult(
                reply_text=("我识别到您想执行写操作,但没有完全确认类型。您可以这样说:"
                            "『修改我的联系方式为…』、『为张三添加评价:…』、『发布一篇文章:…』。"))
        # 仅他人画像需要人名词典(评价对象兑底);DB 故障不阻断其余动作
        name_to_id: dict[str, str] = {}
        if action_type == ACTION_REVIEW:
            try:
                name_to_id = await self._known_people_map(query, exclude=user_context.name)
            except Exception:  # noqa: BLE001
                name_to_id = {}
        extracted, degraded = await self._extract(action_type, query)
        builder = {
            ACTION_PROFILE: self._build_profile,
            ACTION_REVIEW: self._build_review,
            ACTION_CONTENT: self._build_content,
        }[action_type]
        if action_type == ACTION_PROFILE:
            result = await builder(query, user_context, run_id=run_id, extracted=extracted,
                                   names=name_to_id)
        else:
            result = builder(query, user_context, run_id=run_id, extracted=extracted,
                             names=name_to_id)
        result.action_type = action_type
        result.degraded = result.degraded or degraded
        return result

    # ---------------- LLM 分类兜底 ----------------

    async def _classify_with_llm(self, query: str, *, history: list[dict] | None = None) -> str | None:
        """约束 JSON 让 LLM 判断写操作类型;失败/非法输出返回 None(走套话澄清)。

        带会话记忆:省略式追问(「再加一句X」)能从上文意图/槽位继承类型。"""
        llm = self._llm or get_llm()
        history_block = ""
        if history:
            from app.agent.memory import format_history
            text = format_history(history, max_chars=200)
            if text:
                history_block = f"对话历史与记忆(供理解追问/指代):\n{text}\n\n"
        try:
            data, _ = await llm.structured_chat(
                [{"role": "user", "content": history_block + _CLASSIFY_PROMPT.format(query=query)}],
                required_keys=["action_type"])
            value = str(data.get("action_type") or "").strip()
            return value if value in (ACTION_PROFILE, ACTION_REVIEW, ACTION_CONTENT) else None
        except Exception:  # noqa: BLE001 —— LLM 失败:不猜测,交给澄清话术
            return None

    # ---------------- 三类草稿 ----------------

    async def _build_profile(self, query, ctx: UserContext, *, run_id, extracted, names) -> ActionDraftResult:
        patch = {k: v for k, v in (extracted.get("nextProfilePatch") or {}).items()
                 if v not in (None, "", [])}
        # LLM 偶发把数组字段返回成字符串,归一为数组
        for list_key in ("addDomains", "removeDomains"):
            if isinstance(patch.get(list_key), str):
                patch[list_key] = [t.strip() for t in re.split(r"[,、,]", patch[list_key]) if t.strip()]
        if not patch:
            # 规则兑底 0:「删去/删除/移除(我的)(标签/领域) X」→ 负责领域删除
            m = re.search(r"(?:删去|删除|移除|去掉)(?:我的)?(?:一?个|一条)?(?:标签|领域|负责领域)?[：:，,\s]*([^,，。！？!?]{1,20})", query)
            if m:
                patch = {"removeDomains": [m.group(1).strip()]}
        if not patch:
            # 规则兑底 1:「电话/联系方式 ... X」(兼容 改为/修改为/是 等说法)
            m = re.search(r"(?:联系方式|电话|手机)[^0-9]{0,6}([0-9][0-9\-]{3,})", query)
            if m:
                patch = {"contact": m.group(1)}
        if not patch:
            # 规则兑底 2:「我现在/目前负责 X」→ 负责领域新增
            m = re.search(r"我(?:现在|目前|如今)?负责([^,，。！？!?]{2,30})", query)
            if m:
                patch = {"addDomains": [m.group(1).strip()]}
        if not patch:
            # 规则兑底 3:「(给我自己)添加/增加 X 标签/领域」或「标签/领域:X」→ 负责领域新增
            m = re.search(r"(?:添加|增加|加|补充)(?:一?个|一条)?([^,，。！？!?]{1,20}?)(?:标签|领域)", query)
            if not m:
                # 「增加/添加标签 X」(标签词在前,值在后)
                m = re.search(r"(?:添加|增加|加|补充)(?:一?个|一条)?(?:标签|领域)[：:，,\s]*([^,，。！？!?]{1,20})", query)
            if not m:
                m = re.search(r"(?:标签|领域)[：:]([^,，。！？!?]{1,20})", query)
            if m:
                patch = {"addDomains": [m.group(1).strip()]}
        if not patch:
            # 规则兑底 4:「(自|字)画像 改为/是/为 X」→ 自画像更新
            m = re.search(r"(?:自画像|字画像|画像)[^,，。！？!?]{0,4}(?:改为|改成|更新为|变为|是|为)([^,，。！？!?]{1,50})", query)
            if m:
                patch = {"selfPortrait": m.group(1).strip()}
        if not patch:
            # 规则兑底 5:「(在)(我的)(自)画像(后面/后/里)新增/补充/添加 X」→ 自画像追加
            m = re.search(r"(?:新增|添加|补充|加上|加一?句|补一?句)[^,，。！？!?]{0,6}?([^,，。！？!?]{1,50})", query)
            if m and re.search(r"(自画像|字画像|画像|简介|自我介绍)", query):
                patch = {"selfPortrait": m.group(1).strip(), "_append": True}
        if not patch:
            return ActionDraftResult(
                action_type=ACTION_PROFILE,
                reply_text=("请告诉我您要更新哪项资料(联系方式/负责领域/自画像/岗位)以及新内容,"
                            "例如『把我的负责领域更新为 RAG、知识检索』。"),
                missing=["nextProfilePatch"])
        # 追加语义:「新增/补充/添加/再加 X」且落到自画像/领域字段 → 与现有内容合并(避免覆盖原文)
        # 注:不再要求句中出现“画像”字样(「再加一句 红色警戒20年老玩家」这种省略说法也要追加)
        append_mode = patch.pop("_append", False) or bool(
            re.search(r"(新增|添加|增加|补充|加上|再加|再添|加一?句|补一?句|添一?句)", query)
            and ("selfPortrait" in patch or "addDomains" in patch))
        if append_mode and patch.get("selfPortrait"):
            try:
                row = await db.fetchrow("SELECT self_portrait FROM public.people WHERE id=$1", ctx.user_id)
                current = (row["self_portrait"] or "").strip() if row else ""
                addition = str(patch["selfPortrait"]).strip()
                if current and addition and addition not in current:
                    patch["selfPortrait"] = f"{current} {addition}"
            except Exception:  # noqa: BLE001 —— 读取失败则保持新增内容,由用户确认前可见
                pass
        # 键名归一:phone→contact、domains→addDomains;剔除前端不可维护字段
        normalized: dict = {}
        for key, value in patch.items():
            mapped = _PATCH_KEY_MAP.get(key, key)
            if mapped in FIELD_LABELS and mapped not in normalized:
                normalized[mapped] = value
        patch = normalized
        if not patch:
            return ActionDraftResult(
                action_type=ACTION_PROFILE,
                reply_text=("识别到的字段不在本人可维护范围(联系方式/负责领域/自画像),"
                            "岗位/姓名等请联系管理员变更。"),
                missing=["nextProfilePatch"])
        changes = [f"{FIELD_LABELS.get(k, k)}将更新为 {('、'.join(v) if isinstance(v, list) else v)}"
                   for k, v in patch.items()]
        card = self._card(ACTION_PROFILE, run_id, {
            "type": ACTION_PROFILE,
            "draftId": f"draft-{run_id}",
            "title": "检测到资料维护需求",
            "description": "识别到你要更新本人资料,确认后仅更新你可维护的字段。",
            "changes": changes,
            "nextProfilePatch": patch,
        }, summary=f"更新资料:{ '、'.join(patch.keys()) }")
        return ActionDraftResult(
            action_type=ACTION_PROFILE, card=card,
            reply_text="已为您整理资料变更草稿,确认后仅更新您本人可维护的字段。",
        )

    def _build_review(self, query, ctx: UserContext, *, run_id, extracted, names) -> ActionDraftResult:
        person_name = str(extracted.get("personName") or "").strip()
        if not person_name and names:
            person_name = next(iter(names.keys()), "")
        tag = str(extracted.get("tag") or "").strip()[:REVIEW_TAG_MAX_LEN]
        if not tag:
            # 规则兑底:「评价:事项」「画像:事项」
            m = re.search(r"(?:评价|画像|点评|标签)[:：]([^,，。！？!?]{1,20})", query)
            if m:
                tag = m.group(1).strip()[:REVIEW_TAG_MAX_LEN]
        if not person_name:
            return ActionDraftResult(
                action_type=ACTION_REVIEW,
                reply_text="请补充评价对象和事项标签,例如『为李四添加评价:模型网关排障』(事项不超过 20 字)。",
                missing=["personName"])
        if person_name == ctx.name:
            return ActionDraftResult(
                action_type=ACTION_REVIEW,
                reply_text="他人画像不能评价本人,请确认评价对象。",
                missing=["personName"])
        person_id = names.get(person_name, "")
        if not person_id:
            # LLM 写出与库内不一致的名字时,尝试库内模糊互包含匹配
            person_id = next((pid for n, pid in names.items()
                              if person_name in n or n in person_name), "")
        if not person_id:
            return ActionDraftResult(
                action_type=ACTION_REVIEW,
                reply_text=(f"没有在名录中找到「{person_name}」,请确认姓名后再试,"
                            "或点『继续修改』在画像页手动选择同事。"),
                missing=["personName"])
        # 字段不完整仍出部分草稿卡(v4 §五:手动补充经 draftId 回填)
        card = self._card(ACTION_REVIEW, run_id, {
            "type": ACTION_REVIEW,
            "draftId": f"draft-{run_id}",
            "title": "为你生成一条待确认评价",
            "description": f"评价对象:{person_name};确认保存后写入其画像。",
            "changes": [f"评价对象:{person_name}", f"事项:{tag or '(待补充)'}",
                        f"日期:{date.today().isoformat()}"],
            "nextReview": {
                "personName": person_name,
                "personId": person_id,
                "tag": tag,
                "text": tag,  # 前端评价卡渲染 nextReview.text
                "date": date.today().isoformat(),
            },
        }, summary=f"为 {person_name} 添加事项:{tag or '(待补充)'}")
        if not tag:
            return ActionDraftResult(
                action_type=ACTION_REVIEW, card=card,
                reply_text=(f"已生成对 {person_name} 的画像评价草稿,还请补充事项标签;"
                            "可点『继续修改』进入画像页补全后保存。"),
                missing=["tag"])
        return ActionDraftResult(
            action_type=ACTION_REVIEW, card=card,
            reply_text=f"已生成对 {person_name} 的画像评价草稿,确认保存后写入其他画像。",
        )

    def _build_content(self, query, ctx: UserContext, *, run_id, extracted, names) -> ActionDraftResult:
        title = str(extracted.get("title") or "").strip()
        summary = str(extracted.get("summary") or "").strip()
        body = str(extracted.get("body") or "").strip()
        # 规则兑底:从原文确定性抽取标题/正文/摘要(LLM 漏抽时补)
        r_title, r_summary, r_body = self._extract_content_parts(query)
        title = title or r_title
        body = body or r_body
        if not body and title:
            # 标题锚定截取正文:长文正文不走 LLM(复述长文输出慢且易截断/超时),
            # 按标题在原文中的位置取其后的全部文字,保真且瞬时
            idx = query.find(title)
            if idx >= 0:
                rest = re.sub(r"^[，,。:：;；\s]+", "", query[idx + len(title):])
                if len(rest) >= 2:
                    body = rest.strip()
        summary = summary or r_summary
        # 摘要/关联领域默认不填:仅用户明确要求时保留(防 LLM 自行概括);
        # 明确要求指:原文出现「摘要」(如 摘要为:X/你给总结摘要)或「关联领域/领域/标签」字样
        if not re.search(r"摘要", query):
            summary = ""
        tags = extracted.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,、,]", tags) if t.strip()]
        if not re.search(r"(关联领域|领域|标签)", query):
            tags = []
        if not title and body:
            # 标题实在抽不到但有正文:用正文首句当标题,保证草稿可用
            title = re.split(r"[。!?!?\n]", body, maxsplit=1)[0].strip()[:30] or "未命名内容"
        if not title:
            return ActionDraftResult(
                action_type=ACTION_CONTENT,
                reply_text="请补充内容标题和摘要(正文可手动补充),例如『发布文章《K8s 部署实践》,摘要:…』。",
                missing=["title"])
        # 摘要/关联领域未明确要求时保持为空(属正常草稿,不再视为缺失字段)
        card = self._card(ACTION_CONTENT, run_id, {
            "type": ACTION_CONTENT,
            "draftId": f"draft-{run_id}",
            "title": "已整理内容发布草稿",
            "description": "确认发布后进入待审核状态,审核通过前不会对外公开。",
            "changes": [f"标题:{title}"]
                       + ([f"关联领域:{'、'.join(tags)}"] if tags else [])
                       + ([f"摘要:{summary[:40]}"] if summary else [])
                       + ([f"正文:已识别 {len(body)} 字"] if body else []),
            "nextContent": {"title": title, "tags": tags,
                            "summary": summary, "body": body or summary},
        }, summary=f"发布内容:{title}")
        return ActionDraftResult(
            action_type=ACTION_CONTENT, card=card,
            reply_text="已生成内容草稿,确认发布后进入待审核状态(审核通过前不会对外公开)。",
        )

    @staticmethod
    def _extract_content_parts(query: str) -> tuple[str, str, str]:
        """从发布请求原文确定性抽取 (标题, 摘要, 正文);抽不到留空。

        支持的说法:
        - 《标题》 / 标题是X / 标题:X
        - 摘要:X / 摘要是X
        - 正文:X / 正文是X(之后全部)
        - 无显式正文标记时:标题声明片段之后的剩余文本(≥15字)视为正文
        """
        title = summary = body = ""
        title_span: tuple[int, int] | None = None
        m = re.search(r"《([^》]{2,60})》", query)
        if m:
            title, title_span = m.group(1).strip(), m.span()
        if not title:
            m = re.search(r"标题\s*[是为：:]\s*([^,，。!?!?；;\n]{2,60})", query)
            if m:
                title, title_span = m.group(1).strip(), m.span()
        if not title:
            m = re.search(r"一?篇(?:内容|文章)?[,，]?(?:题目是|叫)?([^,，。!?!?]{2,30})", query)
            if m:
                title, title_span = m.group(1).strip(), m.span()
        m = re.search(r"摘要\s*[是为：:]\s*([^。!?!?\n]{2,120})", query)
        if m:
            summary = m.group(1).strip()
        m = re.search(r"正文\s*[是为：:]\s*(.+)$", query, re.S)
        if m:
            body = m.group(1).strip()
        if not body and title_span and title_span[1] < len(query):
            rest = query[title_span[1]:]
            rest = re.sub(r"^[，,。:：;；\s]*(正文)?[是为：:]?\s*", "", rest)
            if len(rest) >= 15:
                body = rest.strip()
        return title, summary, body

    # ---------------- 内部 ----------------

    @staticmethod
    def _card(action_type: str, run_id: str, action: dict, *, summary: str) -> dict:
        return {
            "id": f"confirm-{run_id}",
            "kind": "confirmation",
            "action": action,
            "analysis": {"intent": "edit", "actionType": action_type, "summary": summary},
            "status": "active",
            "submitTarget": SUBMIT_TARGETS[action_type],
        }

    async def _extract(self, action_type: str, query: str) -> tuple[dict, bool]:
        """LLM 草稿字段提取;失败返回空骨架 + degraded(由调用方走规则/澄清)。"""
        llm = self._llm or get_llm()
        try:
            data, _ = await llm.structured_chat(
                [{"role": "user", "content": _EXTRACT_PROMPT.format(
                    action_type=action_type, schema=_EXTRACT_SCHEMAS[action_type], query=query)}],
                required_keys=list(__import__("json").loads(_EXTRACT_SCHEMAS[action_type]).keys()),
            )
            return data, False
        except Exception:  # noqa: BLE001 —— LLM 失败:空骨架,降级
            return {}, True

    @staticmethod
    async def _known_people_map(query: str, *, exclude: str = "") -> dict[str, str]:
        """文中显式出现的人名 → id(用于 review 对象兜底),排除本人。"""
        rows = await db.fetch("SELECT id, name FROM public.people WHERE status='active'")
        return {r["name"]: r["id"] for r in rows
                if r["name"] in query and r["name"] != exclude}
