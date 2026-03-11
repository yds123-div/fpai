"""pkg.logger 单元测试：traceId 绑定与日志输出."""
import logging

import pytest

from pkg.logger import (
    TraceIdFilter,
    bind_trace_id,
    clear_trace_id,
    get_logger,
    get_trace_id,
)


def test_get_trace_id_default_none():
    clear_trace_id()
    assert get_trace_id() is None


def test_bind_and_get_trace_id():
    bind_trace_id("req-123")
    try:
        assert get_trace_id() == "req-123"
    finally:
        clear_trace_id()


def test_trace_id_filter_injects_into_record():
    clear_trace_id()
    f = TraceIdFilter()
    record = logging.LogRecord("n", logging.INFO, "", 0, "msg", (), None)
    assert not hasattr(record, "trace_id")
    f.filter(record)
    assert record.trace_id == ""
    bind_trace_id("t1")
    try:
        f.filter(record)
        assert record.trace_id == "t1"
    finally:
        clear_trace_id()


def test_get_logger_returns_logger_with_filter():
    log = get_logger(__name__)
    assert isinstance(log, logging.Logger)
    assert any(isinstance(x, TraceIdFilter) for x in log.filters)
