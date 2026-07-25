# -*- coding: utf-8 -*-
"""T6 (#24)：structured_outputs collector（栅栏 #5，原生重表达）。

旧链路（``ProductQueryAgent`` / ``ProductCompareAgent``）在路由后由各 agent 分别调
``build_single_output`` / ``build_compare_output``。新原生链路无显式路由--agent 自路由
（LLM 自选工具），故 collector 在 ``on_acting`` 中间件里攥取数 payload，回复后按取数
形状决定 single / compare：

- ``query_fund_detail`` 返回 2+ 只基金 -> ``compare``（对比+优选）
- ``query_fund_detail`` 返回 1 只、或 ``query_fund_rank``（榜单）、或仅 resolve/kb -> ``single``

builder（``build_single_output`` / ``build_compare_output``）原样存活，collector 只负责
「攒 payload + 选模式 + 喂 builder」，**不**走 ``ChatModelBase.generate_structured_output``
（spec #18：原生结构化输出通道留给将来，本链路用既有 builder 保形）。

纯函数（``select_output_mode`` / ``pick_primary_payload`` / ``build_structured_output``）
独立可测，不依赖 AgentScope；``StructuredOutputsCollector`` 是 ``on_acting`` 中间件壳，
把 tool_call 结果喂给纯函数。

测试 seam：脚本化假 ``ChatModelBase`` + 桩取数工具（不打真实 LLM/akshare）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from agentscope.message import ToolResultState
from agentscope.middleware import MiddlewareBase
from agentscope.tool import ToolResponse

from pkg.fund_formatter import build_compare_output, build_single_output, extract_funds

OutputMode = Literal["single", "compare"]


@dataclass
class CapturedToolResult:
    """一次工具调用的捕获结果（collector 在 on_acting 攒取）。"""

    tool_name: str
    payload: Any  # 工具返回值（已解析的 dict / str / 其它）


def select_output_mode(captured: list[CapturedToolResult]) -> OutputMode:
    """按取数形状选输出模式：单只/榜单 -> ``single``，多只对比 -> ``compare``。

    规则（与 sys_prompt 三模式对齐：榜单短版/单只标准 -> single，多只对比 -> compare）：
    - 任一 ``query_fund_detail`` 调用返回 2+ 只基金 -> ``compare``（多只对比意图）。
    - ``query_fund_rank``（榜单，即使返回多只）-> ``single``（榜单不是对比）。
    - 单只 detail / 仅 resolve/kb / 空 -> ``single``。

    「任一 detail 2+ 即 compare」：模型可能在一次 reply 内先查单只再扩到对比，
    取数形状以最宽者为准（对比优先），与旧 ``ProductCompareAgent`` 语义一致。
    """
    for cap in captured:
        if cap.tool_name == "query_fund_detail" and len(extract_funds(cap.payload)) >= 2:
            return "compare"
    return "single"


def pick_primary_payload(captured: list[CapturedToolResult]) -> Any:
    """选出喂给 builder 的主取数 payload。

    优先级：最后一次 ``query_fund_detail``（详情，含完整基金模块）> 最后一次
    ``query_fund_rank``（榜单）> None。resolve/kb 不是基金详情数据，不作为 builder 输入。
    """
    detail = [c for c in captured if c.tool_name == "query_fund_detail"]
    if detail:
        return detail[-1].payload
    rank = [c for c in captured if c.tool_name == "query_fund_rank"]
    if rank:
        return rank[-1].payload
    return None


def build_structured_output(
    captured: list[CapturedToolResult],
    llm_text: str,
) -> dict[str, Any] | None:
    """按取数形状跑 builder，产出 ``FundAnalysisOutput``。

    无基金详情/榜单 payload 时返回 ``None``（如纯知识库问答，不产出 fund_analysis 结构）。
    """
    payload = pick_primary_payload(captured)
    if payload is None:
        return None
    if select_output_mode(captured) == "compare":
        return build_compare_output(payload, llm_text)
    return build_single_output(payload, llm_text)


# ---------------------------------------------------------------------------
# ToolResponse payload 提取 + on_acting 中间件
# ---------------------------------------------------------------------------
def _parse_tool_response_content(content: Any) -> Any:
    """从 ``ToolResponse.content`` 解析出可用的 payload。

    与 ``fund_formatter._extract_payload``（从 dict 包装取 payload dict）语义不同：
    本函数把 ``ToolResponse.content``（``list[TextBlock]``，``FunctionTool`` 经
    ``_convert_func_result_to_chunk`` 把 str/dict 包成 ``TextBlock``）拼成文本后
    ``json.loads``；防御性兼容 str。非 JSON 则原样返回文本。
    """
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(
            getattr(b, "text", "") or "" for b in content if hasattr(b, "text")
        )
    else:
        return content
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text


class StructuredOutputsCollector(MiddlewareBase):
    """``on_acting`` 中间件：攥取数工具的 payload，回复后跑 builder（栅栏 #5）。

    只攥 ``SUCCESS`` 的工具结果（``ERROR``/``DENIED`` 的回灌归 M4，不喂 builder）。
    用法：``agent, collector = build_fund_agent(...)``；``await agent.reply(...)``
    拿最终文本后调 ``collector.build_structured_output(final_text)``。

    验证：``on_acting`` 包 ``toolkit.call_tool``（见 ``_agent._acting``），每次
    工具执行后拿到末尾的 ``ToolResponse``；不干预执行、只观察攥数。
    """

    def __init__(self) -> None:
        self._captured: list[CapturedToolResult] = []

    async def on_acting(  # type: ignore[override]
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Any,
    ) -> Any:
        tool_call = input_kwargs["tool_call"]
        name = getattr(tool_call, "name", "")
        async for item in next_handler():
            yield item
            if (
                isinstance(item, ToolResponse)
                and item.state == ToolResultState.SUCCESS
            ):
                payload = _parse_tool_response_content(item.content)
                self._captured.append(CapturedToolResult(name, payload))

    @property
    def captured(self) -> list[CapturedToolResult]:
        """已攥取的工具结果快照（测试 / 诊断用）。"""
        return list(self._captured)

    def build_structured_output(self, llm_text: str) -> dict[str, Any] | None:
        """回复后按取数形状跑 builder（单只/榜单 -> single，多只 -> compare）。"""
        return build_structured_output(self._captured, llm_text)
