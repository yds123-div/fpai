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


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    基于 AkShare 的数据获取入口（聚合版）：
    - 从问题中提取最多 5 个 6 位基金代码
    - 聚合四大模块数据：基本信息、业绩表现、资产配置、风险提示

    返回 JSON 字符串（供上层 LLM 作为“供应商数据”输入）。
    若某模块接口不可用，则在模块下返回 {"ok": false, "message": "..."}，避免整体失败。
    """
    q = (question or "").strip()
    # 兼容 “对比161039和110011这两只基金” 这类数字紧贴中文的场景；
    # 使用数字边界而不是 \b（\b 在部分 unicode 场景下可能失效）
    symbols = re.findall(r"(?<!\d)\d{6}(?!\d)", q)
    # 去重并保序
    seen = set()
    uniq: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    uniq = uniq[:5]

    if not uniq:
        return json.dumps({"ok": False, "message": "未从问题中识别到基金代码（6位数字）"}, ensure_ascii=False)

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

    # --------- 逐基金聚合（以雪球 XQ 单基金接口为主，辅以 EM 持仓） ---------
    funds: list[dict[str, Any]] = []
    for sym in uniq:
        fund_obj: dict[str, Any] = {"symbol": sym}

        # 基本信息（雪球）
        fn_basic_xq = _fn("fund_individual_basic_info_xq")
        if callable(fn_basic_xq):
            try:
                df = fn_basic_xq(symbol=sym)  # type: ignore[misc]
                fund_obj["basic_info"] = _module_ok(_df_records(df, limit=200))
            except Exception as e:
                fund_obj["basic_info"] = _module_fail(f"fund_individual_basic_info_xq 失败: {e}")
        else:
            fund_obj["basic_info"] = _module_fail("akshare 未提供 fund_individual_basic_info_xq")

        # 业绩表现（雪球：业绩概要 + 盈亏概率）
        perf: dict[str, Any] = {}
        fn_ach = _fn("fund_individual_achievement_xq")
        if callable(fn_ach):
            try:
                df = fn_ach(symbol=sym)  # type: ignore[misc]
                perf["achievement"] = _module_ok(_df_records(df, limit=200))
            except Exception as e:
                perf["achievement"] = _module_fail(f"fund_individual_achievement_xq 失败: {e}")
        else:
            perf["achievement"] = _module_fail("akshare 未提供 fund_individual_achievement_xq")

        fn_prob = _fn("fund_individual_profit_probability_xq")
        if callable(fn_prob):
            try:
                df = fn_prob(symbol=sym)  # type: ignore[misc]
                perf["profit_probability"] = _module_ok(_df_records(df, limit=20))
            except Exception as e:
                perf["profit_probability"] = _module_fail(f"fund_individual_profit_probability_xq 失败: {e}")
        else:
            perf["profit_probability"] = _module_fail("akshare 未提供 fund_individual_profit_probability_xq")
        fund_obj["performance"] = perf

        # 资产配置/持仓：东方财富 持仓明细（按年度季度）
        fn_hold = _fn("fund_portfolio_hold_em")
        if callable(fn_hold):
            try:
                # 尝试当年，不行就往前试两年
                from datetime import datetime

                y = datetime.now().year
                rows = None
                last_err = None
                for yy in (y, y - 1, y - 2):
                    try:
                        df = fn_hold(symbol=sym, date=str(yy))  # type: ignore[misc]
                        rows = _df_records(df, limit=15)
                        if rows:
                            break
                    except Exception as e:
                        last_err = e
                        continue
                if rows:
                    # 只保留前 10 条，降低 prompt 体积
                    fund_obj["asset_allocation"] = _module_ok({"top_holdings": rows[:10]})
                else:
                    fund_obj["asset_allocation"] = _module_fail(f"fund_portfolio_hold_em 无可用数据: {last_err}")
            except Exception as e:
                fund_obj["asset_allocation"] = _module_fail(f"fund_portfolio_hold_em 失败: {e}")
        else:
            fund_obj["asset_allocation"] = _module_fail("akshare 未提供 fund_portfolio_hold_em")

        # 风险提示：优先使用雪球的盈亏概率（作为风险分布信息）；其它指标后续可扩展
        fund_obj["risk"] = perf.get("profit_probability") or _module_fail("未获取到风险相关数据")
        funds.append(fund_obj)

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

