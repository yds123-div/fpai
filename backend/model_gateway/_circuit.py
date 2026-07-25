"""简单进程内熔断器：按 key 统计连续失败次数，超过阈值后在一段时间内直接失败。

模块级函数（is_open/record_failure/record_success/reset）是二态熔断，
供 embedding.py / reranker.py 按 key 复用。

CircuitBreaker 类是三态熔断（CLOSED/OPEN/HALF_OPEN），供 GatewayChatModel
（T4 #22）以类级 key="llm" 持有；验收要求开/半开/关转移单测。
"""
import time
from enum import Enum
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


# ---------------------------------------------------------------------------
# 三态熔断器（T4 #22）：CLOSED / OPEN / HALF_OPEN
# ---------------------------------------------------------------------------
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """三态进程内熔断器。

    状态转移：
      CLOSED    --失败达阈值-->  OPEN
      OPEN      --冷却到期-->    HALF_OPEN（放行一个试探请求）
      HALF_OPEN --试探成功-->    CLOSED
      HALF_OPEN --试探失败-->    OPEN（重置冷却）

    线程安全（per-instance Lock）。clock 可注入以便单测控制时间推进。

    与模块级二态函数的差异：模块级函数按 key 共享全局字典、只有开/关两态；
    CircuitBreaker 是独立实例对象、含 HALF_OPEN 试探态，供 GatewayChatModel
    以类级 key="llm" 持有（G1 决策：熔断 key 上移到类）。
    """

    def __init__(
        self,
        key: str,
        threshold: int = 5,
        recovery_seconds: float = 60.0,
        *,
        clock=time.monotonic,
    ) -> None:
        self.key = key
        self._threshold = threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._failures = 0
        self._opened_until = 0.0
        self._half_open_trial = False  # HALF_OPEN 是否已放行试探请求

    @property
    def state(self) -> CircuitState:
        """当前状态（只读，不触发转移）。"""
        with self._lock:
            return self._state

    def is_open(self) -> bool:
        """是否应拒绝请求。

        - OPEN 且未过冷却 -> True（拒绝）。
        - OPEN 过冷却 -> 转 HALF_OPEN 并放行首个试探请求（返回 False）。
        - HALF_OPEN 且已放行试探 -> True（拒绝后续，等试探决断）。
        - CLOSED -> False。
        """
        now = self._clock()
        with self._lock:
            if self._state is CircuitState.OPEN:
                if now >= self._opened_until:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_trial = False
                else:
                    return True
            if self._state is CircuitState.HALF_OPEN:
                if not self._half_open_trial:
                    self._half_open_trial = True
                    return False  # 放行试探
                return True
            return False  # CLOSED

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                # 试探成功 -> 恢复
                self._state = CircuitState.CLOSED
                self._failures = 0
                self._half_open_trial = False
            elif self._state is CircuitState.CLOSED:
                self._failures = 0
            # OPEN 时不应被调用（is_open 会先拒绝）；防御性忽略

    def record_failure(self) -> None:
        now = self._clock()
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                # 试探失败 -> 重新打开
                self._state = CircuitState.OPEN
                self._opened_until = now + self._recovery_seconds
                self._half_open_trial = False
            elif self._state is CircuitState.OPEN:
                # 已打开：刷新冷却窗口
                self._opened_until = now + self._recovery_seconds
            else:  # CLOSED
                self._failures += 1
                if self._failures >= self._threshold:
                    self._state = CircuitState.OPEN
                    self._opened_until = now + self._recovery_seconds

    def reset(self) -> None:
        """测试用：回到 CLOSED。"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_until = 0.0
            self._half_open_trial = False
