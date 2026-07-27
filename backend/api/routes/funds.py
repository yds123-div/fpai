from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.deps import get_auth_context
from pkg.akshare_client import AkShareClient
from pkg.codes import ErrorCode, envelope, message_for
from pkg.fund_formatter import format_nav_chart_from_akshare

router = APIRouter(prefix="/funds", tags=["funds"])

# 复用 client，避免频繁创建导致卡顿
_client = AkShareClient()

# 按 symbol 限制并发：同一基金同时只处理 1 个净值请求
_nav_locks: dict[str, asyncio.Semaphore] = {}

_PERIOD_MAP = {
    "近1月": "1月",
    "近3月": "3月",
    "近1年": "1年",
    "成立以来": "成立来",
}


def _lock_for_symbol(symbol: str) -> asyncio.Semaphore:
    lock = _nav_locks.get(symbol)
    if lock is None:
        lock = asyncio.Semaphore(1)
        _nav_locks[symbol] = lock
    return lock


@router.get("/{symbol}/nav")
async def get_fund_nav_by_period(
    symbol: str,
    period: str = Query(default="近1年"),
    _auth=Depends(get_auth_context),
):
    if period not in _PERIOD_MAP:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"不支持的周期：{period}，仅支持 近1月/近3月/近1年/成立以来",
                data=None,
            ),
        )

    if not symbol or (not symbol.isdigit()) or len(symbol) != 6:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR,
                message="基金代码格式错误，应为 6 位数字",
                data=None,
            ),
        )

    lock = _lock_for_symbol(symbol)
    async with lock:
        try:
            nav_result: dict[str, Any] = await asyncio.wait_for(
                _client.get_nav_data(symbol, period=_PERIOD_MAP[period]),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            try:
                nav_result = await asyncio.wait_for(
                    _client.get_nav_data(symbol, period=_PERIOD_MAP[period]),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                return JSONResponse(
                    status_code=200,
                    content=envelope(
                        code=ErrorCode.SERVICE_UNAVAILABLE,
                        message="净值数据获取超时，请稍后重试",
                        data=None,
                    ),
                )
        except Exception as e:
            return JSONResponse(
                status_code=200,
                content=envelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(e) or message_for(ErrorCode.INTERNAL_ERROR),
                    data=None,
                ),
            )

    if not nav_result.get("ok"):
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.BAD_REQUEST,
                message=nav_result.get("message") or message_for(ErrorCode.BAD_REQUEST),
                data=None,
            ),
        )

    chart = format_nav_chart_from_akshare(nav_result, symbol)
    if not chart or not isinstance(chart.get("data"), dict):
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.BAD_REQUEST,
                message="该周期暂无可展示净值数据",
                data=None,
            ),
        )

    x_axis = chart.get("data", {}).get("xAxis") if isinstance(chart.get("data"), dict) else None
    x_list = x_axis if isinstance(x_axis, list) else []
    start = str(x_list[0]) if x_list else ""
    end = str(x_list[-1]) if x_list else ""
    points = len(x_list)
    return JSONResponse(
        status_code=200,
        content=envelope(
            code=ErrorCode.OK,
            message="ok",
            data={
                "symbol": symbol,
                "period": period,
                "start": start,
                "end": end,
                "points": points,
                "chart": {
                    "id": chart.get("id"),
                    "title": chart.get("title"),
                    "description": chart.get("description"),
                    "data": chart.get("data"),
                    "options": chart.get("options"),
                },
            },
        ),
    )
