# -*- coding: utf-8 -*-
"""
知识库检索（外部接口模式）：
- 在知识库页面选择模型与知识库后，通过本路由调用外部知识库检索接口获取片段列表，供前端展示或后续问答链路使用。
- 外部知识库服务由环境变量配置，当前约定：
    - EXTERNAL_KB_BASE_URL：外部知识库服务基础地址，如 http://localhost:8080
    - EXTERNAL_KB_API_KEY：访问外部知识库的鉴权密钥（对应 X-API-Key）

后端仅作为轻量代理与契约统一层，不落库。
"""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger


router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = get_logger(__name__)


class ExternalKnowledgeQuery(BaseModel):
    """外部知识库检索请求体。"""

    model: str = Field(default="", description="模型标识，由前端选择传入，可透传给外部服务（当前外部接口未使用）")
    knowledge_base_id: str = Field(default="", description="知识库标识，由前端选择传入，对应 knowledge_base_ids 中的一个元素")
    question: str = Field(default="", description="用户查询问题/检索文本，对应外部接口的 query")
    top_k: int = Field(default=5, ge=1, le=50, description="返回的最多片段数量（当前外部接口未使用）")

class KnowledgeChatBody(BaseModel):
    """知识库对话：选择模型与知识库，基于外部检索结果进行回答。"""

    model_id: int | None = Field(default=None, description="模型配置 ID（来自模型管理）")
    model: str = Field(default="", description="大模型名称（兼容旧字段）")
    knowledge_base_id: str = Field(default="", description="知识库 UUID（将用于 knowledge_base_ids）")
    message: str = Field(default="", description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20, description="检索片段数量")


def _chunk_text(text: str, chunk_size: int = 300) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= chunk_size:
        return [text]
    out: list[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + chunk_size])
        i += chunk_size
    return out


def _sse_event(event: str, data: Any) -> str:
    import json

    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _external_kb_search(question: str, knowledge_base_id: str, top_k: int) -> list[dict[str, Any]]:
    """
    调用外部知识库检索接口并返回「归一化后的 items」。
    复用 external-search 的核心逻辑，但不走 HTTP 层封装。
    """
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
        logger.warning("external kb search failed: %s", e)
        return []

    # 兼容 {success,true,data:[...]} 结构
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
            if isinstance(snippet, str) and len(snippet) > 240:
                snippet = snippet[:240] + "…"
            normalized.append(
                {
                    "id": it.get("id") or it.get("chunk_id") or it.get("seq"),
                    "title": title or "未命名片段",
                    "snippet": snippet,
                    "content": content,
                    "score": it.get("score"),
                    "source": (it.get("knowledge_filename") or it.get("knowledge_title") or it.get("source") or "").strip(),
                    "raw": it,
                }
            )
    return normalized


