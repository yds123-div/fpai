# -*- coding: utf-8 -*-
"""
产品推荐智能体：按客户画像/需求 TopN 推荐；Data Access + ReAgent。

T021：向 AgentScope 注册为工具 product_recommend_query；Data Access 取候选产品，ReAgent 筛选并生成推荐理由。
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from data_access import get_data

try:
    from agentscope.tool import ToolResponse, Toolkit
    from agentscope.message import TextBlock
    from agentscope.agent import ReActAgent
    from agentscope.formatter import DashScopeChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.message import Msg
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    ToolResponse = None  # type: ignore[misc, assignment]
    Toolkit = None  # type: ignore[misc, assignment]
    TextBlock = None  # type: ignore[misc, assignment]
    ReActAgent = None  # type: ignore[misc, assignment]
    DashScopeChatFormatter = None  # type: ignore[misc, assignment]
    InMemoryMemory = None  # type: ignore[misc, assignment]
    Msg = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False

DEFAULT_PRODUCT_MODEL_CODE = "products"
DEFAULT_CANDIDATE_PAGE_SIZE = 30
DEFAULT_TOP_N = 5


def _product_summary_line(p: dict[str, Any], index: int) -> str:
    """单条产品摘要，供 ReAgent 阅读。"""
    name = p.get("name") or p.get("product_name") or p.get("id") or ""
    pid = p.get("id") or p.get("product_id") or ""
    parts = [f"[{index}] id={pid}, 名称={name}"]
    for key in ("summary", "description", "risk_level", "term", "fee_rate", "investment_direction"):
        v = p.get(key)
        if v and isinstance(v, str) and v.strip():
            parts.append(f"  {key}={v.strip()[:200]}")
        elif v is not None and not isinstance(v, str):
            parts.append(f"  {key}={v}")
    return "\n".join(parts)


from agents.model_config import create_chat_model_from_config


async def _recommend_via_reagent(
    customer_profile: str,
    candidates_text: str,
    top_n: int,
) -> str | None:
    """用 ReActAgent 根据客户画像与候选产品列表生成 TopN 推荐及理由。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return None
    model = create_chat_model_from_config()
    if model is None:
        return None
    sys_prompt = """你是金融产品推荐助手。根据客户需求/画像，从给定的候选产品中选出最匹配的 TopN 个产品，并为每个产品写一句推荐理由。
输出格式严格为（每行一条）：
1. 产品名称（id: xxx）推荐理由
2. ...
不要编造候选列表中不存在的产品；仅从候选列表中选择。"""
    user_content = f"""客户需求/画像：
{customer_profile}

候选产品（方括号内为序号，id 为产品 ID）：
{candidates_text}

请从中选出最匹配的 Top{top_n} 个产品，按上述格式输出推荐列表。"""
    agent = ReActAgent(
        name="ProductRecommendAgent",
        sys_prompt=sys_prompt,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=Toolkit(),
    )
    msg_res = await agent(Msg("user", user_content, "user"))
    if msg_res is None:
        return None
    text = msg_res.get_text_content() if hasattr(msg_res, "get_text_content") else None
    if not text and hasattr(msg_res, "get_content_blocks"):
        blocks = msg_res.get_content_blocks("text")
        if blocks:
            text = "\n".join(getattr(b, "text", b.get("text", "")) for b in blocks)
    return (text or "").strip() or None


