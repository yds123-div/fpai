# -*- coding: utf-8 -*-
"""T9 (#27)：启发式兜底共存（栅栏 #3，G5/#8 锁定）。

LLM 不可用 / ReAct 循环耗尽时，agent 退出后走一条**独立降级路径**：启发式分类
-> 直调取数工具（不调 LLM）-> 模拟流式 -> 既有 builder。与原生 agent **共存**
（路由由 agent 自路由承担，启发式分类降级为 "LLM-down 退路"，不再当路由种子）。

G5/#8 四项锁定（源码验证 ``_agent.py`` / ``shape_adapter.py``）：

1. **结构**：A（``model_unavailable``：模型 API 失败，``_call_model`` 无 try/except
   直接 raise，经 ``reply_stream`` -> ``ShapeAdapter.drive()`` 传播，orchestrator catch）
   与 B（``max_iters_exceeded``：``ExceedMaxItersEvent`` 是 yield 不抛，``drive()`` 返回后
   orchestrator 见标记）**共用一条 agent 退出后的独立降级路径**，入口按失败原因标记，
   复用同一套启发式分类 + 工具直调逻辑。不设宽泛 catch-all。
2. **流式/进度衔接（栅栏 #6 保形）**：**不改 ShapeAdapter**。兜底先发
   ``progress("degraded_fallback")`` + 清晰分隔提示，再输出降级结果；模拟流式切块走
   现有 ``stream_callback`` 通道，复用保形通路。B 续流接在已流文本后（``prior_text``），
   A 干净从零开始。
3. **structured_outputs 保留（栅栏 #5 延伸）**：兜底把 (直调工具 data, 兜底文本) 喂同一套
   ``build_single_output`` / ``build_compare_output``，图表/表格在降级下存活（数据驱动），
   分析叙述段退化为降级提示文本。other 类（kb）无 builder，纯文本。
4. **取数序列 + 栅栏 #1 确定性（不放宽）**：``heuristic_classify`` -> 直调取数工具映射：
   ``product_query`` -> 查榜单 / ``product_interpret``（单只）/ ``product_compare``（多只）
   -> 名称转代码 -> 查详情 / ``other`` -> kb。栅栏 #1 在降级下**不放宽**：臆测代码经
   ``resolve_fund_code`` 可信集校验被拒（``raise AgentOrientedException``），查不到代码即
   abort（发"未查询到基金代码"提示，不臆造）。确定性是栅栏硬契约，LLM 挂不挂都得守。

自写层（薄）：``HeuristicFallback``（降级路径主体）+ ``drive_with_fallback``（orchestrator
级：catch A 异常 / 检测 B ``exceed_max_iters`` 标记 -> 标记原因 -> 调降级路径）。
``heuristic_classify`` / ``IntentCategory`` 自旧 ``fund_agent_framework`` 改造搬迁至此
（栅栏 #3 是存活栅栏，旧框架 T10 删除后仍须存活；fund_agent_framework 现从此处 import，
保持单一权威源、零行为变更）。

复用：``heuristic_classify``、4 取数工具（``agents.tools.fund_tools``）、
``build_single_output``/``build_compare_output``（经 ``structured_collector.build_structured_output``）、
``stream_callback``/``progress_callback`` 通路、``ShapeAdapter``（不改）。

主 seam ``run_chat_turn_async`` 接线在 T10；本工单提供降级路径供其调用
（同 T7 contextvars helper / T8 ShapeAdapter 模式）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Literal

from agentscope.exception import AgentOrientedException
from agentscope.message import Msg

from agents.native_agent.shape_adapter import ShapeAdapter
from agents.native_agent.structured_collector import (
    CapturedToolResult,
    build_structured_output,
)

#: 兜底触发的失败原因（G5 决策 1：A/B 共用一条路径，入口按原因标记）。
FallbackReason = Literal["model_unavailable", "max_iters_exceeded"]

#: 6 位基金代码正则（与 ``fund_code_registry`` / 旧 ``_extract_codes_from_text`` 一致）。
_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")

#: 降级分隔提示（G5 决策 2：清晰分隔，注明数据未经 LLM 总结）。
_DEGRADED_NOTICE = "（以下为降级检索结果，数据未经 LLM 总结。）"

#: 栅栏 #1 abort 时的用户提示（与旧 planner abort 文案对齐，不臆造代码）。
_ABORT_NO_CODE_MSG = (
    "未查询到基金代码，请补充准确的基金名称或直接提供 6 位基金代码。"
)


# ---------------------------------------------------------------------------
# 启发式分类（自 ``fund_agent_framework._heuristic_classify`` 改造搬迁）
# ---------------------------------------------------------------------------
IntentCategory = Literal[
    "product_query", "product_interpret", "product_compare", "other"
]


def heuristic_classify(text: str) -> IntentCategory:
    """轻量启发式分类：保证在 LLM 不可用时也能工作。

    原 ``fund_agent_framework._heuristic_classify`` 原样搬迁（栅栏 #3 存活栅栏，
    旧框架 T10 删除后此函数仍须存活）。行为零变更：四分类
    product_query / product_interpret / product_compare / other。
    """
    t = (text or "").strip()
    if not t:
        return "other"
    codes = _CODE_RE.findall(t)
    uniq_codes = list(dict.fromkeys(codes))

    # 产品对比：显式"对比/比较"或出现多只基金代码
    if any(k in t for k in ("对比", "比较", "哪个好", "差异", "PK", "pk")) or len(
        uniq_codes
    ) >= 2:
        return "product_compare"

    # 产品查询：榜单/筛选/推荐/"哪些"类问题
    query_triggers = (
        "有哪些", "哪些", "推荐", "排行", "排名", "榜", "top", "TOP", "筛选",
        "找", "选", "收益率高", "涨幅", "近期", "最近", "近一周", "近1周",
        "近一月", "近1月", "近三月", "近3月", "近半年", "近6月", "近一年",
        "近1年", "今年来", "成立来", "稳健", "低风险",
    )
    if any(k in t for k in query_triggers):
        if len(uniq_codes) == 0:
            return "product_query"

    # 产品解析：单只基金/产品"怎么样/分析/解读/适不适合/风险点"
    interpret_triggers = (
        "解析", "解读", "分析", "怎么样", "怎么看", "要点", "风险", "适合",
        "条款", "能买吗", "值不值得",
    )
    if any(k in t for k in interpret_triggers) or (
        len(uniq_codes) == 1
        and any(k in t for k in ("风险", "收益", "回撤", "波动", "稳健"))
    ):
        return "product_interpret"

    # 兜底：包含"基金/理财/产品"关键词但未命中时，优先认为是产品查询
    if any(k in t for k in ("基金", "理财", "产品", "收益率", "净值")):
        return "product_query"
    return "other"


# ---------------------------------------------------------------------------
# 降级结果
# ---------------------------------------------------------------------------
@dataclass
class FallbackResult:
    """启发式兜底降级路径的产出（供 T10 orchestrator 消费）。

    - ``degraded_fallback`` 恒为 True（兜底已触发）；``reason`` 标 A/B。
    - ``aborted``：栅栏 #1 拒绝（臆测代码 / 查不到代码）-> 中止，不臆造；
      此时 ``structured_output`` 为 None（不放宽）。
    - ``structured_output``：降级下仍按 single/compare 形状产出（栅栏 #5 不放宽）；
      kb / abort 时为 None。
    - ``final_text``：完整回复文本（含 ``prior_text`` 续流 + 分隔提示 + 降级内容）。
    """

    degraded_fallback: bool = True
    reason: FallbackReason | None = None
    category: IntentCategory = "other"
    final_text: str = ""
    structured_output: dict[str, Any] | None = None
    aborted: bool = False
    abort_message: str = ""
    captured_tool_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 取数工具类型（默认指向 T5 的 4 个只读 FunctionTool 的 impl，可注入桩）
# ---------------------------------------------------------------------------
#: ``async (question: str) -> str``（返回 JSON 字符串，与 FunctionTool impl 一致）。
FetchTool = Callable[..., Any]


def _parse_tool_result(raw: Any) -> Any:
    """把直调工具的返回（JSON 字符串 / 已是 dict）解析为 payload。

    与 ``structured_collector._parse_tool_response_content`` 同语义：合法 JSON -> dict；
    非 JSON -> 原样文本。直调工具不经 ``ToolResponse`` 包装，故直接 ``json.loads``。
    """
    if isinstance(raw, (dict, list)):
        return raw
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except (TypeError, ValueError, json.JSONDecodeError):
            return s
    return raw


def _extract_codes(text: str) -> list[str]:
    """从文本提取去重保序的 6 位基金代码。"""
    return list(dict.fromkeys(_CODE_RE.findall(text or "")))


def _codes_from_resolve(payload: Any) -> list[str]:
    """从 ``resolve_fund_code`` 的返回 payload 提取解析出的代码。"""
    if not isinstance(payload, dict):
        return []
    # code_provided 分支 -> codes[].code；name_to_code 分支 -> matches[].code
    for key in ("codes", "matches"):
        items = payload.get(key)
        if isinstance(items, list):
            out: list[str] = []
            for it in items:
                if isinstance(it, dict):
                    c = str(it.get("code") or "").strip()
                    if c:
                        out.append(c)
                elif isinstance(it, str) and it.strip():
                    out.append(it.strip())
            if out:
                return out
    return []


def _summarize_payload(category: IntentCategory, payload: Any) -> str:
    """对直调取数 payload 做基本清洗与格式化（G5 决策 2：raw data 经清洗）。

    不做 LLM 分析；只提取代码/名称/片段数等确定性摘要，供降级叙述。
    """
    p = payload
    if isinstance(p, dict) and "payload" in p and isinstance(p["payload"], dict):
        p = p["payload"]
    if not isinstance(p, dict):
        return str(payload)[:500]
    if category == "other":
        chunks = p.get("chunks")
        count = p.get("count")
        if isinstance(chunks, list):
            lines = []
            for c in chunks[:5]:
                if isinstance(c, dict):
                    src = str(c.get("source") or "").strip()
                    txt = str(c.get("chunk_text") or "").strip()[:120]
                    lines.append(f"- [{src}] {txt}" if src else f"- {txt}")
            head = f"命中 {count if isinstance(count, int) else len(chunks)} 条相关片段："
            return head + ("\n" + "\n".join(lines) if lines else "")
        return str(payload)[:500]
    # rank / detail：提取代码与名称
    funds = p.get("funds")
    if isinstance(funds, list) and funds:
        items = []
        for f in funds[:10]:
            if isinstance(f, dict):
                sym = str(f.get("symbol") or f.get("code") or "").strip()
                name = str(f.get("name") or "").strip()
                items.append(f"{sym}{(' ' + name) if name else ''}".strip())
        if items:
            kind = "榜单基金" if category == "product_query" else "基金详情"
            return f"{kind}（共 {len(funds)} 只）：\n" + "\n".join(items)
    return str(payload)[:500]


# ---------------------------------------------------------------------------
# HeuristicFallback：agent 退出后的独立降级路径
# ---------------------------------------------------------------------------
class HeuristicFallback:
    """栅栏 #3 启发式兜底降级路径（G5/#8）。

    agent 退出后（A 模型异常 / B max_iters 耗尽）由 orchestrator 调 ``run``：
    启发式分类 -> 直调取数工具（不调 LLM）-> 模拟流式（复用 ``stream_callback`` 通路）
    -> 既有 builder（structured_outputs 不放宽）。栅栏 #1 在降级下不放宽
    （臆测代码经 ``resolve_fund_code`` 校验被拒 -> abort）。

    用法（orchestrator 侧，T10 接线）::

        fallback = HeuristicFallback(
            progress_callback=progress_cb,
            stream_callback=stream_cb,
            show_thinking=show_thinking,
        )
        result = await fallback.run("model_unavailable", message, prior_text="")
        # result.structured_output / result.final_text / result.degraded_fallback

    全参数可注入（假工具 + 桩 classify/builder），供组件级 seam 测试（不打 akshare/Milvus）。
    """

    def __init__(
        self,
        *,
        progress_callback: Callable[..., Any] | None = None,
        stream_callback: Callable[[str], Any] | None = None,
        show_thinking: bool = False,
        classify_fn: Callable[[str], IntentCategory] = heuristic_classify,
        rank_tool: FetchTool | None = None,
        detail_tool: FetchTool | None = None,
        resolve_tool: FetchTool | None = None,
        kb_tool: FetchTool | None = None,
        build_fn: Callable[
            [list[CapturedToolResult], str], dict[str, Any] | None
        ]
        = build_structured_output,
    ) -> None:
        # 延迟 import 真实工具，避免本模块 import 时拉 akshare 链路（测试注入桩）。
        if rank_tool is None or detail_tool is None or resolve_tool is None or kb_tool is None:
            from agents.tools.fund_tools import (
                query_fund_detail,
                query_fund_rank,
                query_knowledge_base,
                resolve_fund_code,
            )

        self.progress_callback = progress_callback
        self.stream_callback = stream_callback
        self.show_thinking = show_thinking
        self._classify = classify_fn
        self._rank_tool = rank_tool or query_fund_rank
        self._detail_tool = detail_tool or query_fund_detail
        self._resolve_tool = resolve_tool or resolve_fund_code
        self._kb_tool = kb_tool or query_knowledge_base
        self._build = build_fn

    # ------------------------------------------------------------------
    # 回调封装（同步/异步兼容 + best-effort，与 ShapeAdapter 一致）
    # ------------------------------------------------------------------
    async def _progress(self, stage: str, **kwargs: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            out = self.progress_callback(stage, **kwargs)
            if _is_coro(out):
                await out
        except Exception:
            return  # 回调失败不阻断降级

    async def _stream(self, token: str) -> None:
        if not token or self.stream_callback is None:
            return
        try:
            out = self.stream_callback(token)
            if _is_coro(out):
                await out
        except Exception:
            return

    async def _stream_text(self, text: str, *, emit_ttft: bool) -> None:
        """模拟流式：把降级文本适当切块走 ``stream_callback``（复用保形通路）。

        ``emit_ttft``：本轮回复的首个 token 前发一次 ``model_first_token`` 进度
        （与 ``run.py`` ``_stream_with_ttft`` / ``ShapeAdapter._emit_token`` 一致）。
        case A（无 prior_text）-> True；case B（prior_text 已触发过 TTFT）-> False。
        """
        chunks = [c for c in _chunk_text(text) if c]
        if not chunks:
            return
        if emit_ttft:
            await self._progress("model_first_token")
        for chunk in chunks:
            await self._stream(chunk)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def run(
        self,
        reason: FallbackReason,
        message: str,
        *,
        prior_text: str = "",
    ) -> FallbackResult:
        """执行启发式兜底降级路径。

        Args:
            reason: 触发原因（``model_unavailable`` / ``max_iters_exceeded``）。
            message: 用户原始问题（供启发式分类 + 直调取数）。
            prior_text: case B 时 ShapeAdapter 已流式吐出的部分文本（续流接其后）；
                case A 传 ""（干净从零开始）。

        Returns:
            ``FallbackResult``：``degraded_fallback=True`` + reason + structured_output
            （不放宽）+ final_text（含 prior_text 续流）。栅栏 #1 拒绝时 ``aborted=True``、
            ``structured_output=None``。
        """
        category = self._classify(message)
        await self._progress(
            "degraded_fallback", reason=reason, category=category
        )

        captured: list[CapturedToolResult] = []
        try:
            content_body, captured = await self._fetch(category, message)
        except _FenceAbort as ab:
            # 栅栏 #1：臆测代码 / 查不到代码 -> abort，不臆造、不放宽。
            return await self._finish_abort(reason, category, prior_text, ab.message)

        narrative = _DEGRADED_NOTICE + "\n\n" + content_body
        structured = self._build(captured, narrative)
        streamed = self._compose_streamed(prior_text, narrative)
        emit_ttft = not prior_text  # prior_text 非空 -> TTFT 已由 ShapeAdapter 发过
        await self._stream_text(streamed, emit_ttft=emit_ttft)

        final_text = prior_text + streamed
        return FallbackResult(
            degraded_fallback=True,
            reason=reason,
            category=category,
            final_text=final_text,
            structured_output=structured,
            aborted=False,
            abort_message="",
            captured_tool_names=[c.tool_name for c in captured],
        )

    async def _finish_abort(
        self,
        reason: FallbackReason,
        category: IntentCategory,
        prior_text: str,
        abort_message: str,
    ) -> FallbackResult:
        """栅栏 #1 abort：发降级提示 + abort 文案，无 structured_output（不放宽）。"""
        narrative = _DEGRADED_NOTICE + "\n\n" + abort_message
        streamed = self._compose_streamed(prior_text, narrative)
        emit_ttft = not prior_text
        await self._stream_text(streamed, emit_ttft=emit_ttft)
        return FallbackResult(
            degraded_fallback=True,
            reason=reason,
            category=category,
            final_text=prior_text + streamed,
            structured_output=None,
            aborted=True,
            abort_message=abort_message,
            captured_tool_names=[],
        )

    @staticmethod
    def _compose_streamed(prior_text: str, narrative: str) -> str:
        """组装待流式文本：case B 在 prior_text 后加空行分隔；case A 干净开头。"""
        if prior_text:
            return "\n\n" + narrative
        return narrative

    # ------------------------------------------------------------------
    # 取数序列（G5 决策 4：heuristic_classify -> 直调工具映射）
    # ------------------------------------------------------------------
    async def _fetch(
        self, category: IntentCategory, message: str
    ) -> tuple[str, list[CapturedToolResult]]:
        """按分类直调取数工具（不调 LLM）。栅栏 #1 在 interpret/compare 下不放宽。

        返回 (content_body, captured)。臆测代码 / 查不到代码 -> ``raise _FenceAbort``。
        """
        if category == "product_query":
            raw = await self._rank_tool(message)
            payload = _parse_tool_result(raw)
            captured = [CapturedToolResult("query_fund_rank", payload)]
            return _summarize_payload(category, payload), captured

        if category in ("product_interpret", "product_compare"):
            # 栅栏 #1：先跑名称转代码（含可信集校验），查不到即 abort（不放宽、不臆造）。
            # 真实 ``resolve_fund_code`` 对臆测代码 / 查不到名称 ``raise AgentOrientedException``
            # （栅栏 #2 M4 abort 信号）-> 此处捕为干净的 fence #1 abort，不回灌自愈（降级路径无 LLM）。
            codes = _extract_codes(message)
            try:
                if codes:
                    # 用户给了代码：校验是否在可信集（臆测代码被 resolve 拒 -> abort）
                    # resolve_fund_code 对含 6 位代码的 query 会逐个 is_trusted 校验。
                    resolve_payload = _parse_tool_result(
                        await self._resolve_tool(" ".join(codes))
                    )
                    final_codes = _codes_from_resolve(resolve_payload) or codes
                else:
                    # 用户给名称：resolve 多策略匹配，未命中 -> abort
                    resolve_payload = _parse_tool_result(
                        await self._resolve_tool(message)
                    )
                    final_codes = _codes_from_resolve(resolve_payload)
            except AgentOrientedException as e:
                raise _FenceAbort(_ABORT_NO_CODE_MSG) from e
            if not final_codes:
                raise _FenceAbort(_ABORT_NO_CODE_MSG)
            detail_query = " ".join(final_codes) if final_codes else message
            raw = await self._detail_tool(detail_query)
            payload = _parse_tool_result(raw)
            captured = [CapturedToolResult("query_fund_detail", payload)]
            return _summarize_payload(category, payload), captured

        # other -> kb（无 builder，纯文本）
        raw = await self._kb_tool(message)
        payload = _parse_tool_result(raw)
        captured = [CapturedToolResult("query_knowledge_base", payload)]
        return _summarize_payload(category, payload), captured


