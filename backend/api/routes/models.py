# -*- coding: utf-8 -*-
"""
模型管理 API：

- 列表/新增/删除
- 连接测试（Ollama / Remote API）

说明：
- 不向前端返回 api_key 明文，仅返回 has_api_key。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger

router = APIRouter(prefix="/models", tags=["models"])
logger = get_logger(__name__)


class ModelUpsertBody(BaseModel):
    id: int | None = None
    name: str = Field(default="", description="显示名称（可为空；为空时使用 model_name）")
    source: str = Field(default="remote")  # ollama | remote
    vendor: str = Field(default="custom")
    model_name: str = Field(default="")
    base_url: str = Field(default="")
    api_key: str | None = Field(default=None)
    enabled: bool = True


class ModelTestBody(BaseModel):
    source: str = Field(default="remote")  # ollama | remote
    vendor: str = Field(default="custom")
    model_name: str = Field(default="")
    base_url: str = Field(default="")
    api_key: str | None = Field(default=None)


@router.get("")
async def list_models(enabledOnly: bool = True):
    try:
        from models.store import list_models as _list

        items = _list(enabled_only=enabledOnly)
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("")
async def upsert_model(body: ModelUpsertBody):
    payload = body.model_dump()
    # api_key None 表示不更新
    if payload.get("api_key") is None:
        payload.pop("api_key", None)
    payload["enabled"] = 1 if body.enabled else 0
    try:
        from models.store import upsert_model as _upsert

        mid = _upsert(payload)
        if not mid:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"id": mid}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.delete("/{model_id}")
async def delete_model(model_id: int):
    try:
        from models.store import delete_model as _del

        ok = _del(int(model_id))
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.NOT_FOUND, message="模型不存在", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("/test")
async def test_connection(body: ModelTestBody):
    """
    连接测试：
    - Ollama：GET {base_url}/api/tags
    - Remote(OpenAI兼容)：POST {base_url}/(v1)/chat/completions （带 Authorization: Bearer）
    """
    source = (body.source or "").strip()
    base_url = (body.base_url or "").strip()
    api_key = (body.api_key or "").strip() if body.api_key else ""
    if not base_url:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.VALIDATION_ERROR, message="Base URL 不能为空", data=None))

    try:
        import httpx
    except ImportError:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.SERVICE_UNAVAILABLE, message="缺少 httpx", data=None))

    try:
        if source == "ollama":
            url = base_url.rstrip("/") + "/api/tags"
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            # 兼容返回 {models:[{name:...}]}
            models = data.get("models") if isinstance(data, dict) else None
            sample = []
            if isinstance(models, list):
                for m in models[:10]:
                    if isinstance(m, dict) and m.get("name"):
                        sample.append(m.get("name"))
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"reachable": True, "sample": sample}))

        # remote
        # Remote(OpenAI兼容)：用最小的 chat/completions 请求做连通性测试。
        # 说明：很多服务的 /v1 根路径与 /v1/models 并不对外开放或不支持 GET，因此用 POST 更通用。
        bu = base_url.strip().rstrip("/")
        if bu.endswith("/v1"):
            url = bu + "/chat/completions"
        else:
            url = bu + "/v1/chat/completions"
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
        model_name = (body.model_name or "").strip() or "gpt-3.5-turbo"
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=15.0, trust_env=False, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # 兼容 OpenAI 风格：{choices:[{message:{content}}]}
        sample = []
        try:
            if isinstance(data, dict) and isinstance(data.get("choices"), list) and data["choices"]:
                choice0 = data["choices"][0]
                if isinstance(choice0, dict):
                    msg = choice0.get("message") or {}
                    if isinstance(msg, dict) and msg.get("content"):
                        sample.append(str(msg.get("content"))[:80])
        except Exception:
            pass
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.OK,
                message="ok",
                data={"reachable": True, "sample": sample, "final_url": str(resp.url)},
            ),
        )
    except Exception as e:
        logger.warning("model test failed: %s", e)
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.SERVICE_UNAVAILABLE, message=f"连接失败：{e}", data={"reachable": False}),
        )

