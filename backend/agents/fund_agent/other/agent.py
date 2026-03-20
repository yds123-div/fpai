from __future__ import annotations

from typing import Any
import os

from agents.fund_agent.runtime import AgentRunContext, BaseBusinessAgent, _emit_progress, _llm_call_maybe_stream, resolve_agent_overrides
from pkg.logger import get_logger


logger = get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = "你是一个通用助手，请用中文简洁、结构化回答用户问题。"
DEFAULT_KB_SYSTEM_PROMPT = (
    "你是知识库问答助手。请严格基于给定的【知识库片段】回答用户问题；"
    "若片段中找不到依据，请明确说明“知识库未检索到相关依据”，并给出建议的补充提问方向。"
    "回答要简洁、结构化，可用要点列表。"
)


class OtherAgent(BaseBusinessAgent):
    name = "OtherAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        q = (question or "").strip()
        if not q:
            return ""

        # other：允许通过 agent_profiles 覆盖通用回答提示词 + 模型
        system_prompt, ctx = resolve_agent_overrides(agent_key="other", ctx=ctx, default_system_prompt=DEFAULT_SYSTEM_PROMPT)

        # 闲聊/客套类问题：即使前端传了 knowledge_base_id，也不触发知识库检索
        if _is_chitchat(q):
            return await self._free_answer(q, ctx, system_prompt=system_prompt)

        kb_id = (ctx.knowledge_base_id or "").strip()
        # 若用户未选择知识库，则直接自由回答
        if not kb_id:
            return await self._free_answer(q, ctx, system_prompt=system_prompt)

        items = await self._external_kb_search(q, kb_id, top_k=5)
        if items:
            return await self._answer_with_kb(q, items, ctx, system_prompt=system_prompt)
        # 知识库检索不到，则模型自由回答
        return await self._free_answer(q, ctx, hint="知识库未检索到相关依据", system_prompt=system_prompt)

    async def _external_kb_search(self, question: str, knowledge_base_id: str, top_k: int) -> list[dict[str, Any]]:
        base_url = (os.getenv("EXTERNAL_KB_BASE_URL") or "").strip()
        api_key = (os.getenv("EXTERNAL_KB_API_KEY") or "").strip()
        if not base_url:
            return []
        try:
            import httpx
        except ImportError:
            return []
        url = f"{base_url.rstrip('/')}/api/v1/knowledge-search"
        payload: dict[str, Any] = {
            "query": (question or "").strip(),
            "knowledge_base_ids": [knowledge_base_id] if (knowledge_base_id or "").strip() else [],
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OtherAgent external kb search failed: %s", e)
            return []

        raw_items: Any = None
        if isinstance(data, dict):
            raw_items = data.get("items")
            if raw_items is None:
                raw_items = data.get("data")
            if raw_items is None:
                raw_items = data.get("list")
            if raw_items is None:
                raw_items = data.get("results")
        else:
            raw_items = data

        normalized: list[dict[str, Any]] = []
        if isinstance(raw_items, list):
            for it in raw_items[: max(1, int(top_k or 5))]:
                if not isinstance(it, dict):
                    continue
                title = (it.get("knowledge_title") or it.get("knowledge_filename") or it.get("title") or "").strip()
                content = it.get("content") or it.get("matched_content") or ""
                snippet = it.get("matched_content") or it.get("content") or ""
                normalized.append(
                    {
                        "title": title or "未命名片段",
                        "content": content,
                        "snippet": snippet,
                        "score": it.get("score"),
                        "source": (it.get("knowledge_filename") or it.get("knowledge_title") or it.get("source") or "").strip(),
                    }
                )
        return normalized

    async def _answer_with_kb(
        self, question: str, items: list[dict[str, Any]], ctx: AgentRunContext, *, system_prompt: str
    ) -> str:
        context_blocks: list[str] = []
        for i, it in enumerate(items, start=1):
            c = (it.get("content") or "").strip()
            if not c:
                continue
            title = it.get("title") or it.get("source") or f"片段{i}"
            score = it.get("score")
            context_blocks.append(f"[{i}] {title} (score={score})\n{c}")
        context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else ""
        sys_prompt = (system_prompt or "").strip() or DEFAULT_KB_SYSTEM_PROMPT
        user_content = f"用户问题：{question}\n\n【知识库片段】\n{context_text or '（无）'}"
        return await self._llm_call(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}],
            ctx,
        )

    async def _free_answer(
        self, question: str, ctx: AgentRunContext, hint: str | None = None, *, system_prompt: str
    ) -> str:
        sys_prompt = (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
        user_content = question if not hint else f"{question}\n\n（提示：{hint}）"
        return await self._llm_call(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}],
            ctx,
        )

    async def _llm_call(self, messages: list[dict[str, str]], ctx: AgentRunContext) -> str:
        try:
            await _emit_progress(ctx, "llm_generating")
            return await _llm_call_maybe_stream(ctx=ctx, messages=messages)
        except Exception as e:
            logger.warning("OtherAgent LLM 调用失败: %s", e)
            return ""


def _is_chitchat(text: str) -> bool:
    """
    轻量闲聊识别：命中问候/客套词就认为是闲聊。
    仅当输入不包含 6 位基金代码时才短路，避免误伤产品问题。
    """
    try:
        import re as _re

        t = (text or "").strip()
        if not t:
            return False

        # 若包含基金代码，优先按产品问题处理
        if _re.search(r"(?<!\d)\d{6}(?!\d)", t):
            return False

        triggers = (
            "你好",
            "您好",
            "在吗",
            "哈喽",
            "你好呀",
            "早上好",
            "晚上好",
            "谢谢",
            "感谢",
            "怎么称呼",
            "你是谁",
            "你叫什么",
            "再见",
            "拜拜",
            "闲聊",
            "聊天",
            "打个招呼",
            "打招呼",
            "问候",
        )
        return any(x in t for x in triggers)
    except Exception:
        return False

