# -*- coding: utf-8 -*-
"""T6 (#24)：原生 ``Agent``（ReActAgent）装配--新链路核心组装。

组合三块前置产出（栅栏交接）：
- **T2** sys_prompt（``agents.prompts.loader.load_prompt("sys_prompt")`` 读 git 文件库，
  含三模式输出契约：榜单短版 / 单只标准 / 多只对比+优选）。
- **T4** ``GatewayChatModel``（``build_gateway_model(stream=True)``，模型 choke-point；
  熔断/超时/fallback 耗尽抛异常，供 T7 ``on_model_call`` 捕）。
- **T5** ``Toolkit``（4 只读取数 ``FunctionTool``，"basic" 组始终激活=白名单单一权威）
  + ``PermissionContext``（4 条 ``ALLOW`` 规则，M3 危险集暂空休眠）。

安全意图 M1-M5 全部原生落位（``_agent._execute_tool_call``，R1 #3 已验证 2.0.4 源码）：
- M1 参数校验：``jsonschema.validate(input_schema)`` -> ``AgentOrientedException`` -> ERROR 回灌。
- M2 工具白名单：``check_tool_available`` + "basic" 组始终激活（Toolkit 注册表即单一权威）。
- M3 危险操作前验证（HITL）：``check_permission`` ASK -> ``RequireUserConfirmEvent`` 暂停；
  4 只读 ALLOW 放行、危险集暂空。
- M4 无效 tool_call 重试：ERROR 回灌自愈 + ``ReActConfig(max_iters=8)`` + ``ExceedMaxItersEvent`` 降级。
- M5 部分工具失败反馈：批调用每工具独立 ``ToolResponse``（合法保留、非法明确反馈）。

路由意图 = agent 自路由（LLM 自选工具）；multi-task / final_instruction 被 ReAct 单轮多工具
调用吸收，模板拼接退役（旧 ``ProductQueryAgent``/``ProductCompareAgent``/coordinator.md 在 T10 切换删除）。

structured_outputs collector（``StructuredOutputsCollector``）作为 ``on_acting`` 中间件挂入，
回复后跑 ``build_single_output`` / ``build_compare_output``（见 ``structured_collector``）。

测试 seam：``build_fund_agent`` 全参数可注入（假 ``ChatModelBase`` + 桩 toolkit/state），
``run_chat_turn_async`` 主 seam验收在 T10。
"""
from __future__ import annotations

from typing import Any

from agentscope.agent import Agent, ModelConfig, ReActConfig
from agentscope.middleware import MiddlewareBase
from agentscope.model import ChatModelBase
from agentscope.state import AgentState
from agentscope.tool import Toolkit

from agents.native_agent.structured_collector import StructuredOutputsCollector
from agents.prompts.loader import load_prompt
from agents.tools.fund_tools import (
    build_fund_permission_context,
    build_fund_toolkit,
)
from model_gateway.gateway_model import build_gateway_model

#: T2 prompt 文件名（``agents/prompts/sys_prompt.md``，无扩展名）
SYS_PROMPT_NAME = "sys_prompt"

#: ReAct 循环上限（spec #18 / SI-7：重试有上限，默认 8）。
DEFAULT_MAX_ITERS = 8

#: 模型级重试（G1：inner max_retries=0，重试归 ModelConfig；此处给 1 次模型 API 瞬断重试）
DEFAULT_MODEL_MAX_RETRIES = 1

AGENT_NAME = "fund_agent"


def build_fund_agent(
    *,
    model: ChatModelBase | None = None,
    toolkit: Toolkit | None = None,
    state: AgentState | None = None,
    middlewares: list[MiddlewareBase] | None = None,
    max_iters: int = DEFAULT_MAX_ITERS,
    enable_thinking: bool = False,
) -> tuple[Agent, StructuredOutputsCollector]:
    """装配原生 fund ``Agent``（T6 核心组装）。

    组合 T2 sys_prompt + T4 GatewayChatModel(stream=True) + T5 Toolkit/permission +
    ``AgentState(permission_context)`` + ``ReActConfig(max_iters=8)`` + collector 中间件。

    Args:
        model: 模型（默认 T4 ``build_gateway_model(stream=True)``；测试注入假 ChatModelBase）。
        toolkit: 工具集（默认 T5 ``build_fund_toolkit``；测试注入桩工具集）。
        state: agent 状态（默认 ``AgentState(permission_context=build_fund_permission_context())``；
            测试可注入带/不带 permission_context 的 state）。
        middlewares: 额外中间件（T7 审计/on_model_call 等后续挂入）。collector 自动追加。
        max_iters: ReAct 循环上限（默认 8，SI-7）。
        enable_thinking: 透传给 GatewayChatModel 的推理开关。

    Returns:
        ``(agent, collector)``：调 ``await agent.reply(...)`` 拿最终文本后，用
        ``collector.build_structured_output(final_text)`` 产出 ``FundAnalysisOutput``。
    """
    all_mw: list[MiddlewareBase] = list(middlewares or [])
    existing = next(
        (m for m in all_mw if isinstance(m, StructuredOutputsCollector)),
        None,
    )
    if existing is None:
        collector = StructuredOutputsCollector()
        all_mw.append(collector)
    else:
        collector = existing

    agent = Agent(
        name=AGENT_NAME,
        system_prompt=load_prompt(SYS_PROMPT_NAME),
        model=model
        or build_gateway_model(
            stream=True,
            enable_thinking=enable_thinking,
        ),
        toolkit=toolkit or build_fund_toolkit(),
        state=state
        or AgentState(permission_context=build_fund_permission_context()),
        model_config=ModelConfig(max_retries=DEFAULT_MODEL_MAX_RETRIES),
        react_config=ReActConfig(max_iters=max_iters),
        middlewares=all_mw,
    )
    return agent, collector
