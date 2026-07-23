# -*- coding: utf-8 -*-
"""E3 原型入口：跑通一个基金查询，验证栅栏 #6 流式/进度/callback 保形。

用法（在 backend/ 下，用已装 agentscope 的 venv）：
    # 真实模型（需配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）
    python -m prototype.e3_streaming.run_prototype
    # 离线 stub（不连模型，验证事件->回调映射）
    python -m prototype.e3_streaming.run_prototype --stub
    python -m prototype.e3_streaming.run_prototype --show-thinking

产出：把 progress 阶段 + token 流打印到 stdout，对照现有契约判断是否保形。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, AsyncGenerator


def _load_dotenv() -> None:
    """从 backend/.env 读取 LLM_* 到 os.environ（不依赖 python-dotenv）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.normpath(os.path.join(here, "..", "..", ".env"))
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k.startswith(("LLM_",)):
                os.environ.setdefault(k, v)


from agentscope.agent import Agent, ModelConfig, ReActConfig
from agentscope.message import Msg, TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason

from .fund_tools import build_fund_toolkit
from .gateway_model import build_gateway_model
from .shape_adapter import ShapeAdapter

SYSTEM_PROMPT = (
    "你是一名基金分析助手。回答用户关于基金的问题时，必须先调用 query_fund 或 "
    "lookup_fund_by_name 工具获取数据，再据实回答。禁止捏造数据；查不到就如实告知。"
    "回答控制在 200 字以内，用自然语句，不要用 markdown 标记。"
)

DEFAULT_QUESTION = "帮我查一下易方达蓝筹精选基金的情况，代码 005827"


# ---------------------------------------------------------------------- stub
class _StubChatModel(ChatModelBase):
    """离线 stub：第一次调用发 tool_call(query_fund)，第二次流式输出文本。

    仅用于验证 reply_stream 事件 -> progress/stream_callback 映射；
    不连真实模型。input_schema 不重要（agent 不向 stub 询问工具 schema 之外的东西）。
    """

    def __init__(self) -> None:
        # ChatModelBase.__init__ 需要 credential/parameters；stub 用占位
        from agentscope.credential import OpenAICredential

        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=type("P", (), {})(),  # 占位 parameters 对象
            stream=True,
            max_retries=0,
        )
        self._call_count = 0

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        self._call_count += 1
        if self._call_count == 1:
            # 发起工具调用（非流式：返回单个 ChatResponse）
            return ChatResponse(
                content=[
                    ToolCallBlock(
                        id="call_stub_1",
                        name="query_fund",
                        input=json.dumps({"fund_code": "005827"}),
                    )
                ],
                is_last=True,
                finished_reason=FinishedReason.COMPLETED,
            )
        # 第二次：流式输出最终回答（返回 async generator，验证 token 级流式）
        tokens = [
            "易方达蓝筹精选混合（005827）",
            "是一只混合型基金，",
            "基金经理张坤，",
            "规模约412.6亿元。",
            "近一年收益-8.3%，近三年-12.5%。",
            "请注意基金有风险，投资需谨慎。",
        ]

        async def _stream() -> AsyncGenerator[ChatResponse, None]:
            for i, t in enumerate(tokens):
                last = i == len(tokens) - 1
                yield ChatResponse(
                    content=[TextBlock(text=t)],
                    is_last=last,
                    finished_reason=FinishedReason.COMPLETED if last else None,
                )

        return _stream()


def _build_agent(*, stub: bool, show_thinking: bool) -> Agent:
    if stub:
        model: ChatModelBase = _StubChatModel()
    else:
        model = build_gateway_model(stream=True)
    return Agent(
        name="fund_agent",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        toolkit=build_fund_toolkit(),
        model_config=ModelConfig(max_retries=1),
        react_config=ReActConfig(max_iters=6),
    )


async def _main(*, stub: bool, show_thinking: bool, question: str) -> int:
    agent = _build_agent(stub=stub, show_thinking=show_thinking)

    progress_events: list[str] = []
    token_chunks: list[str] = []

    def progress_cb(stage: str, **kwargs: Any) -> None:
        progress_events.append(stage)
        extra = ""
        if "tool" in kwargs:
            extra = f" ({kwargs['tool']})"
        print(f"  [progress] {stage}{extra}")

    def stream_cb(token: str) -> None:
        token_chunks.append(token)
        print(f"  [token] {token!r}", end="", flush=True)

    print(f"=== E3 原型：{'stub' if stub else 'real'} 模式 | show_thinking={show_thinking} ===")
    print(f"question: {question}")
    print("--- reply_stream 事件 -> progress/token 回调 ---")

    adapter = ShapeAdapter(
        progress_callback=progress_cb,
        stream_callback=stream_cb,
        show_thinking=show_thinking,
    )
    print()  # token 行起首换行
    async for kind, detail in adapter.drive(agent, UserMsg(name="user", content=[TextBlock(text=question)])):
        # drive 内部已透传回调；这里不再重复打印
        pass
    print()  # token 行收尾换行

    print("--- 保形校验 ---")
    final_text = getattr(adapter, "final_text", "")
    print(f"final_text ({len(final_text)} chars): {final_text[:120]}...")
    print(f"progress 阶段序列: {progress_events}")
    print(f"token 分片数: {len(token_chunks)}，拼接长度: {len(''.join(token_chunks))}")

    # 形状断言：关键阶段是否齐全
    expected_core = {"accepted", "thinking", "llm_generating", "model_first_token", "done"}
    have = set(progress_events)
    print(f"核心阶段命中: {sorted(expected_core & have)}")
    print(f"核心阶段缺失: {sorted(expected_core - have) or '无'}")
    print(f"skill_fetching 命中: {'skill_fetching' in progress_events}")
    print(f"token 流式生效: {len(token_chunks) > 1}")
    return 0 if final_text else 1


def main() -> None:
    args = sys.argv[1:]
    stub = "--stub" in args
    show_thinking = "--show-thinking" in args
    question = DEFAULT_QUESTION
    for i, a in enumerate(args):
        if a == "--question" and i + 1 < len(args):
            question = args[i + 1]
    if not stub:
        _load_dotenv()
    rc = asyncio.run(_main(stub=stub, show_thinking=show_thinking, question=question))
    sys.exit(rc)


if __name__ == "__main__":
    main()
