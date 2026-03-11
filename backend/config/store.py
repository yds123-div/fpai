"""
策略/模板/路由配置与版本管理：从 MySQL config_strategy 表加载。

合规策略、报告模板、对比维度模板、智能体注册信息等；见 compliance_improvements_plan 与 technical_design §4.1。
"""
from __future__ import annotations

import json
import time
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)

# 合规策略 config_key（与 compliance_improvements_plan §1.2 一致）
CONFIG_KEY_COMPLIANCE_POLICY = "compliance_policy"

# 内存缓存：key -> (value, 过期时间戳)；TTL 秒
_CACHE: dict[str, tuple[Any, float]] = {}
_CACHE_TTL_SECONDS = 60


def _now_ts() -> float:
    return time.monotonic()


def _get_cached(key: str) -> Any | None:
    if key not in _CACHE:
        return None
    val, expires = _CACHE[key]
    if _now_ts() >= expires:
        del _CACHE[key]
        return None
    return val


def _set_cached(key: str, value: Any, ttl_seconds: int = _CACHE_TTL_SECONDS) -> None:
    _CACHE[key] = (value, _now_ts() + ttl_seconds)


def clear_config_cache(key: str | None = None) -> None:
    """清除配置缓存；key 为 None 时清空全部。用于测试或强制刷新。"""
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


def get_config(config_key: str, use_cache: bool = True) -> dict[str, Any] | None:
    """
    从 config_strategy 表按 config_key 读取一条，返回 config_value（JSON 解析为 dict）。
    未配置 MySQL、无记录或解析失败时返回 None。
    """
    if not config_key or not mysql_configured():
        return None
    if use_cache:
        cached = _get_cached(config_key)
        if cached is not None:
            return cached
    try:
        with get_connection() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT config_value, version FROM config_strategy WHERE config_key = %s LIMIT 1""",
                    (config_key,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                config_value, version = row[0], row[1]
                if isinstance(config_value, str):
                    data = json.loads(config_value)
                elif isinstance(config_value, dict):
                    data = config_value
                else:
                    return None
                if not isinstance(data, dict):
                    return None
                # 可选：注入表 version 供调用方使用
                data["_version"] = version
                if use_cache:
                    _set_cached(config_key, data)
                return data
    except Exception as e:
        logger.warning("get_config 失败: %s", e, extra={"config_key": config_key})
        return None


def get_compliance_policy(use_cache: bool = True) -> dict[str, Any] | None:
    """
    从 MySQL 读取合规策略（config_key = compliance_policy），返回可构造 CompliancePolicy 的 dict。
    MySQL 未配置或无记录时返回 None；compliance 层可回退到 DEFAULT_POLICY。
    与 compliance_improvements_plan §1.3 一致。
    """
    data = get_config(CONFIG_KEY_COMPLIANCE_POLICY, use_cache=use_cache)
    if data is None:
        return None
    # 返回副本，避免调用方修改影响缓存；去掉内部字段
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    return out
