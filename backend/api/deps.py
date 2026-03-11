# -*- coding: utf-8 -*-
"""
API 依赖：鉴权后从 request.state 读取 user_id / role / product_pool_ids，供业务路由注入。

T028：鉴权由中间件完成，此处仅提供便捷依赖；未认证请求已在中间件返回 401 envelope。
"""
from __future__ import annotations

from fastapi import Request


def get_current_user_id(request: Request) -> str:
    """
    从 request.state 读取当前用户 ID（鉴权中间件已注入）。
    仅用于已受鉴权保护的路径；未认证时由中间件直接返回，不会执行到依赖。
    """
    return getattr(request.state, "user_id", None) or ""


def get_auth_context(request: Request) -> "AuthContext":
    """返回当前请求的鉴权上下文（user_id、role、product_pool_ids）。"""
    return AuthContext(
        user_id=getattr(request.state, "user_id", None) or "",
        role=getattr(request.state, "role", None),
        product_pool_ids=getattr(request.state, "product_pool_ids", None) or [],
    )


class AuthContext:
    """鉴权上下文：user_id、role、product_pool_ids（由鉴权中间件注入）。"""

    __slots__ = ("user_id", "role", "product_pool_ids")

    def __init__(self, user_id: str, role: str | None, product_pool_ids: list):
        self.user_id = user_id
        self.role = role
        self.product_pool_ids = product_pool_ids


