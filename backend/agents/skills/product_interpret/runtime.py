# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from typing import Any, Callable
import asyncio


def _is_blocked_or_html_error(err: Exception) -> bool:
    s = str(err or "")
    return (
        "Unexpected token '<'" in s
        or "notfound.html" in s
        or "403" in s
        or "Forbidden" in s
        or "result_code" in s
    )


async def _fetch_fundf10_tables(symbol: str, page: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    """
    通用 fundf10 HTML 表格抓取（备用源）。
    page 示例：jdzf / zcpz / jjcc 等；URL 形如 https://fundf10.eastmoney.com/{page}_{code}.html
    返回 {ok, data:[{col:val,...}], message?}
    """
    try:
        import httpx
        import pandas as pd  # type: ignore
    except Exception as e:
        return {"ok": False, "message": f"fallback {page} missing deps: {e}", "data": []}

    url = f"https://fundf10.eastmoney.com/{page}_{symbol}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text or ""
        if "<html" not in html.lower():
            return {"ok": False, "message": f"fallback {page} got non-html", "data": []}
        dfs = pd.read_html(html)
        if not dfs:
            return {"ok": False, "message": f"fallback {page} read_html empty", "data": []}
        out: list[dict[str, Any]] = []
        for df in dfs[:4]:
            try:
                records = df.head(200).to_dict(orient="records")  # type: ignore[no-any-return]
            except Exception:
                records = []
            for r in records:
                if isinstance(r, dict):
                    out.append({str(k).strip(): (str(v).strip() if v is not None else "") for k, v in r.items()})
        out = out[:400]
        if not out:
            return {"ok": False, "message": f"fallback {page} parsed empty", "data": []}
        return {"ok": True, "data": out}
    except Exception as e:
        return {"ok": False, "message": f"fallback {page} failed: {e}", "data": []}


async def _fetch_eastmoney_f10_nav(symbol: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    """
    备用净值抓取：绕开 pingzhongdata.js，改走 fundf10 的历史净值接口（HTML table）。
    返回格式对齐上层：{ok, message?, data:[{净值日期, 单位净值, 累计净值, 日增长率},...]}
    """
    try:
        import httpx
        import pandas as pd  # type: ignore
    except Exception as e:
        return {"ok": False, "message": f"fallback nav missing deps: {e}", "data": []}

    url = "https://fundf10.eastmoney.com/F10DataApi.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": f"https://fundf10.eastmoney.com/jjjz_{symbol}.html",
    }

    def _parse(html: str) -> list[dict[str, Any]]:
        # Eastmoney 返回形如：var apidata={ content:"<table>...</table>", ... }
        m = re.search(r'content:"(?P<tbl>.*)"\s*,\s*records', html, flags=re.S)
        if not m:
            # 有些情况下直接返回 table
            tbl_html = html
        else:
            tbl_html = m.group("tbl")
            tbl_html = tbl_html.replace("\\/", "/").replace('\\"', '"').replace("\\n", "\n")
        try:
            dfs = pd.read_html(tbl_html)
        except Exception:
            return []
        if not dfs:
            return []
        df = dfs[0]
        # 常见列：净值日期 单位净值 累计净值 日增长率 申购状态 赎回状态 分红送配
        out: list[dict[str, Any]] = []
        for _, row in df.head(365).iterrows():
            rec = {}
            for k in ("净值日期", "单位净值", "累计净值", "日增长率"):
                if k in df.columns:
                    v = row.get(k)
                    rec[k] = str(v).strip() if v is not None else ""
            if rec:
                out.append(rec)
        return out

    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            # 先拿第一页（最近 20 条）
            resp = await client.get(url, params={"type": "lsjz", "code": symbol, "page": 1, "per": 40}, headers=headers)
            resp.raise_for_status()
            txt = resp.text or ""
        data = _parse(txt)
        if not data:
            return {"ok": False, "message": "fallback nav parse empty", "data": []}
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "message": f"fallback nav failed: {e}", "data": []}


