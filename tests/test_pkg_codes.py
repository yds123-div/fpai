"""pkg.codes 单元测试：错误码与 envelope."""
import pytest

from pkg.codes import (
    ErrorCode,
    envelope,
    is_client_error,
    is_server_error,
    message_for,
)


def test_message_for_ok():
    assert message_for(ErrorCode.OK) == "ok"


def test_message_for_and_default():
    assert message_for(ErrorCode.INTERNAL_ERROR) == "服务内部错误"
    # 已知码优先，default 仅在未命中时使用
    assert message_for(ErrorCode.OK, default="自定义") == "ok"


def test_is_client_error():
    assert is_client_error(ErrorCode.BAD_REQUEST) is True
    assert is_client_error(ErrorCode.RATE_LIMITED) is True
    assert is_client_error(ErrorCode.INTERNAL_ERROR) is False


def test_is_server_error():
    assert is_server_error(ErrorCode.INTERNAL_ERROR) is True
    assert is_server_error(ErrorCode.SERVICE_UNAVAILABLE) is True
    assert is_server_error(ErrorCode.BAD_REQUEST) is False


def test_envelope_success():
    r = envelope(ErrorCode.OK, data={"x": 1})
    assert r["code"] == 0
    assert r["message"] == "ok"
    assert r["data"] == {"x": 1}


def test_envelope_error_custom_message():
    r = envelope(ErrorCode.BAD_REQUEST, message="参数 id 无效")
    assert r["code"] == 400
    assert r["message"] == "参数 id 无效"
    assert r["data"] is None
