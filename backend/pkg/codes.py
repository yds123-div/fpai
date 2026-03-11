"""
统一错误码枚举，与 API 契约一致。

约定：0 成功；4xx 客户端（参数/鉴权/限流）；5xx 服务端；
业务子码与合规子码可在本模块扩展或由 decisions.md 维护。
"""
from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """HTTP 语义错误码，与统一响应 envelope 的 code 字段对应。"""

    OK = 200
    # 4xx 客户端
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    RATE_LIMITED = 429
    # 5xx 服务端
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503
    # 合规子码（4xx 段）
    COMPLIANCE_REJECT = 40301
    COMPLIANCE_REVIEW = 40302
    # 业务子码：参数校验、会话、产品等（与前端约定）
    VALIDATION_ERROR = 40001
    SESSION_NOT_FOUND = 40401
    PRODUCT_NOT_FOUND = 40402
    ANSWER_NOT_FOUND = 40403


# 默认可展示文案，便于 API 直接返回 message
DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.OK: "ok",
    ErrorCode.BAD_REQUEST: "请求参数错误",
    ErrorCode.UNAUTHORIZED: "未授权",
    ErrorCode.FORBIDDEN: "禁止访问",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.RATE_LIMITED: "请求过于频繁，请稍后再试",
    ErrorCode.INTERNAL_ERROR: "服务内部错误",
    ErrorCode.SERVICE_UNAVAILABLE: "服务暂不可用",
    ErrorCode.COMPLIANCE_REJECT: "内容未通过合规审查",
    ErrorCode.COMPLIANCE_REVIEW: "内容需人工复核",
    ErrorCode.VALIDATION_ERROR: "参数校验失败",
    ErrorCode.SESSION_NOT_FOUND: "会话不存在",
    ErrorCode.PRODUCT_NOT_FOUND: "产品不存在",
    ErrorCode.ANSWER_NOT_FOUND: "答案或证据不存在",
}


def message_for(code: ErrorCode, default: str | None = None) -> str:
    """返回错误码对应的可展示文案。"""
    return DEFAULT_MESSAGES.get(code, default or "未知错误")


def is_client_error(code: ErrorCode) -> bool:
    """是否为客户端错误（4xx 段）。"""
    return 400 <= code < 500


def is_server_error(code: ErrorCode) -> bool:
    """是否为服务端错误（5xx 段）。"""
    return code >= 500


def envelope(
    code: ErrorCode = ErrorCode.OK,
    message: str | None = None,
    data: Any = None,
) -> dict[str, Any]:
    """构造统一响应 envelope。"""
    return {
        "code": int(code),
        "message": message or message_for(code),
        "data": data,
    }