async def _fetch_eastmoney_f10_basic(symbol: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    """
    备用基础信息抓取：fundf10 基本概况页面（HTML tables）。
    返回 {ok, data:[{item,value},...]}
    """
    try:
        import httpx
        import pandas as pd  # type: ignore
    except Exception as e:
        return {"ok": False, "message": f"fallback basic missing deps: {e}", "data": []}

    url = f"https://fundf10.eastmoney.com/jbgk_{symbol}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text or ""
        if "<html" not in html.lower():
            return {"ok": False, "message": "fallback basic got non-html", "data": []}
        dfs = pd.read_html(html)
        if not dfs:
            return {"ok": False, "message": "fallback basic read_html empty", "data": []}
        # 取前几个表尝试拼 item/value
        out: list[dict[str, Any]] = []
        for df in dfs[:3]:
            # 常见两列：项目 / 值
            if df.shape[1] >= 2:
                for _, row in df.iterrows():
                    k = str(row.iloc[0]).strip()
                    v = str(row.iloc[1]).strip()
                    if k and k != "nan" and v and v != "nan":
                        out.append({"item": k, "value": v})
        out = out[:200]
        if not out:
            return {"ok": False, "message": "fallback basic parsed empty", "data": []}
        return {"ok": True, "data": out}
    except Exception as e:
        return {"ok": False, "message": f"fallback basic failed: {e}", "data": []}

async def _enrich_fund_with_ak_client(sym: str, fund_obj: dict[str, Any]) -> None:
    """从 AkShareClient.get_all_data 合并经理/评级/净值字段，避免与 client 内重复拉取逻辑。"""
    try:
        from pkg.akshare_client import AkShareClient

        client = AkShareClient()
        all_res = await client.get_all_data(sym)
        if not isinstance(all_res, dict) or not all_res.get("ok") or not isinstance(all_res.get("data"), dict):
            msg = (
                str((all_res or {}).get("message", "get_all_data failed"))
                if isinstance(all_res, dict)
                else "get_all_data failed"
            )
            fund_obj.setdefault("manager_tenure", {"ok": False, "message": msg, "data": []})
            fund_obj.setdefault("manager_career", {"ok": False, "message": msg, "data": []})
            fund_obj.setdefault("rating_info", {"ok": False, "message": msg, "data": {}})
            fund_obj.setdefault("nav_data", {"ok": False, "message": msg, "data": []})
            fund_obj.setdefault("nav_data_periods", {})
            return
        d = all_res["data"]
        fund_obj["manager_tenure"] = d.get("manager_tenure") or {"ok": False, "data": []}
        fund_obj["manager_career"] = d.get("manager_career") or {"ok": False, "data": []}
        fund_obj["rating_info"] = d.get("rating_info") or {"ok": False, "data": {}}
        fund_obj["nav_data"] = d.get("nav_data") or {"ok": False, "data": []}
        fund_obj["nav_data_periods"] = d.get("nav_data_periods") or {}
    except Exception as e:
        err = str(e)
        fund_obj.setdefault("manager_tenure", {"ok": False, "message": err, "data": []})
        fund_obj.setdefault("manager_career", {"ok": False, "message": err, "data": []})
        fund_obj.setdefault("rating_info", {"ok": False, "message": err, "data": {}})
        fund_obj.setdefault("nav_data", {"ok": False, "message": err, "data": []})
        fund_obj.setdefault("nav_data_periods", {})


def _json_dumps_safe(obj: Any) -> str:
    """确保 AkShare/HTTPX 返回中的 date/datetime 等可序列化。"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        # 极端兜底：避免 skill 因序列化失败导致整体丢失
        return json.dumps({"ok": False, "message": "json serialization failed"}, ensure_ascii=False)


def _extract_symbols(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # 兼容“这只基金161039”这类中文紧贴数字场景
    symbols = re.findall(r"(?<!\d)\d{6}(?!\d)", t)
    # 全局去重保持顺序
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_symbol_from_history(question: str, ctx: dict[str, Any], limit: int = 30) -> list[str]:
    """
    当用户未显式给出基金代码时，从会话历史中尝试回填：
    - 优先取最近一条 assistant 消息里出现的第一个 6 位代码
    - 否则取全部历史里出现过的第一个代码
    """
    q = (question or "").strip()
    _ = q  # 当前逻辑不依赖“前/后/这只”，保守取最近
    session_id = str((ctx or {}).get("session_id") or "").strip()
    if not session_id:
        return []
    try:
        from orchestrator.session import get_recent_messages

        msgs = get_recent_messages(session_id, limit=limit) or []
    except Exception:
        msgs = []

    for m in msgs:
        if str(m.get("role") or "").lower() != "assistant":
            continue
        syms = _extract_symbols(str(m.get("content_summary") or ""))
        if syms:
            return [syms[0]]

    # fallback：取历史中出现过的第一个代码
    for m in msgs:
        syms = _extract_symbols(str(m.get("content_summary") or ""))
        if syms:
            return [syms[0]]

    return []


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    产品解析 skill（基金单只深度取数）：
    - 基本信息：fund_individual_basic_info_xq
    - 业绩/表现：fund_individual_achievement_xq
    - 数据分析：fund_individual_analysis_xq
    - 盈亏概率：fund_individual_profit_probability_xq
    - 持仓行情/持仓明细：fund_individual_detail_hold_xq
    - 详情信息：fund_individual_detail_info_xq

    返回 JSON 字符串（供上层 LLM 作为“基金供应商数据”输入）。
    """
    q = (question or "").strip()
    uniq = _extract_symbols(q)
    if not uniq:
        uniq = _resolve_symbol_from_history(q, ctx)
    # 解析通常是单只/近似单只；最多处理 3 只，避免 prompt 过大
    uniq = uniq[:3]

    if not uniq:
        return _json_dumps_safe(
            {
                "ok": False,
                "mode": "single",
                "message": "未识别到可用基金代码（6位数字）。请直接提供代码（如161039），或先查询基金后再问“这只/这基金”。",
            },
        )

    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        return _json_dumps_safe(
            {
                "ok": False,
                "mode": "single",
                "message": "缺少 akshare 依赖，请在后端环境安装：pip install akshare pandas",
                "error": str(e),
                "symbols": uniq,
            },
        )

    def _fn(name: str) -> Callable[..., Any] | None:
        return getattr(ak, name, None)

    async def _call_ak(fn: Callable[..., Any], *, timeout_s: float, **kwargs: Any) -> Any:
        """Run AkShare sync API in thread with timeout. Note: timed-out threads may continue; we cap attempts by short timeouts."""
        async def _once(attempt: int) -> Any:
            out = await asyncio.wait_for(asyncio.to_thread(fn, **kwargs), timeout=timeout_s)
            return out

        try:
            return await _once(1)
        except asyncio.TimeoutError:
            # single retry on timeout (network instability)
            try:
                return await _once(2)
            except Exception:
                raise
        except Exception:
            raise

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

    # --------- 逐基金聚合（以雪球 XQ 单基金接口为主） ---------
    funds: list[dict[str, Any]] = []
    for sym in uniq:
        fund_obj: dict[str, Any] = {"symbol": sym}
        module_fail_count = 0
        module_ok_count = 0

        # 1) 基本信息
        fn_basic = _fn("fund_individual_basic_info_xq")
        if callable(fn_basic):
            try:
                df = await _call_ak(fn_basic, timeout_s=8.0, symbol=sym)  # type: ignore[misc]
                fund_obj["basic_info"] = _module_ok(_df_records(df, limit=200))
                module_ok_count += 1
            except Exception as e:
                # fallback: fundf10 基本概况
                fb = await _fetch_eastmoney_f10_basic(sym)
                if fb.get("ok") and isinstance(fb.get("data"), list) and fb["data"]:
                    fund_obj["basic_info"] = fb
                    module_ok_count += 1
                else:
                    fund_obj["basic_info"] = _module_fail(f"fund_individual_basic_info_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["basic_info"] = _module_fail("akshare 未提供 fund_individual_basic_info_xq")
            module_fail_count += 1

        # 2) 业绩/表现
        fn_ach = _fn("fund_individual_achievement_xq")
        if callable(fn_ach):
            try:
                df = await _call_ak(fn_ach, timeout_s=10.0, symbol=sym)  # type: ignore[misc]
                fund_obj["achievement"] = _module_ok(_df_records(df, limit=200))
                module_ok_count += 1
            except Exception as e:
                fb = await _fetch_fundf10_tables(sym, "jdzf")
                if fb.get("ok") and isinstance(fb.get("data"), list) and fb["data"]:
                    fund_obj["achievement"] = fb
                    module_ok_count += 1
                else:
                    fund_obj["achievement"] = _module_fail(f"fund_individual_achievement_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["achievement"] = _module_fail("akshare 未提供 fund_individual_achievement_xq")
            module_fail_count += 1

        # 3) 数据分析（风格/行业/配置等更偏“分析型”数据）
        fn_analysis = _fn("fund_individual_analysis_xq")
        if callable(fn_analysis):
            try:
                df = await _call_ak(fn_analysis, timeout_s=8.0, symbol=sym)  # type: ignore[misc]
                fund_obj["analysis"] = _module_ok(_df_records(df, limit=200))
                module_ok_count += 1
            except Exception as e:
                fb = await _fetch_fundf10_tables(sym, "zcpz")
                if fb.get("ok") and isinstance(fb.get("data"), list) and fb["data"]:
                    fund_obj["analysis"] = fb
                    module_ok_count += 1
                else:
                    fund_obj["analysis"] = _module_fail(f"fund_individual_analysis_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["analysis"] = _module_fail("akshare 未提供 fund_individual_analysis_xq")
            module_fail_count += 1

        # 4) 盈亏概率（雪球：雪球盈亏概率/胜率类数据）
        fn_prob = _fn("fund_individual_profit_probability_xq")
        if callable(fn_prob):
            try:
                df = await _call_ak(fn_prob, timeout_s=8.0, symbol=sym)  # type: ignore[misc]
                fund_obj["profit_probability"] = _module_ok(_df_records(df, limit=50))
                module_ok_count += 1
            except Exception as e:
                fund_obj["profit_probability"] = _module_fail(f"fund_individual_profit_probability_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["profit_probability"] = _module_fail("akshare 未提供 fund_individual_profit_probability_xq")
            module_fail_count += 1

        # 5) 持仓行情/持仓明细
        fn_hold = _fn("fund_individual_detail_hold_xq")
        if callable(fn_hold):
            try:
                df = await _call_ak(fn_hold, timeout_s=10.0, symbol=sym)  # type: ignore[misc]
                fund_obj["detail_hold"] = _module_ok(_df_records(df, limit=120))
                module_ok_count += 1
            except Exception as e:
                fb = await _fetch_fundf10_tables(sym, "jjcc")
                if fb.get("ok") and isinstance(fb.get("data"), list) and fb["data"]:
                    fund_obj["detail_hold"] = fb
                    module_ok_count += 1
                else:
                    fund_obj["detail_hold"] = _module_fail(f"fund_individual_detail_hold_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["detail_hold"] = _module_fail("akshare 未提供 fund_individual_detail_hold_xq")
            module_fail_count += 1

        # 6) 详情信息
        fn_detail = _fn("fund_individual_detail_info_xq")
        if callable(fn_detail):
            try:
                df = await _call_ak(fn_detail, timeout_s=10.0, symbol=sym)  # type: ignore[misc]
                fund_obj["detail_info"] = _module_ok(_df_records(df, limit=200))
                module_ok_count += 1
            except Exception as e:
                fund_obj["detail_info"] = _module_fail(f"fund_individual_detail_info_xq 失败: {e}")
                module_fail_count += 1
        else:
            fund_obj["detail_info"] = _module_fail("akshare 未提供 fund_individual_detail_info_xq")
            module_fail_count += 1

        # 额外：给上层做“风险相关”快速索引
        fund_obj["risk"] = fund_obj.get("profit_probability") or _module_fail("未获取到风险相关数据")

        await _enrich_fund_with_ak_client(sym, fund_obj)
        # fallback: nav_data 若仍失败（AkShare 可能走 pingzhongdata 被 notfound）
        try:
            nav = fund_obj.get("nav_data")
            if not (isinstance(nav, dict) and nav.get("ok")):
                fb_nav = await _fetch_eastmoney_f10_nav(sym)
                if fb_nav.get("ok"):
                    fund_obj["nav_data"] = fb_nav
        except Exception:
            pass

        funds.append(fund_obj)

    return _json_dumps_safe(
        {
            "ok": True,
            "mode": "single",
            "symbols": uniq,
            "funds": funds,
            "note": "字段/接口因上游站点风控/改版可能不稳定；模块级降级以 ok=false 表示。若遇 pingzhongdata/notfound/403，将自动使用 fundf10 作为净值/基础信息备用源。",
        },
    )

