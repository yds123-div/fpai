"""简单进程内熔断器，按机构/数据源 key 统计失败，供统一层调用适配器前检查。"""
import os
import time
from threading import Lock

_lock = Lock()
_failures: dict[str, list[float]] = {}
_opened_until: dict[str, float] = {}

DEFAULT_THRESHOLD = int(os.getenv("DATA_ACCESS_CIRCUIT_THRESHOLD", "5"))
DEFAULT_WINDOW_SECONDS = float(os.getenv("DATA_ACCESS_CIRCUIT_WINDOW_SECONDS", "60"))


def _key(org_id: str) -> str:
    return f"data_access:{org_id}"


def record_failure(org_id: str, threshold: int | None = None, window_seconds: float | None = None) -> None:
    threshold = threshold or DEFAULT_THRESHOLD
    window_seconds = window_seconds or DEFAULT_WINDOW_SECONDS
    now = time.monotonic()
    k = _key(org_id)
    with _lock:
        if k not in _failures:
            _failures[k] = []
        _failures[k].append(now)
        cutoff = now - window_seconds
        _failures[k] = [t for t in _failures[k] if t > cutoff]
        if len(_failures[k]) >= threshold:
            _opened_until[k] = now + window_seconds


def record_success(org_id: str) -> None:
    with _lock:
        _failures.pop(_key(org_id), None)


def is_open(org_id: str) -> bool:
    now = time.monotonic()
    with _lock:
        until = _opened_until.get(_key(org_id), 0)
        if now >= until:
            _opened_until.pop(_key(org_id), None)
            _failures.pop(_key(org_id), None)
            return False
        return True


def reset(org_id: str | None = None) -> None:
    with _lock:
        if org_id is None:
            _failures.clear()
            _opened_until.clear()
        else:
            k = _key(org_id)
            _failures.pop(k, None)
            _opened_until.pop(k, None)
