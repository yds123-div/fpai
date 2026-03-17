# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import re
from typing import Any, Callable


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        if isinstance(x, (int, float)):
            if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
                return None
            return float(x)
        s = str(x).strip()
        if not s or s in ("nan", "NaN", "None"):
            return None
        if s.endswith("%"):
            return float(s[:-1])
        return float(s)
    except Exception:
        return None


def _pick_horizon_key(q: str) -> str:
    """
    将用户“近期/近1月/近一年/今年来/成立来”等表述映射为内部 horizon key。
    后续再映射到 AkShare 开放式基金排行（按列序号）字段。
    """
    t = (q or "").strip()
    if any(k in t for k in ("近一周", "近1周", "近7天", "一周", "周")):
        return "week"
    if any(k in t for k in ("近一月", "近1月", "近30天", "一月", "1个月", "月")):
        return "month"
    if any(k in t for k in ("近三月", "近3月", "3个月", "三月")):
        return "m3"
    if any(k in t for k in ("近半年", "近6月", "6个月", "半年")):
        return "m6"
    if any(k in t for k in ("近一年", "近1年", "1年", "一年")):
        return "y1"
    if any(k in t for k in ("近两年", "近2年", "2年", "两年")):
        return "y2"
    if any(k in t for k in ("近三年", "近3年", "3年", "三年")):
        return "y3"
    if "今年" in t:
        return "this_year"
    if any(k in t for k in ("成立来", "成立以来", "成立至今")):
        return "since_est"
    # 默认“近期”按近 1 月
    return "month"


