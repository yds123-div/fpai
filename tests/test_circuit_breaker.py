# -*- coding: utf-8 -*-
"""T4 #22：GatewayChatModel 的三态熔断器单测。

验收：熔断状态机单测（开/半开/关转移，key="llm" 类级）通过。

CircuitBreaker 是纯 Python 三态熔断器（CLOSED/OPEN/HALF_OPEN），
被 GatewayChatModel 以类级 key="llm" 持有。本文件独立测状态转移，
不依赖 AgentScope / 网络模型。

运行：cd backend && python -m pytest -c pyproject.toml ../tests/test_circuit_breaker.py -v
"""
from __future__ import annotations

import threading

import pytest

from model_gateway._circuit import CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# 测试用可控时钟：让状态转移的时间推进可断言
# ---------------------------------------------------------------------------
class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# 初始状态：CLOSED
# ---------------------------------------------------------------------------
def test_initial_state_is_closed() -> None:
    cb = CircuitBreaker(key="llm", threshold=3, recovery_seconds=60.0)
    assert cb.state is CircuitState.CLOSED
    assert cb.is_open() is False


# ---------------------------------------------------------------------------
# CLOSED -> OPEN：连续失败达阈值
# ---------------------------------------------------------------------------
def test_threshold_failures_open_circuit() -> None:
    cb = CircuitBreaker(key="llm", threshold=3, recovery_seconds=60.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED  # 未达阈值仍关
    cb.record_failure()  # 第 3 次 -> OPEN
    assert cb.state is CircuitState.OPEN
    assert cb.is_open() is True


def test_below_threshold_stays_closed() -> None:
    cb = CircuitBreaker(key="llm", threshold=5, recovery_seconds=60.0)
    for _ in range(4):
        cb.record_failure()
    assert cb.state is CircuitState.CLOSED
    assert cb.is_open() is False


# ---------------------------------------------------------------------------
# 成功重置失败计数（CLOSED 内）
# ---------------------------------------------------------------------------
def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker(key="llm", threshold=3, recovery_seconds=60.0)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # 清零
    # 再失败 2 次不应打开（阈值 3，当前 2）
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# OPEN -> HALF_OPEN：冷却到期
# ---------------------------------------------------------------------------
def test_open_transitions_to_half_open_after_recovery() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(
        key="llm", threshold=2, recovery_seconds=60.0, clock=clock
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN

    clock.advance(60.0)  # 冷却到期
    # is_open() 触发 OPEN -> HALF_OPEN 转移，并放行试探请求
    assert cb.is_open() is False
    assert cb.state is CircuitState.HALF_OPEN


def test_open_rejects_before_recovery() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(
        key="llm", threshold=2, recovery_seconds=60.0, clock=clock
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(59.9)  # 未到期
    assert cb.is_open() is True
    assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN：只放行一个试探请求
# ---------------------------------------------------------------------------
def test_half_open_allows_only_one_trial() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(
        key="llm", threshold=2, recovery_seconds=60.0, clock=clock
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(60.0)

    assert cb.is_open() is False  # 第 1 个试探请求放行
    assert cb.state is CircuitState.HALF_OPEN
    # 试探未决前，后续请求被拒
    assert cb.is_open() is True
    assert cb.is_open() is True


# ---------------------------------------------------------------------------
# HALF_OPEN 试探成功 -> CLOSED
# ---------------------------------------------------------------------------
def test_half_open_trial_success_closes_circuit() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(
        key="llm", threshold=2, recovery_seconds=60.0, clock=clock
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(60.0)
    cb.is_open()  # 进入 HALF_OPEN + 占用试探槽
    cb.record_success()  # 试探成功

    assert cb.state is CircuitState.CLOSED
    assert cb.is_open() is False
    # 失败计数已清零：再失败 1 次不应打开（阈值 2）
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# HALF_OPEN 试探失败 -> 重新 OPEN
# ---------------------------------------------------------------------------
def test_half_open_trial_failure_reopens_circuit() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(
        key="llm", threshold=2, recovery_seconds=60.0, clock=clock
    )
    cb.record_failure()
    cb.record_failure()
    clock.advance(60.0)
    cb.is_open()  # 进入 HALF_OPEN + 占用试探槽
    cb.record_failure()  # 试探失败

    assert cb.state is CircuitState.OPEN
    assert cb.is_open() is True


# ---------------------------------------------------------------------------
# 线程安全：并发 record_failure 不会破坏状态
# ---------------------------------------------------------------------------
def test_concurrent_failures_are_thread_safe() -> None:
    cb = CircuitBreaker(key="llm", threshold=100, recovery_seconds=60.0)

    def _hammer() -> None:
        for _ in range(500):
            cb.record_failure()

    threads = [threading.Thread(target=_hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 4000 次失败远超阈值 100 -> 必然 OPEN
    assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# 不同 key 隔离
# ---------------------------------------------------------------------------
def test_different_keys_are_isolated() -> None:
    a = CircuitBreaker(key="llm", threshold=2, recovery_seconds=60.0)
    b = CircuitBreaker(key="embedding", threshold=2, recovery_seconds=60.0)
    a.record_failure()
    a.record_failure()
    assert a.state is CircuitState.OPEN
    assert b.state is CircuitState.CLOSED  # 互不影响


# ---------------------------------------------------------------------------
# reset() 测试辅助
# ---------------------------------------------------------------------------
def test_reset_restores_closed() -> None:
    cb = CircuitBreaker(key="llm", threshold=2, recovery_seconds=60.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    cb.reset()
    assert cb.state is CircuitState.CLOSED
    assert cb.is_open() is False