def _parse_recommend_lines(raw: str, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    从 ReAgent 返回的文本中解析「产品名（id: xxx）理由」，与 products 匹配得到 id/name/reason。
    未匹配到 id 时按顺序与候选产品前 N 条对应。
    """
    results: list[dict[str, Any]] = []
    id_to_product: dict[str, dict[str, Any]] = {}
    for p in products:
        pid = str(p.get("id") or p.get("product_id") or "").strip()
        if pid:
            id_to_product[pid] = p
    lines = re.split(r"[\n\r]+", (raw or "").strip())
    used_ids: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line or not re.match(r"^\d+[\.\、)]", line):
            continue
        line = re.sub(r"^\d+[\.\、)]\s*", "", line).strip()
        id_match = re.search(r"[(（]?\s*id[=：:]\s*([^\s）)]+)[）)]?", line, re.IGNORECASE)
        pid = id_match.group(1).strip() if id_match else None
        if pid and pid in id_to_product and pid not in used_ids:
            p = id_to_product[pid]
        else:
            p = next((x for x in products if str(x.get("id") or x.get("product_id") or "") not in used_ids), None)
        if not p:
            continue
        used_ids.add(str(p.get("id") or p.get("product_id") or ""))
        reason = line
        if id_match:
            before = line[: id_match.start()].strip()
            after = line[id_match.end() :].strip()
            reason = (before + " " + after).strip()
            reason = re.sub(r"\s*[（(]\s*id[=：:][^）)]+[）)]?\s*", " ", reason).strip()
        if not reason:
            reason = "与需求匹配，可进一步查看详情。"
        results.append({
            "id": p.get("id") or p.get("product_id"),
            "name": p.get("name") or p.get("product_name"),
            "reason": reason,
        })
        if len(results) >= len(products):
            break
    return results


def query_product_recommend(
    customer_profile: str,
    top_n: int = DEFAULT_TOP_N,
    permission_context: dict[str, Any] | None = None,
    use_reagent: bool = True,
    model_code: str = DEFAULT_PRODUCT_MODEL_CODE,
) -> dict[str, Any]:
    """
    按客户画像/需求 TopN 推荐：Data Access 取候选产品 → ReAgent 筛选并生成推荐理由。

    Args:
        customer_profile: 客户需求/画像描述（期限、流动性、风险偏好、目标收益等）。
        top_n: 推荐条数。
        permission_context: 权限上下文。
        use_reagent: 是否用 ReAgent 生成推荐与理由。
        model_code: 产品列表领域模型编码。

    Returns:
        products: 推荐结果列表 [{id, name, reason}]
        summary: 简短摘要
        answer: 完整展示用文本
    """
    profile = (customer_profile or "").strip()
    if not profile:
        return {
            "products": [],
            "summary": "请提供客户需求或画像（如期限、风险偏好、收益目标等）。",
            "answer": "请提供客户需求或画像（如期限、风险偏好、收益目标等）。",
        }
    top_n = max(1, min(top_n, 20))
    try:
        records, total = get_data(
            model_code=model_code,
            request_params={
                "page": 1,
                "page_size": max(DEFAULT_CANDIDATE_PAGE_SIZE, top_n * 4),
            },
            permission_context=permission_context,
        )
    except Exception:
        records = []
        total = 0
    if not records:
        return {
            "products": [],
            "summary": "当前无可用产品，无法推荐。",
            "answer": "当前无可用产品，无法推荐。",
        }
    candidates_text = "\n\n".join(_product_summary_line(p, i + 1) for i, p in enumerate(records))
    summary = ""
    recommended: list[dict[str, Any]] = []
    if use_reagent:
        try:
            raw = asyncio.run(_recommend_via_reagent(profile, candidates_text, top_n))
            if raw:
                recommended = _parse_recommend_lines(raw, records)
                if not recommended:
                    recommended = [
                        {
                            "id": p.get("id") or p.get("product_id"),
                            "name": p.get("name") or p.get("product_name"),
                            "reason": "与需求匹配，请以产品说明书为准。",
                        }
                        for p in records[:top_n]
                    ]
                summary = f"根据您的需求已推荐 {len(recommended)} 款产品，请以产品说明书与销售文件为准。"
        except Exception:
            pass
    if not recommended:
        recommended = [
            {
                "id": p.get("id") or p.get("product_id"),
                "name": p.get("name") or p.get("product_name"),
                "reason": "可售产品，建议结合客户需求进一步筛选。",
            }
            for p in records[:top_n]
        ]
        summary = f"共 {total} 条可售产品，已取前 {len(recommended)} 条供参考；建议补充客户画像以获取更精准推荐。"
    lines = [f"{i+1}. {r.get('name') or r.get('id')}（id: {r.get('id')}）\n   推荐理由：{r.get('reason') or '—'}" for i, r in enumerate(recommended)]
    answer = "【推荐结果】\n\n" + "\n\n".join(lines) + "\n\n" + (summary or "以上推荐仅供参考，投资需谨慎。")
    return {
        "products": recommended,
        "summary": summary or "以上推荐仅供参考，投资需谨慎。",
        "answer": answer,
    }


async def product_recommend_query(customer_profile: str) -> Any:
    """
    产品推荐，包装为 ToolResponse。供 toolkit.register_tool_function(product_recommend_query) 注册。

    Args:
        customer_profile: 客户需求/画像描述（如期限、风险偏好、收益目标等）。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_product_recommend((customer_profile or "").strip())
    text = result.get("answer") or "无法生成推荐。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
