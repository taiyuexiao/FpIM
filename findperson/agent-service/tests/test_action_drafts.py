"""动作草稿(三类 confirmation 动作)单元测试。

分类规则与卡片结构为纯逻辑;LLM 提取用 stub 注入,不访问网络/DB。
"""
from app.agent.action_drafts import (
    ACTION_CONTENT, ACTION_PROFILE, ACTION_REVIEW, ActionDraftService,
)
from app.contracts.agent_state import UserContext

CTX = UserContext(user_id="p-0001", name="王丹")


class StubLLM:
    """按 action_type 返回固定提取结果的 LLM stub。"""

    def __init__(self, payload: dict):
        self._payload = payload

    async def structured_chat(self, messages, *, required_keys, **kwargs):
        return self._payload, None

    async def chat(self, messages, **kwargs):
        raise NotImplementedError


# ---------------- 分类规则 ----------------

def test_classify_review() -> None:
    assert ActionDraftService.classify("为张三添加评价:模型网关排障") == ACTION_REVIEW
    assert ActionDraftService.classify("给李四补一条画像,事项是 K8s 部署") == ACTION_REVIEW


def test_classify_content() -> None:
    assert ActionDraftService.classify("发布一篇文章《RAG 实践》") == ACTION_CONTENT
    assert ActionDraftService.classify("帮我投稿一篇知识检索总结") == ACTION_CONTENT


def test_classify_profile() -> None:
    assert ActionDraftService.classify("修改我的联系方式为 1234") == ACTION_PROFILE
    assert ActionDraftService.classify("更新我的负责领域") == ACTION_PROFILE


def test_classify_unknown() -> None:
    assert ActionDraftService.classify("谁负责 Dify 平台") is None


# ---------------- 卡片构建 ----------------

async def test_profile_card() -> None:
    svc = ActionDraftService(llm=StubLLM({
        "nextProfilePatch": {"contact": "1234", "domains": ["RAG", "知识检索"]}}))
    result = await svc.build("修改我的联系方式为 1234,领域改为 RAG 和知识检索", CTX, run_id="r1")
    assert result.action_type == ACTION_PROFILE
    card = result.card
    assert card["kind"] == "confirmation" and card["status"] == "active"
    assert card["action"]["type"] == ACTION_PROFILE
    assert card["action"]["nextProfilePatch"]["contact"] == "1234"
    assert card["action"]["draftId"]
    assert card["submitTarget"]


async def test_review_card_and_validation() -> None:
    svc = ActionDraftService(llm=StubLLM({"personName": "张三", "tag": "模型网关排障"}))
    result = await svc.build("为张三添加评价:模型网关排障", CTX, run_id="r2")
    assert result.card["action"]["type"] == ACTION_REVIEW
    review = result.card["action"]["nextReview"]
    assert review["personName"] == "张三" and review["tag"] == "模型网关排障"
    assert review["date"]


async def test_review_reject_self() -> None:
    svc = ActionDraftService(llm=StubLLM({"personName": "王丹", "tag": "自评"}))
    result = await svc.build("为王丹添加评价:自评", CTX, run_id="r3")
    assert result.card is None  # 他人画像不能评价本人(v4 §五)
    assert "personName" in result.missing


async def test_review_missing_tag_clarifies() -> None:
    svc = ActionDraftService(llm=StubLLM({"personName": "张三", "tag": ""}))
    result = await svc.build("为张三添加评价", CTX, run_id="r4")
    assert result.card is None and "tag" in result.missing


async def test_content_card() -> None:
    svc = ActionDraftService(llm=StubLLM({
        "title": "K8s 部署实践", "tags": ["K8s", "部署"],
        "summary": "总结", "body": "正文"}))
    result = await svc.build("发布一篇文章《K8s 部署实践》", CTX, run_id="r5")
    assert result.card["action"]["type"] == ACTION_CONTENT
    content = result.card["action"]["nextContent"]
    assert content["title"] == "K8s 部署实践" and content["tags"] == ["K8s", "部署"]
    # 发布卡文案不得表述为已公开发布(v4 §五)
    assert "待审核" in result.reply_text and "已发布" not in result.reply_text.replace("待审核", "")


async def test_llm_failure_degrades_without_card() -> None:
    class FailingLLM:
        async def structured_chat(self, messages, *, required_keys, **kwargs):
            raise RuntimeError("llm down")

    svc = ActionDraftService(llm=FailingLLM())
    result = await svc.build("修改我的联系方式为 1234", CTX, run_id="r6")
    assert result.degraded is True
    assert result.card is None  # 字段提取失败 → 澄清,不编造
