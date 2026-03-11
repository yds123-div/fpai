# -*- coding: utf-8 -*-
"""
意图识别与槽位抽取：意图分类（FAQ/产品解读/对比/推荐/RAG/报告/洞察等）、槽位抽取（产品 ID、类型、时间范围、客户画像等）。
T025：输出意图+槽位供 AgentScope 使用；见 architecture Intent & Slot Service。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pkg.logger import get_logger

logger = get_logger(__name__)

try:
    from model_gateway.llm import llm_chat, ModelNotConfiguredError
except ImportError:
    llm_chat = None  # type: ignore[assignment]
    ModelNotConfiguredError = Exception  # type: ignore[misc, assignment]


# 意图标签与 registry 能力 id 对齐，供 T026 注入上下文或缩小候选工具集
INTENT_FAQ = "faq"
INTENT_RAG = "rag"
INTENT_PRODUCT_LIST = "product_list"
INTENT_PRODUCT_INTERPRET = "product_interpret"
INTENT_PRODUCT_COMPARE = "product_compare"
INTENT_PRODUCT_RECOMMEND = "product_recommend"
INTENT_REPORT_GENERATE = "report_generate"
INTENT_INSIGHT = "insight"
INTENT_OTHER = "other"

VALID_INTENTS = frozenset({
    INTENT_FAQ,
    INTENT_RAG,
    INTENT_PRODUCT_LIST,
    INTENT_PRODUCT_INTERPRET,
    INTENT_PRODUCT_COMPARE,
    INTENT_PRODUCT_RECOMMEND,
    INTENT_REPORT_GENERATE,
    INTENT_INSIGHT,
    INTENT_OTHER,
})

# 槽位键：与 PRD/architecture 一致
SLOT_PRODUCT_IDS = "product_ids"
SLOT_PRODUCT_TYPE = "product_type"
SLOT_TIME_RANGE = "time_range"
SLOT_CUSTOMER_PROFILE = "customer_profile"
SLOT_KEYWORD = "keyword"
SLOT_CONTRAST_DIMENSIONS = "contrast_dimensions"


@dataclass
class IntentSlotResult:
    """意图与槽位抽取结果，供 AgentScope 或编排使用。"""
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""

    def to_context_prompt_fragment(self) -> str:
        """转为可注入 AgentScope 的上下文片段。"""
        parts = [f"当前识别意图：{self.intent}"]
        if self.slots:
            parts.append("已抽取槽位：")
            for k, v in self.slots.items():
                if v is not None and v != "" and v != []:
                    parts.append(f"  - {k}: {v}")
        return "\n".join(parts)


_SYS_PROMPT = """你是意图与槽位抽取助手。根据用户输入，输出一条 JSON，且仅输出该 JSON，不要其他文字。
JSON 结构：
{
  "intent": "意图标签",
  "slots": {
    "product_ids": ["id1", "id2"],
    "product_type": "产品类型或空字符串",
    "time_range": "时间范围如 本周/本月 或空",
    "customer_profile": "客户画像/需求描述或空",
    "keyword": "检索关键词或空",
    "contrast_dimensions": "对比维度或空"
  }
}
意图标签必须为以下之一：faq（常见问题/话术）、rag（研报/政策/知识库检索）、product_list（产品列表/筛选）、product_interpret（产品解读/要点/风险）、product_compare（多产品对比）、product_recommend（产品推荐/客户匹配）、report_generate（周报/月报/报告生成）、insight（猜你想问/洞察）、other（闲聊或无法识别）。
槽位只填从用户输入中能明确抽取到的内容，没有则填空字符串或空数组。product_ids 为产品 ID 列表。"""


def _parse_llm_json(raw: str) -> tuple[str, dict[str, Any]]:
    """从 LLM 返回文本中解析 intent 与 slots。"""
    intent = INTENT_OTHER
    slots: dict[str, Any] = {}
    raw = (raw or "").strip()
    # 尝试提取 JSON 块
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict):
                intent = (data.get("intent") or INTENT_OTHER).strip().lower()
                if intent not in VALID_INTENTS:
                    intent = INTENT_OTHER
                s = data.get("slots")
                if isinstance(s, dict):
                    slots = {
                        SLOT_PRODUCT_IDS: s.get(SLOT_PRODUCT_IDS) if isinstance(s.get(SLOT_PRODUCT_IDS), list) else [],
                        SLOT_PRODUCT_TYPE: str(s.get(SLOT_PRODUCT_TYPE) or "").strip(),
                        SLOT_TIME_RANGE: str(s.get(SLOT_TIME_RANGE) or "").strip(),
                        SLOT_CUSTOMER_PROFILE: str(s.get(SLOT_CUSTOMER_PROFILE) or "").strip(),
                        SLOT_KEYWORD: str(s.get(SLOT_KEYWORD) or "").strip(),
                        SLOT_CONTRAST_DIMENSIONS: str(s.get(SLOT_CONTRAST_DIMENSIONS) or "").strip(),
                    }
        except json.JSONDecodeError:
            logger.debug("意图槽位 JSON 解析失败: %s", raw[:200])
    return intent, slots


def detect_intent_and_slots(
    message: str,
    context: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> IntentSlotResult:
    """
    对用户消息做意图分类与槽位抽取，供 AgentScope 或编排使用。

    Args:
        message: 用户输入文本。
        context: 可选上下文（如 session 内 productIds、customerProfile），用于补充槽位或提示。
        use_llm: 是否调用 LLM；否则返回 intent=other, slots={}。

    Returns:
        IntentSlotResult: intent + slots + raw_response。
    """
    message = (message or "").strip()
    if not message:
        return IntentSlotResult(intent=INTENT_OTHER, slots={}, raw_response="")

    if not use_llm or llm_chat is None:
        return IntentSlotResult(intent=INTENT_OTHER, slots={}, raw_response="")

    user_parts = [f"用户输入：{message}"]
    if context:
        if context.get("productIds"):
            user_parts.append(f"会话内已选产品 ID：{context.get('productIds')}")
        if context.get("customerProfile"):
            user_parts.append(f"会话内客户画像：{context.get('customerProfile')}")
    user_content = "\n".join(user_parts) + "\n\n请输出上述 JSON。"

    try:
        raw = llm_chat([
            {"role": "system", "content": _SYS_PROMPT},
            {"role": "user", "content": user_content},
        ])
    except ModelNotConfiguredError:
        return IntentSlotResult(intent=INTENT_OTHER, slots={}, raw_response="")
    except Exception as e:
        logger.warning("意图槽位 LLM 调用失败: %s", e)
        return IntentSlotResult(intent=INTENT_OTHER, slots={}, raw_response="")

    intent, slots = _parse_llm_json(raw or "")
    # 若上下文带了 productIds/customerProfile 而 slots 里为空，可回填
    if context:
        if not slots.get(SLOT_PRODUCT_IDS) and context.get("productIds"):
            slots[SLOT_PRODUCT_IDS] = list(context["productIds"]) if isinstance(context["productIds"], (list, tuple)) else [context["productIds"]]
        if not slots.get(SLOT_CUSTOMER_PROFILE) and context.get("customerProfile"):
            slots[SLOT_CUSTOMER_PROFILE] = str(context["customerProfile"] or "").strip()
    return IntentSlotResult(intent=intent, slots=slots, raw_response=(raw or "").strip())