# ---------------------------------------------------------------------------
# 栅栏 #1 abort 信号（内部）：取数序列抛出，run 捕获 -> _finish_abort
# ---------------------------------------------------------------------------
class _FenceAbort(Exception):
    """栅栏 #1 中止：臆测代码 / 查不到代码 -> 不臆造、不放宽。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _is_coro(obj: Any) -> bool:
    import asyncio

    return asyncio.iscoroutine(obj)


def _chunk_text(text: str) -> list[str]:
    """把降级文本适当切块（按句号/换行切，保留分隔符），供模拟流式。"""
    if not text:
        return []
    parts = re.split(r"(?<=[\n。！？!?;；])", text)
    return [p for p in parts if p]


def _msg_text(msg: Msg) -> str:
    """从 ``Msg.content``（``list[TextBlock]``）拼出纯文本。"""
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            getattr(b, "text", "") or ""
            for b in content
            if hasattr(b, "text")
        )
    return str(content or "")


# ---------------------------------------------------------------------------
# orchestrator 级降级路径函数（G5 决策自写层 1）
# ---------------------------------------------------------------------------
async def drive_with_fallback(
    adapter: ShapeAdapter,
    agent: Any,
    user_input: Msg,
    fallback: HeuristicFallback,
) -> tuple[str, FallbackResult | None]:
    """驱动 ``ShapeAdapter.drive``；LLM-down（A）/ max_iters 耗尽（B）时触发兜底。

    栅栏 #3 与栅栏 #6 续流共存（不改 ShapeAdapter）：

    - **A**：``reply_stream`` 模型 API 失败（``GatewayChatModel`` 熔断/超时/fallback 耗尽抛
      异常）经 ``drive()`` 传播 -> 此处 ``except`` 捕获 -> ``reason="model_unavailable"``
      ``prior_text=""``（模型未产出文本，干净接管）。
    - **B**：``ExceedMaxItersEvent`` 是 yield（不抛），``drive()`` 正常返回 ->
      从 yielded 事件见 ``("progress", "exceed_max_iters")`` 标记 -> ``reason=
      "max_iters_exceeded"`` ``prior_text=adapter.final_text``（续流接已流文本后）。
    - 正常完成 -> ``(adapter.final_text, None)``（未触发兜底）。

    供 T10 ``run_chat_turn_async`` 调用（或内联同逻辑）；本函数只做"驱动 + 触发判定 +
    续流"，不做审计/合规/structured_outputs 接线（那些在 T10 主 seam）。
    """
    driven: list[tuple[str, str]] = []
    try:
        async for kind, detail in adapter.drive(agent, user_input):
            driven.append((kind, detail))
    except Exception:
        # A：模型 API 失败传播出 reply_stream（ModelConfig 重试+fallback 耗尽）
        message = _msg_text(user_input)
        result = await fallback.run(
            "model_unavailable", message, prior_text=""
        )
        return result.final_text, result

    # B：drive 正常返回，检查是否见 exceed_max_iters 标记
    if any(d == "exceed_max_iters" for _, d in driven):
        message = _msg_text(user_input)
        result = await fallback.run(
            "max_iters_exceeded", message, prior_text=adapter.final_text
        )
        return result.final_text, result

    return adapter.final_text, None
