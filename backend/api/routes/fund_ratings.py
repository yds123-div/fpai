from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import get_auth_context
from pkg.akshare_client import AkShareClient
from pkg.codes import ErrorCode, envelope, message_for

router = APIRouter(prefix="/funds", tags=["funds"])

_client = AkShareClient()


@router.get("/{symbol}/rating")
async def get_fund_rating_info(
    symbol: str,
    _auth=Depends(get_auth_context),
):
    """
    按需获取第三方评级信息（上海证券/招商证券/济安金信）。

    说明：
    - rating_info 默认不在 get_all_data 里拉取，避免拖慢聊天主流程
    - 该接口用于前端按需展示（例如用户展开“评级”区域时触发）
    """
    if not symbol or (not symbol.isdigit()) or len(symbol) != 6:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR,
                message="基金代码格式错误，应为 6 位数字",
                data=None,
            ),
        )

    try:
        # 评级接口偶发很慢，这里也做超时保护
        rating_info = await asyncio.wait_for(_client.get_rating_info(symbol), timeout=6.0)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="评级信息获取超时，请稍后重试",
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

    if not isinstance(rating_info, dict) or not rating_info.get("ok"):
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.BAD_REQUEST,
                message=str((rating_info or {}).get("message") or message_for(ErrorCode.BAD_REQUEST)),
                data=None,
            ),
        )

    return JSONResponse(
        status_code=200,
        content=envelope(
            code=ErrorCode.OK,
            message="ok",
            data={"symbol": symbol, "rating_info": rating_info.get("data") or {}},
        ),
    )

