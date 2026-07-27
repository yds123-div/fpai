# -*- coding: utf-8 -*-
"""
产品对比 Agent skill 执行入口（占位）。

后续你提供 skill 内容后：
- 在这里加载 prompt、组装 messages
- 选择并调用工具（如数据查询、画像分析、对比维度提取等）
- 返回最终文本
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable


def _extract_symbols(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # 兼容“对比161039和110011这两只基金”这类数字紧贴中文场景
    symbols = re.findall(r"(?<!\d)\d{6}(?!\d)", t)
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _pick_ref_count(question: str) -> int | None:
    q = (question or "").strip()
    if not q:
        return None
    nmap = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}

    m = re.search(r"(?:前|后|这)([一二两三四五1-5])(?:只|个)?", q)
    if m:
        x = m.group(1)
        if x.isdigit():
            return int(x)
        return nmap.get(x)

    m2 = re.search(r"([一二两三四五1-5])(?:只|个)(?:基金)?", q)
    if m2:
        x = m2.group(1)
        if x.isdigit():
            return int(x)
        return nmap.get(x)
    return None


def _resolve_symbols_from_history(question: str, ctx: dict[str, Any], limit: int = 30) -> list[str]:
    """
    当用户未显式给出基金代码时，尝试从会话历史中回填：
    - 优先使用“最近一条含 2+ 代码”的消息（通常是上一轮榜单/对比结果）
    - 支持“前两只/后两只/这两只”等指代表达
    """
    q = (question or "").strip()
    session_id = str((ctx or {}).get("session_id") or "").strip()
    if not session_id:
        return []

    try:
        from orchestrator.session import get_recent_messages

        msgs = get_recent_messages(session_id, limit=limit) or []
    except Exception:
        msgs = []
    if not msgs:
        return []

    # 全局去重序列（按时间正序）
    global_seen: set[str] = set()
    global_symbols: list[str] = []
    for m in reversed(msgs):
        syms = _extract_symbols(str(m.get("content_summary") or ""))
        for s in syms:
            if s not in global_seen:
                global_seen.add(s)
                global_symbols.append(s)

    # 最近“一个消息块”中出现的代码（优先 assistant，且至少 2 只）
    latest_block: list[str] = []
    for m in msgs:  # msgs 为倒序：最新在前
        if str(m.get("role") or "").lower() != "assistant":
            continue
        syms = _extract_symbols(str(m.get("content_summary") or ""))
        if len(syms) >= 2:
            latest_block = syms
            break
    if not latest_block:
        for m in msgs:
            syms = _extract_symbols(str(m.get("content_summary") or ""))
            if len(syms) >= 2:
                latest_block = syms
                break

    base = latest_block or global_symbols
    if not base:
        return []

    cnt = _pick_ref_count(q) or 2
    cnt = max(1, min(cnt, 5))
    if "后" in q:
        return base[-cnt:]
    return base[:cnt]


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    基于 AkShare 的数据获取入口（聚合版）：
    - 从问题中提取最多 5 个 6 位基金代码
    - 聚合四大模块数据：基本信息、业绩表现、资产配置、风险提示

    返回 JSON 字符串（供上层 LLM 作为“供应商数据”输入）。
    若某模块接口不可用，则在模块下返回 {"ok": false, "message": "..."}，避免整体失败。
    """
    q = (question or "").strip()
    uniq = _extract_symbols(q)
    # 未显式给代码时，尝试基于会话历史回填（支持“前两只基金”等表达）
    if len(uniq) < 2:
        from_history = _resolve_symbols_from_history(q, ctx)
        if from_history:
            merged = uniq + [x for x in from_history if x not in uniq]
            uniq = merged
    uniq = uniq[:5]

    if not uniq:
        return json.dumps(
            {
                "ok": False,
                "message": "未识别到可用基金代码（6位数字）。请直接提供代码，或先查询基金后再使用“前两只/后两只”等上下文指代。",
            },
            ensure_ascii=False,
        )

    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "message": "缺少 akshare 依赖，请在后端环境安装：pip install akshare pandas",
                "error": str(e),
                "symbols": uniq,
            },
            ensure_ascii=False,
        )

    def _fn(name: str) -> Callable[..., Any] | None:
        return getattr(ak, name, None)

    def _df_records(df: Any, limit: int = 200) -> list[dict[str, Any]]:
        try:
            if df is None:
                return []
            if hasattr(df, "head") and hasattr(df, "to_dict"):
                return df.head(limit).to_dict(orient="records")  # type: ignore[no-any-return]
        except Exception:
            return []
        return []

    def _module_fail(message: str, **extra: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "message": message}
        out.update(extra)
        return out

    def _module_ok(data: Any) -> dict[str, Any]:
        return {"ok": True, "data": data}

    # --------- 并行获取所有基金数据 ---------
    import asyncio
    import time
    from pkg.metrics import get_metrics_collector
    
    metrics_collector = get_metrics_collector()
    
    async def _fetch_with_timeout(coro, timeout: float = 5.0, default: Any = None) -> Any:
        """带超时的异步调用，避免单个 API 阻塞过久"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            import logging
            logging.warning(f"操作超时（{timeout}s），返回降级数据")
            return default
        except Exception as e:
            import logging
            logging.warning(f"操作失败: {e}")
            return default
    
    async def _fetch_single_fund(sym: str) -> dict[str, Any]:
        """并行获取单只基金的所有数据"""
        fund_obj: dict[str, Any] = {"symbol": sym}
        
        # 定义各个数据获取任务
        async def _fetch_basic_info() -> dict[str, Any]:
            """获取基本信息"""
            api_name = "fund_individual_basic_info_xq"
            fn_basic_xq = _fn(api_name)
            if not callable(fn_basic_xq):
                return _module_fail(f"akshare 未提供 {api_name}")
            
            start_time = time.time()
            try:
                df = await asyncio.to_thread(fn_basic_xq, symbol=sym)
                duration = time.time() - start_time
                metrics_collector.record_api_success(api_name, duration)
                return _module_ok(_df_records(df, limit=200))
            except Exception as e:
                duration = time.time() - start_time
                if duration >= 5.0:
                    metrics_collector.record_api_timeout(api_name)
                else:
                    metrics_collector.record_api_error(api_name)
                return _module_fail(f"{api_name} 失败: {e}")
        
        async def _fetch_performance() -> dict[str, Any]:
            """获取业绩表现（业绩概要 + 盈亏概率）- 并行获取"""
            
            async def _get_achievement() -> dict[str, Any]:
                api_name = "fund_individual_achievement_xq"
                fn_ach = _fn(api_name)
                if not callable(fn_ach):
                    return _module_fail(f"akshare 未提供 {api_name}")
                
                start_time = time.time()
                try:
                    df = await asyncio.to_thread(fn_ach, symbol=sym)
                    duration = time.time() - start_time
                    metrics_collector.record_api_success(api_name, duration)
                    return _module_ok(_df_records(df, limit=200))
                except Exception as e:
                    duration = time.time() - start_time
                    if duration >= 5.0:
                        metrics_collector.record_api_timeout(api_name)
                    else:
                        metrics_collector.record_api_error(api_name)
                    return _module_fail(f"{api_name} 失败: {e}")
            
            async def _get_profit_probability() -> dict[str, Any]:
                api_name = "fund_individual_profit_probability_xq"
                fn_prob = _fn(api_name)
                if not callable(fn_prob):
                    return _module_fail(f"akshare 未提供 {api_name}")
                
                start_time = time.time()
                try:
                    df = await asyncio.to_thread(fn_prob, symbol=sym)
                    duration = time.time() - start_time
                    metrics_collector.record_api_success(api_name, duration)
                    return _module_ok(_df_records(df, limit=20))
                except Exception as e:
                    duration = time.time() - start_time
                    if duration >= 5.0:
                        metrics_collector.record_api_timeout(api_name)
                    else:
                        metrics_collector.record_api_error(api_name)
                    return _module_fail(f"{api_name} 失败: {e}")
            
            # 并行获取两个子模块
            achievement, profit_probability = await asyncio.gather(
                _get_achievement(),
                _get_profit_probability(),
                return_exceptions=True,
            )
            
            perf: dict[str, Any] = {}
            perf["achievement"] = achievement if not isinstance(achievement, Exception) else _module_fail(f"获取业绩异常: {achievement}")
            perf["profit_probability"] = profit_probability if not isinstance(profit_probability, Exception) else _module_fail(f"获取盈亏概率异常: {profit_probability}")
            
            return perf
        
        async def _fetch_asset_allocation() -> dict[str, Any]:
            """获取资产配置/持仓"""
            api_name = "fund_portfolio_hold_em"
            fn_hold = _fn(api_name)
            if not callable(fn_hold):
                return _module_fail(f"akshare 未提供 {api_name}")
            
            start_time = time.time()
            try:
                from datetime import datetime
                y = datetime.now().year
                rows = None
                last_err = None
                
                # 尝试当年，不行就往前试两年
                for yy in (y, y - 1, y - 2):
                    try:
                        df = await asyncio.to_thread(fn_hold, symbol=sym, date=str(yy))
                        rows = _df_records(df, limit=15)
                        if rows:
                            break
                    except Exception as e:
                        last_err = e
                        continue
                
                duration = time.time() - start_time
                if rows:
                    metrics_collector.record_api_success(api_name, duration)
                    return _module_ok({"top_holdings": rows[:10]})
                else:
                    if duration >= 5.0:
                        metrics_collector.record_api_timeout(api_name)
                    else:
                        metrics_collector.record_api_error(api_name)
                    return _module_fail(f"{api_name} 无可用数据: {last_err}")
            except Exception as e:
                duration = time.time() - start_time
                if duration >= 5.0:
                    metrics_collector.record_api_timeout(api_name)
                else:
                    metrics_collector.record_api_error(api_name)
                return _module_fail(f"{api_name} 失败: {e}")
        
        # 并行获取三个模块的数据（每个模块最多5秒超时）
        module_start = time.time()
        basic_info, performance, asset_allocation = await asyncio.gather(
            _fetch_with_timeout(_fetch_basic_info(), timeout=5.0, default=_module_fail("获取基本信息超时")),
            _fetch_with_timeout(_fetch_performance(), timeout=5.0, default={"achievement": _module_fail("获取业绩超时")}),
            _fetch_with_timeout(_fetch_asset_allocation(), timeout=5.0, default=_module_fail("获取资产配置超时")),
            return_exceptions=True,
        )
        module_duration = time.time() - module_start
        
        # 记录各模块耗时
        metrics_collector.record_module_duration(f"fetch_basic_info_{sym}", module_duration)
        metrics_collector.record_module_duration(f"fetch_performance_{sym}", module_duration)
        metrics_collector.record_module_duration(f"fetch_asset_allocation_{sym}", module_duration)
        
        # 处理异常情况
        if isinstance(basic_info, Exception):
            fund_obj["basic_info"] = _module_fail(f"获取基本信息异常: {basic_info}")
        else:
            fund_obj["basic_info"] = basic_info
        
        if isinstance(performance, Exception):
            fund_obj["performance"] = {"achievement": _module_fail(f"获取业绩异常: {performance}")}
        else:
            fund_obj["performance"] = performance
        
        if isinstance(asset_allocation, Exception):
            fund_obj["asset_allocation"] = _module_fail(f"获取资产配置异常: {asset_allocation}")
        else:
            fund_obj["asset_allocation"] = asset_allocation
        
        # 风险提示：优先使用雪球的盈亏概率
        if isinstance(performance, dict):
            fund_obj["risk"] = performance.get("profit_probability") or _module_fail("未获取到风险相关数据")
        else:
            fund_obj["risk"] = _module_fail("未获取到风险相关数据")
        
        return fund_obj
    
    # 并行获取所有基金的数据
    funds = await asyncio.gather(*[_fetch_single_fund(sym) for sym in uniq])

    # 多基金对比：以业绩概要为主（逐基金已含），这里保留占位
    compare: dict[str, Any] = _module_ok({"mode": "per_fund_achievement", "count": len(uniq)})

    return json.dumps(
        {
            "ok": True,
            "symbols": uniq,
            "funds": funds,
            "compare": compare,
            "note": "字段/接口因 AkShare 版本与数据源变化可能不稳定；模块级降级以 ok=false 表示。",
        },
        ensure_ascii=False,
    )

