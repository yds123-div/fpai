from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pkg.logger import get_logger


logger = get_logger(__name__)


@dataclass
class AgentRunContext:
    """运行上下文（后续可扩展：用户、权限、会话、产品池等）。"""

    session_id: str | None = None
    user_id: str | None = None
    permission_context: dict[str, Any] | None = None
    product_ids: list[str] | None = None
    customer_profile: str | None = None

    # 模型覆盖（来自 model_id 的 ai_models 配置）
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None

    # 其它 Agent 走知识库检索时使用
    knowledge_base_id: str | None = None

    # SSE/流式体验优化：进度与 token 回调（由 API 层注入；Agent 可选使用）
    progress_callback: Any | None = None
    stream_callback: Any | None = None

    # 是否允许并展示模型推理过程（输出 <think>...</think>）
    show_thinking: bool = False


class BaseBusinessAgent:
    name: str = "BaseBusinessAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        raise NotImplementedError


def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return s


def resolve_agent_overrides(
    *,
    agent_key: str,
    ctx: AgentRunContext,
    default_system_prompt: str,
) -> tuple[str, AgentRunContext]:
    """
    从 agent_profiles 读取配置覆盖：
    - system_prompt：覆盖默认 system prompt（仅当非空）
    - model_id：覆盖 ctx.model_name/base_url/api_key（用于本轮 LLM 调用）

    说明：
    - 若未配置 MySQL 或找不到 agent_key，则保持默认行为
    - 仅当 enabled=1 且未删除时生效
    """
    key = (agent_key or "").strip()
    if not key:
        return default_system_prompt, ctx

    try:
        from agents.agent_store import get_agent as _get_agent

        cfg = _get_agent(key)
    except Exception:
        cfg = None

    if not isinstance(cfg, dict) or cfg.get("deleted_at") or int(cfg.get("enabled") or 0) != 1:
        return default_system_prompt, ctx

    prompt = (cfg.get("system_prompt") or "").strip() or default_system_prompt

    mid = cfg.get("model_id")
    if mid is None:
        return prompt, ctx
    try:
        from models.store import get_model_by_id

        m = get_model_by_id(int(mid))
    except Exception:
        m = None
    if not isinstance(m, dict) or int(m.get("enabled") or 0) != 1:
        return prompt, ctx

    # 覆盖本轮 ctx 的模型配置（就地修改，避免复制 dataclass）
    try:
        ctx.model_name = (m.get("model_name") or "").strip() or ctx.model_name
        ctx.base_url = (m.get("base_url") or "").strip() or ctx.base_url
        ctx.api_key = (m.get("api_key") or "").strip() or ctx.api_key
    except Exception:
        pass
    return prompt, ctx


def resolve_agent_skill_keys(*, agent_key: str) -> list[str] | None:
    """
    从 agent_profiles 读取 skill_keys（JSON 数组字符串或空）。
    返回：
    - None：未配置/不可用
    - list[str]：配置的 skill key 列表（可能为空）
    """
    key = (agent_key or "").strip()
    if not key:
        return None
    try:
        from agents.agent_store import get_agent as _get_agent

        cfg = _get_agent(key)
    except Exception:
        cfg = None
    if not isinstance(cfg, dict) or cfg.get("deleted_at") or int(cfg.get("enabled") or 0) != 1:
        return None
    raw = cfg.get("skill_keys")
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [str(x) for x in obj if str(x).strip()]
        except Exception:
            return []
    return []


async def run_configured_skills(
    *,
    skill_keys: list[str],
    question: str,
    ctx: AgentRunContext,
) -> Any:
    """
    按顺序尝试执行 skills，返回第一个成功的 payload（dict）。
    约定：
    - 每个 skill 模块需提供 async run(question:str, ctx:dict)->str（JSON 字符串）
    - skill_profiles.module_path 指向该模块
    """
    if not skill_keys:
        return None
    try:
        from agents.skills_store import get_skill as _get_skill
    except Exception:
        _get_skill = None  # type: ignore
    for k in skill_keys:
        kk = (k or "").strip()
        if not kk:
            continue
        try:
            if _get_skill is None:
                continue
            meta = _get_skill(kk)
            if not isinstance(meta, dict) or meta.get("deleted_at") or int(meta.get("enabled") or 0) != 1:
                continue
            mp = (meta.get("module_path") or "").strip()
            if not mp:
                continue
            mod = __import__(mp, fromlist=["run"])
            fn = getattr(mod, "run", None)
            if not callable(fn):
                continue
            await _emit_progress(ctx, "skill_fetching")
            s = await fn(question, {"session_id": ctx.session_id, "user_id": ctx.user_id})
            return {"skill": kk, "payload": _safe_json_loads(s)}
        except Exception:
            continue
    return None


async def _emit_progress(ctx: AgentRunContext, stage: str):
    try:
        cb = getattr(ctx, "progress_callback", None)
        if callable(cb):
            out = cb(stage)
            if asyncio.iscoroutine(out):
                await out
    except Exception:
        return


async def _llm_call_maybe_stream(
    *,
    ctx: AgentRunContext,
    messages: list[dict[str, str]],
) -> str:
    """
    统一的 LLM 调用：
    - 若 API 层提供了 stream_callback 且当前轮模型配置有 base_url：走 OpenAI 兼容流式，边生成边推送 token
    - 否则：走原 llm_chat（一次性返回）
    """
    stream_cb = getattr(ctx, "stream_callback", None)
    # 只要模型名存在就尽量走真正流式；
    # base_url 可由 llm_chat_stream 内部回退到网关默认配置。
    if callable(stream_cb) and (ctx.model_name or "").strip():
        try:
            from model_gateway.llm import llm_chat_stream

            full = ""
            async for t in llm_chat_stream(
                messages,
                model=ctx.model_name,
                base_url=ctx.base_url,
                api_key=ctx.api_key,
                show_thinking=bool(getattr(ctx, "show_thinking", False)),
            ):
                if not t:
                    continue
                full += t
                out = stream_cb(t)
                if asyncio.iscoroutine(out):
                    await out
            return full.strip()
        except Exception as e:
            logger.warning("流式 LLM 调用失败，回退到非流式: %s", e)
            # fallthrough to non-stream

    from model_gateway.llm import llm_chat

    return (
        await asyncio.to_thread(
            llm_chat,
            messages,
            model=ctx.model_name,
            base_url=ctx.base_url,
            api_key=ctx.api_key,
            enable_thinking=bool(getattr(ctx, "show_thinking", False)),
        )
    ).strip()

