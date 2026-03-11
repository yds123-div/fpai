"""
产品要素/条款抽取：从文档/条款文本中抽取期限、费率、风险、赎回规则等。

文档解析 + LLM/规则（technical_design）；供解读/对比/报告或 ingestion 调用。
"""
from __future__ import annotations

import json
import re
from typing import Any

from pkg.logger import get_logger

from agents.product_element.types import ProductElements

logger = get_logger(__name__)

try:
    from model_gateway.llm import llm_chat, ModelNotConfiguredError
except ImportError:
    llm_chat = None  # type: ignore[assignment]
    ModelNotConfiguredError = Exception  # type: ignore[misc, assignment]

# 规则：常见模式，用于 LLM 不可用时的兜底
_PATTERNS = [
    (r"期限[：:]\s*([^\n，,。]+)", "term"),
    (r"投资期限[：:]\s*([^\n，,。]+)", "term"),
    (r"费率[：:]\s*([^\n，,。]+)", "fee_rate"),
    (r"管理费[率]?[：:]\s*([^\n，,。]+)", "fee_rate"),
    (r"风险等级[：:]\s*([^\n，,。]+)", "risk_level"),
    (r"风险[等级]?[：:]\s*([^\n，,。]+)", "risk_level"),
    (r"赎回[规则条款]?[：:]\s*([^\n，,。]+)", "redemption_rules"),
    (r"投向[：:]\s*([^\n，,。]+)", "investment_direction"),
    (r"投资范围[：:]\s*([^\n，,。]+)", "investment_direction"),
    (r"业绩基准[：:]\s*([^\n，,。]+)", "performance_benchmark"),
    (r"收益[规则说明]?[：:]\s*([^\n，,。]+)", "income_rules"),
]


def _rule_extract(text: str) -> dict[str, str]:
    """规则抽取：用正则匹配常见「标签：值」模式，填充到 dict。"""
    if not text or not text.strip():
        return {}
    out: dict[str, str] = {}
    for pattern, key in _PATTERNS:
        if key in out:
            continue
        m = re.search(pattern, text)
        if m:
            out[key] = m.group(1).strip()
    return out


def _llm_extract(text: str) -> dict[str, Any] | None:
    """调用 LLM 抽取结构化要素，要求返回 JSON。"""
    if not llm_chat:
        return None
    sys_prompt = """你是金融产品文档解析助手。从用户提供的产品说明书/条款片段中，抽取以下要素（若文中无则填空字符串）。
仅输出一行 JSON，不要其他文字。键名必须为英文：term（期限）、fee_rate（费率）、risk_level（风险等级）、redemption_rules（赎回规则）、investment_direction（投向）、performance_benchmark（业绩基准）、income_rules（收益规则）、product_name（产品名称）。"""
    user_prompt = f"请从以下文本中抽取产品要素，输出上述 JSON：\n\n{text[:6000]}"
    try:
        raw = llm_chat([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}])
    except ModelNotConfiguredError:
        return None
    except Exception as e:
        logger.warning("产品要素 LLM 抽取异常: %s", e)
        return None
    raw = (raw or "").strip()
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        logger.debug("产品要素 LLM 返回非 JSON: %s", raw[:200])
        return None


def extract_elements(text: str, use_llm: bool = True) -> ProductElements:
    """
    从文档/条款文本中抽取产品要素（期限、费率、风险、赎回规则等）。

    - 若 use_llm 且 LLM 可用，优先用 LLM 抽取并解析 JSON，再与规则结果合并（LLM 覆盖规则）。
    - 否则仅用规则抽取；无匹配时返回空要素。
    """
    if not text or not text.strip():
        return ProductElements()
    rule_result = _rule_extract(text)
    if use_llm and llm_chat is not None:
        llm_result = _llm_extract(text)
        if llm_result:
            for k, v in llm_result.items():
                if isinstance(v, str) and v.strip():
                    rule_result[k] = v.strip()
                elif isinstance(v, (int, float)) and str(v).strip():
                    rule_result[k] = str(v)
    return ProductElements.from_dict(rule_result)
