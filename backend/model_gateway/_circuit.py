"""简单进程内熔断器：按 key 统计连续失败次数，超过阈值后在一段时间内直接失败。"""
import time
from threading import Lock

_lock = Lock()
_failures: dict[str, list[float]] = {}
_opened_until: dict[str, float] = {}


def record_failure(key: str, threshold: int, window_seconds: float) -> None:
    now = time.monotonic()
    with _lock:
        if key not in _failures:
            _failures[key] = []
        _failures[key].append(now)
        # 只保留 window 内的
        cutoff = now - window_seconds
        _failures[key] = [t for t in _failures[key] if t > cutoff]
        if len(_failures[key]) >= threshold:
            _opened_until[key] = now + window_seconds


def record_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def is_open(key: str) -> bool:
    """熔断是否打开（应拒绝请求）。"""
    now = time.monotonic()
    with _lock:
        until = _opened_until.get(key, 0)
        if now >= until:
            _opened_until.pop(key, None)
            _failures.pop(key, None)
            return False
        return True


def reset(key: str | None = None) -> None:
    """测试用：重置熔断状态。"""
    with _lock:
        if key is None:
            _failures.clear()
            _opened_until.clear()
        else:
            _failures.pop(key, None)
            _opened_until.pop(key, None)