async def _stream_openai_chat(
    base_url: str,
    api_key: str | None,
    model_name: str,
    messages: list[dict[str, str]],
    max_tokens: int = 5000,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    通过 OpenAI 兼容接口做真正流式对话（/chat/completions, stream=true），逐个 yield 文本片段。
    """
    try:
        import httpx
        import json
    except ImportError:
        return

    bu = (base_url or "").rstrip("/")
    if not bu.endswith("/v1"):
        bu = bu + "/v1"
    url = bu + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield str(content)
        except Exception as e:
            logger.warning("stream_openai_chat failed: %s", e)
            return


@router.get("/bases")
async def list_bases(enabledOnly: bool = True):
    """知识库下拉选项：从 MySQL 读取 uuid+name。"""
    try:
        from knowledge.store import list_knowledge_bases

        items = list_knowledge_bases(enabled_only=enabledOnly)
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("/bases/sync")
async def sync_bases():
    """手动触发同步外部知识库列表到 MySQL。"""
    try:
        from knowledge.sync import sync_knowledge_bases_once

        out = sync_knowledge_bases_once()
        if not out.get("ok"):
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.SERVICE_UNAVAILABLE, message=out.get("message") or "同步失败", data=out),
            )
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=out))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("/external-search")
async def external_search(body: ExternalKnowledgeQuery):
    """
    调用外部知识库检索接口，返回检索到的片段列表。

    - 若未配置 EXTERNAL_KB_BASE_URL，则返回 SERVICE_UNAVAILABLE。
    - 按以下约定调用外部接口：
        URL:  {EXTERNAL_KB_BASE_URL}/api/v1/knowledge-search
        头:   Content-Type: application/json
              X-API-Key:   EXTERNAL_KB_API_KEY（如配置）
        体:   { "query": "...", "knowledge_base_ids": ["..."] }
    """
    base_url = (os.getenv("EXTERNAL_KB_BASE_URL") or "").strip()
    api_key = (os.getenv("EXTERNAL_KB_API_KEY") or "").strip()
    if not base_url:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="外部知识库未配置（缺少 EXTERNAL_KB_BASE_URL）",
                data=None,
            ),
        )

    query = (body.question or "").strip()
    if not query:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR,
                message="问题不能为空",
                data=None,
            ),
        )

    try:
        import httpx
    except ImportError:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="后端缺少 httpx 依赖，无法调用外部知识库",
                data=None,
            ),
        )

    # 目标接口：{base_url}/api/v1/knowledge-search
    url = f"{base_url.rstrip('/')}/api/v1/knowledge-search"
    payload: dict[str, Any] = {
        "query": query,
        "knowledge_base_ids": [body.knowledge_base_id] if body.knowledge_base_id else [],
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        # 本地开发环境常见存在 HTTP(S)_PROXY，可能导致 localhost 请求走代理并返回 502；
        # 这里禁用读取环境代理配置，强制直连目标地址。
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:  # type: ignore[name-defined]
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"外部知识库 HTTP 错误：{e.response.status_code}",
                data={"status_code": e.response.status_code},
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"外部知识库调用失败：{e}",
                data={"url": url},
            ),
        )

    # 外部接口返回示例：
    # { "success": true, "data": [ { id, content, score, knowledge_title, matched_content, ... }, ... ] }
    # 这里做一次归一化，兼容 items/data/list 等字段，并整理为前端易展示字段。
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
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            title = (it.get("knowledge_title") or it.get("knowledge_filename") or it.get("title") or "").strip()
            content = it.get("content") or it.get("matched_content") or ""
            snippet = it.get("matched_content") or it.get("content") or ""
            if isinstance(snippet, str) and len(snippet) > 240:
                snippet = snippet[:240] + "…"
            normalized.append(
                {
                    "id": it.get("id") or it.get("chunk_id") or it.get("seq"),
                    "title": title or "未命名片段",
                    "snippet": snippet,
                    "content": content,
                    "score": it.get("score"),
                    "source": (it.get("knowledge_filename") or it.get("knowledge_title") or it.get("source") or "").strip(),
                    # 保留原始字段便于调试/后续扩展
                    "raw": it,
                }
            )
    items = normalized
    return JSONResponse(
        status_code=200,
        content=envelope(
            code=ErrorCode.OK,
            message=message_for(ErrorCode.OK),
            data={"items": items},
        ),
    )


@router.post("/chat")
async def knowledge_chat_stream(body: KnowledgeChatBody):
    """
    知识库对话（SSE 流式）：
    1) 调用外部知识库检索得到片段
    2) 将片段拼入 prompt 调用 LLM
    3) 将回答按块推送 message 事件，并推送 citation/done
    """
    question = (body.message or "").strip()
    if not question:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="message 不能为空", data=None),
        )

    async def event_gen():
        try:
            items = await _external_kb_search(question, body.knowledge_base_id or "", body.top_k or 5)
            # 推送引用（先发，便于前端提前展示）
            for c in items:
                yield _sse_event("citation", {k: v for k, v in c.items() if k != "raw"}).encode("utf-8")

            context_blocks: list[str] = []
            for i, it in enumerate(items, start=1):
                ctx = (it.get("content") or "").strip()
                if not ctx:
                    continue
                title = it.get("title") or it.get("source") or f"片段{i}"
                score = it.get("score")
                context_blocks.append(f"[{i}] {title} (score={score})\n{ctx}")

            context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else ""

            sys_prompt = (
                "你是知识库问答助手。请严格基于给定的【知识库片段】回答用户问题；"
                "若片段中找不到依据，请明确说明“知识库未检索到相关依据”，并给出你建议的补充提问方向。"
                "回答要简洁、结构化，可用要点列表。"
            )
            user_content = f"用户问题：{question}\n\n【知识库片段】\n{context_text or '（无）'}"
            # 若传入 model_id，则从 MySQL 读取模型配置（base_url/api_key/model_name）
            base_url_override: str | None = None
            api_key_override: str | None = None
            model_name_override: str | None = (body.model or "").strip() or None
            if body.model_id:
                try:
                    from models.store import get_model_by_id

                    cfg = get_model_by_id(int(body.model_id))
                    if cfg and int(cfg.get("enabled") or 0) == 1:
                        base_url_override = (cfg.get("base_url") or "").strip() or None
                        api_key_override = (cfg.get("api_key") or "").strip() or None
                        model_name_override = (cfg.get("model_name") or "").strip() or model_name_override
                except Exception:
                    pass

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ]

            if base_url_override and model_name_override:
                # 选中了自定义模型配置，且提供了 base_url，则通过 OpenAI 兼容接口做真正流式输出
                async for chunk in _stream_openai_chat(
                    base_url=base_url_override,
                    api_key=api_key_override,
                    model_name=model_name_override,
                    messages=messages,
                ):
                    yield _sse_event("message", {"text": chunk}).encode("utf-8")
            else:
                # 回退到统一 LLM 网关（非真正 token 级流式，但保持兼容）
                from model_gateway.llm import llm_chat

                answer = llm_chat(
                    messages=messages,
                    model=model_name_override,
                )
                answer = (answer or "").strip() or "当前无法生成回复，请稍后重试。"
                for chunk in _chunk_text(answer):
                    yield _sse_event("message", {"text": chunk}).encode("utf-8")

            yield _sse_event(
                "done",
                {
                    "knowledgeBaseId": body.knowledge_base_id or "",
                    "model": model_name_override or "",
                    "citationsCount": len(items),
                },
            ).encode("utf-8")
        except Exception as e:
            logger.warning("knowledge chat failed: %s", e, exc_info=True)
            yield _sse_event("error", {"code": int(ErrorCode.INTERNAL_ERROR), "message": message_for(ErrorCode.INTERNAL_ERROR)}).encode(
                "utf-8"
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