def _need_low_risk(q: str) -> bool:
    t = (q or "").strip()
    return any(k in t for k in ("低风险", "风险低", "稳健", "回撤小", "波动小", "稳", "保守"))


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    产品查询 skill：
    - 若问题中包含基金代码：复用 product_compare 聚合数据（单/多基金）
    - 否则：返回“开放式基金排行 TopN（默认 5） + 每只基金的盈亏概率概览（稳健性参考）”

    返回 JSON 字符串（供上层 LLM 使用）。
    """
    q = (question or "").strip()
    symbols = re.findall(r"(?<!\d)\d{6}(?!\d)", q)
    uniq_symbols = list(dict.fromkeys(symbols))[:5]

    # 1) 有基金代码：复用现有聚合取数
    if uniq_symbols:
        try:
            from agents.skills.product_compare.runtime import run as run_compare_skill  # type: ignore

            s = await run_compare_skill(q, ctx)
            obj = json.loads(s) if isinstance(s, str) else s
            if isinstance(obj, dict):
                obj.setdefault("mode", "symbols")
            return json.dumps(obj, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "mode": "symbols", "message": f"复用 product_compare skill 失败: {e}", "symbols": uniq_symbols},
                ensure_ascii=False,
            )

    # 2) 无基金代码：走榜单/筛选
    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "mode": "rank",
                "message": "缺少 akshare 依赖，请在后端环境安装：pip install akshare pandas",
                "error": str(e),
            },
            ensure_ascii=False,
        )

    horizon = _pick_horizon_key(q)
    want_low_risk = _need_low_risk(q)

    # fund_open_fund_rank_em 列顺序（AkShare 当前版本常见）：
    # 0 排名 1 代码 2 名称 3 日期 4 单位净值 5 累计净值 6 日增长率
    # 7 近1周 8 近1月 9 近3月 10 近6月 11 近1年 12 近2年 13 近3年
    # 14 今年来 15 成立来 16 自定义 17 手续费
    horizon_col_index = {
        "week": 7,
        "month": 8,
        "m3": 9,
        "m6": 10,
        "y1": 11,
        "y2": 12,
        "y3": 13,
        "this_year": 14,
        "since_est": 15,
    }.get(horizon, 8)

    def _df_records(df: Any, limit: int = 200) -> list[dict[str, Any]]:
        try:
            if df is None:
                return []
            if hasattr(df, "head") and hasattr(df, "to_dict"):
                return df.head(limit).to_dict(orient="records")  # type: ignore[no-any-return]
        except Exception:
            return []
        return []

    def _safe_call(fn: Callable[..., Any], **kwargs: Any) -> tuple[bool, Any]:
        try:
            return True, fn(**kwargs)
        except Exception as e:
            return False, str(e)

    ok_rank, df_or_err = _safe_call(ak.fund_open_fund_rank_em, symbol="全部")  # type: ignore[misc]
    if not ok_rank:
        return json.dumps(
            {"ok": False, "mode": "rank", "message": f"fund_open_fund_rank_em 失败: {df_or_err}"},
            ensure_ascii=False,
        )

    df = df_or_err
    # 候选集：只取前 2000 行，避免 prompt 过大与后续逐只补充调用过慢
    try:
        if hasattr(df, "head"):
            df = df.head(2000)
    except Exception:
        pass

    items: list[dict[str, Any]] = []
    try:
        values = getattr(df, "values", None)
        if values is None:
            raise ValueError("rank df 无 values")
        for row in values:
            try:
                code = str(row[1]).strip()
                name = str(row[2]).strip()
                date = str(row[3]).strip()
                horizon_ret = _to_float(row[horizon_col_index])
                day_ret = _to_float(row[6])
                if not code or code == "nan" or code == "None":
                    continue
                items.append(
                    {
                        "symbol": code,
                        "name": name,
                        "date": date,
                        "return_day_pct": day_ret,
                        "return_horizon_pct": horizon_ret,
                    }
                )
            except Exception:
                continue
    except Exception as e:
        return json.dumps(
            {"ok": False, "mode": "rank", "message": f"解析 fund_open_fund_rank_em 返回失败: {e}"},
            ensure_ascii=False,
        )

    # 先按“horizon 收益”粗排，取一小段候选再做“稳健性”补充与重排（避免逐只调用过慢）
    items = [x for x in items if x.get("return_horizon_pct") is not None]
    items.sort(key=lambda x: float(x.get("return_horizon_pct") or -10_000), reverse=True)
    candidates = items[:10]

    # 补充稳健性：雪球盈亏概率（win_rate + avg_return）
    fn_prob = getattr(ak, "fund_individual_profit_probability_xq", None)
    if callable(fn_prob) and candidates:
        import asyncio

        sem = asyncio.Semaphore(5)  # 限制并发，避免把数据源打爆

        async def _fetch_prob(sym: str) -> dict[str, Any]:
            async with sem:
                try:
                    # akshare 接口为同步函数，放入线程；并设置超时，避免单只基金卡死拖慢整体
                    df_prob = await asyncio.wait_for(asyncio.to_thread(fn_prob, symbol=sym), timeout=4.0)  # type: ignore[misc]
                except asyncio.TimeoutError:
                    return {"ok": False, "message": "fund_individual_profit_probability_xq 超时"}
                except Exception as e:
                    return {"ok": False, "message": f"fund_individual_profit_probability_xq 失败: {e}"}

                rows = _df_records(df_prob, limit=20)
                summary: dict[str, Any] = {"ok": True, "rows": rows}
                try:
                    if rows:
                        first = rows[0]
                        keys = list(first.keys())
                        if len(keys) >= 3:
                            summary["sample"] = {
                                "period": first.get(keys[0]),
                                "win_rate": _to_float(first.get(keys[1])),
                                "avg_return": _to_float(first.get(keys[2])),
                            }
                except Exception:
                    pass
                return summary

        probs = await asyncio.gather(*[_fetch_prob(it["symbol"]) for it in candidates], return_exceptions=False)
        for it, st in zip(candidates, probs, strict=False):
            it["stability"] = st

    def _score(it: dict[str, Any]) -> float:
        ret = float(it.get("return_horizon_pct") or 0.0)
        win = None
        try:
            sample = (it.get("stability") or {}).get("sample")  # type: ignore[union-attr]
            if isinstance(sample, dict):
                win = _to_float(sample.get("win_rate"))
        except Exception:
            win = None
        # 风险低诉求：提高 win_rate 权重（用作“稳定性/波动小”的近似）
        if want_low_risk:
            return ret * 0.6 + float(win or 0.0) * 0.4
        return ret * 0.85 + float(win or 0.0) * 0.15

    candidates.sort(key=_score, reverse=True)
    topn = 5
    top_items = candidates[:topn]

    return json.dumps(
        {
            "ok": True,
            "mode": "rank",
            "horizon": horizon,
            "want_low_risk": want_low_risk,
            "topn": topn,
            "items": top_items,
            "note": "低风险/稳健为近似：使用“盈亏概率(胜率)”作为稳定性参考；非严格风险指标（如最大回撤/波动率）。",
        },
        ensure_ascii=False,
    )

