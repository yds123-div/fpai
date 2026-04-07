# -*- coding: utf-8 -*-
"""
系统参数配置 API：

- GET /config/external-kb：获取外部知识库配置
- PUT /config/external-kb：保存外部知识库配置
- POST /config/external-kb/test：测试外部知识库连接

配置存储在 config_strategy 表，config_key = 'external_kb_config'
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger

router = APIRouter(prefix="/config", tags=["config"])
logger = get_logger(__name__)

CONFIG_KEY_EXTERNAL_KB = "external_kb_config"


def _is_admin(role: str | None) -> bool:
    """检查是否为管理员角色"""
    r = (role or "").strip().lower()
    return r in ("admin", "administrator", "ops_admin")


def _forbidden():
    """返回 403 禁止访问"""
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.FORBIDDEN, message=message_for(ErrorCode.FORBIDDEN), data=None),
    )


class ExternalKBConfigBody(BaseModel):
    """外部知识库配置请求体"""

    base_url: str = Field(default="", description="外部知识库服务基础地址，如 http://localhost:8080")
    api_key: str = Field(default="", description="访问外部知识库的鉴权密钥（对应 X-API-Key）")
    enabled: bool = Field(default=True, description="是否启用外部知识库")


@router.get("/external-kb")
async def get_external_kb_config(auth=Depends(get_auth_context)):
    """
    获取外部知识库配置。
    
    返回格式：
    {
      "base_url": "http://localhost:8080",
      "api_key": "***",  // 脱敏显示
      "enabled": true,
      "version": 1
    }
    """
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()

    try:
        from config.store import get_config

        config = get_config(CONFIG_KEY_EXTERNAL_KB, use_cache=False)
        
        if config is None:
            # 如果数据库没有配置，尝试从环境变量读取（兼容旧方式）
            base_url = os.getenv("EXTERNAL_KB_BASE_URL", "").strip()
            api_key = os.getenv("EXTERNAL_KB_API_KEY", "").strip()
            
            if base_url or api_key:
                # 返回环境变量配置（标记为未保存到数据库）
                return JSONResponse(
                    status_code=200,
                    content=envelope(
                        code=ErrorCode.OK,
                        message="ok",
                        data={
                            "base_url": base_url,
                            "api_key": "***" if api_key else "",  # 脱敏
                            "api_key_masked": bool(api_key),
                            "enabled": True,
                            "source": "env",  # 标记来源为环境变量
                            "version": 0,
                        },
                    ),
                )
            else:
                # 完全未配置
                return JSONResponse(
                    status_code=200,
                    content=envelope(
                        code=ErrorCode.OK,
                        message="ok",
                        data={
                            "base_url": "",
                            "api_key": "",
                            "api_key_masked": False,
                            "enabled": False,
                            "source": "none",
                            "version": 0,
                        },
                    ),
                )

        # 从数据库读取到配置
        base_url = config.get("base_url", "")
        api_key = config.get("api_key", "")
        enabled = config.get("enabled", True)
        version = config.get("_version", 0)

        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.OK,
                message="ok",
                data={
                    "base_url": base_url,
                    "api_key": "***" if api_key else "",  # 脱敏显示
                    "api_key_masked": bool(api_key),
                    "enabled": enabled,
                    "source": "database",
                    "version": version,
                },
            ),
        )

    except Exception as e:
        logger.exception("get_external_kb_config failed")
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=str(e), data=None),
        )


@router.put("/external-kb")
async def update_external_kb_config(body: ExternalKBConfigBody, auth=Depends(get_auth_context)):
    """
    保存外部知识库配置到数据库。
    
    请求体：
    {
      "base_url": "http://localhost:8080",
      "api_key": "your-api-key",
      "enabled": true
    }
    """
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()

    base_url = (body.base_url or "").strip()
    api_key = (body.api_key or "").strip()
    enabled = body.enabled

    # 基本校验
    if enabled and not base_url:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="启用时必须填写 base_url", data=None),
        )
    
    # 校验 base_url 格式：不应包含 API 路径
    if base_url and ("/api/" in base_url or "/knowledge" in base_url.lower()):
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR, 
                message="base_url 应该只填写基础地址（如 http://139.9.59.175:8080），不要包含 /api/ 路径", 
                data=None
            ),
        )

    try:
        from config.store import set_config

        config_value = {
            "base_url": base_url,
            "api_key": api_key,
            "enabled": enabled,
        }

        success = set_config(CONFIG_KEY_EXTERNAL_KB, config_value)

        if not success:
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.INTERNAL_ERROR, message="保存配置失败", data=None),
            )

        logger.info(
            "external_kb_config updated",
            extra={
                "user_id": getattr(auth, "user_id", ""),
                "base_url": base_url,
                "enabled": enabled,
            },
        )

        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.OK, message="保存成功", data={"ack": True}),
        )

    except Exception as e:
        logger.exception("update_external_kb_config failed")
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=str(e), data=None),
        )


@router.post("/external-kb/test")
async def test_external_kb_connection(auth=Depends(get_auth_context)):
    """
    测试外部知识库连接。
    
    使用当前保存的配置（或环境变量）尝试调用外部知识库的健康检查接口。
    """
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()

    try:
        # 读取配置
        from config.store import get_config

        config = get_config(CONFIG_KEY_EXTERNAL_KB, use_cache=False)

        if config:
            base_url = config.get("base_url", "").strip()
            api_key = config.get("api_key", "").strip()
            enabled = config.get("enabled", True)
        else:
            # 回退到环境变量
            base_url = os.getenv("EXTERNAL_KB_BASE_URL", "").strip()
            api_key = os.getenv("EXTERNAL_KB_API_KEY", "").strip()
            enabled = True

        if not base_url:
            return JSONResponse(
                status_code=200,
                content=envelope(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="未配置外部知识库地址",
                    data=None,
                ),
            )

        if not enabled:
            return JSONResponse(
                status_code=200,
                content=envelope(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="外部知识库已禁用",
                    data=None,
                ),
            )

        # 尝试调用健康检查接口
        try:
            import httpx
        except ImportError:
            return JSONResponse(
                status_code=200,
                content=envelope(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="后端缺少 httpx 依赖",
                    data=None,
                ),
            )

        # 尝试调用 /api/v1/health 或 /health
        test_urls = [
            f"{base_url.rstrip('/')}/api/v1/health",
            f"{base_url.rstrip('/')}/health",
            f"{base_url.rstrip('/')}/api/v1/knowledge-bases",  # 尝试列表接口
        ]

        headers: dict[str, Any] = {}
        if api_key:
            headers["X-API-Key"] = api_key

        last_error = None
        for url in test_urls:
            try:
                async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code < 500:  # 2xx, 3xx, 4xx 都算连接成功
                        return JSONResponse(
                            status_code=200,
                            content=envelope(
                                code=ErrorCode.OK,
                                message="连接成功",
                                data={
                                    "url": url,
                                    "status_code": resp.status_code,
                                    "success": True,
                                },
                            ),
                        )
            except Exception as e:
                last_error = str(e)
                continue

        # 所有接口都失败
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"连接失败: {last_error}",
                data={"base_url": base_url, "success": False},
            ),
        )

    except Exception as e:
        logger.exception("test_external_kb_connection failed")
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=str(e), data=None),
        )
