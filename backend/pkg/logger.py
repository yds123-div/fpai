"""
结构化日志（含 traceId），供各模块复用。

请求头 X-Request-Id 或网关生成的 ID 作为 traceId 贯穿日志与审计；
在中间件中调用 bind_trace_id()，日志格式为结构化字段便于检索。
"""
import logging
import os
from contextvars import ContextVar
from typing import Any

# 请求级 trace_id，由 API 层或中间件设置
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_trace_id() -> str | None:
    """获取当前上下文的 traceId。"""
    return trace_id_ctx.get()


def bind_trace_id(trace_id: str | None) -> None:
    """绑定当前请求的 traceId（通常在中间件中调用）。"""
    trace_id_ctx.set(trace_id)


def clear_trace_id() -> None:
    """清除当前上下文的 traceId。"""
    try:
        trace_id_ctx.set(None)
    except LookupError:
        pass


class TraceIdFilter(logging.Filter):
    """为每条 LogRecord 注入 trace_id，便于结构化输出。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or ""  # type: ignore[attr-defined]
        return True


class TraceIdFormatter(logging.Formatter):
    """带 trace_id 的 Formatter；若 record 无 trace_id（如第三方库日志）则填空，避免 KeyError。"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id() or ""  # type: ignore[attr-defined]
        return super().format(record)


def _structured_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    """合并 trace_id 与调用方 extra，避免静默覆盖。"""
    out: dict[str, Any] = {"trace_id": get_trace_id() or ""}
    if extra:
        out.update(extra)
    return out


def get_logger(name: str) -> logging.Logger:
    """
    返回带 TraceIdFilter 的 logger；若尚未添加则添加一次，避免重复。
    """
    log = logging.getLogger(name)
    if not any(isinstance(f, TraceIdFilter) for f in log.filters):
        log.addFilter(TraceIdFilter())
    return log


# 标记本模块添加的 handler，避免 configure_logging 重复添加
_fpai_handlers_key = "_fpai_configured"


def configure_logging(
    level: str | int | None = None,
    format_string: str | None = None,
    log_file: str | None = None,
) -> None:
    """
    配置根 logger：级别、格式，并同时输出到控制台与可选日志文件。
    - level：未传则从环境变量 LOG_LEVEL 读取，默认 INFO（DEBUG 可看到 auth 等详细日志）。
    - format_string：格式中可使用 %(trace_id)s。
    - log_file：未传则从环境变量 LOG_FILE 读取；若设置则追加 FileHandler，日志同时写入该文件。
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    if format_string is None:
        format_string = (
            "%(asctime)s [%(levelname)s] %(name)s trace_id=%(trace_id)s %(message)s"
        )
    if log_file is None:
        log_file = os.getenv("LOG_FILE", "").strip() or None
    fmt = TraceIdFormatter(format_string)
    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加：仅当未标记时添加 handler
    if getattr(root, _fpai_handlers_key, False):
        return
    # 控制台
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)
    setattr(stream_handler, _fpai_handlers_key, True)
    root.addHandler(stream_handler)
    # 可选：日志文件（与控制台相同级别与格式）；自动创建所在目录
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(fmt)
            setattr(file_handler, _fpai_handlers_key, True)
            root.addHandler(file_handler)
        except OSError as e:
            root.warning("LOG_FILE 无法创建 %s: %s", log_file, e)
    # TraceIdFilter
    if not any(isinstance(f, TraceIdFilter) for f in root.filters):
        root.addFilter(TraceIdFilter())
    setattr(root, _fpai_handlers_key, True)
