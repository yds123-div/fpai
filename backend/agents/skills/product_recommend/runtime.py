from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime
from typing import Any, Callable, Iterable

from pkg.logger import get_logger


logger = get_logger(__name__)


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
                return None
            return float(x)
        s = str(x).strip()
        if not s or s.lower() in ("nan", "none"):
            return None
        if s.endswith("%"):
            return float(s[:-1])
        return float(s)
    except Exception:
        return None


def _extract_recommend_count(question: str) -> int | None:
    q = (question or "").strip()
    if not q:
        return None

    # 优先解析类似：目标推荐数量（...）：3
    m = re.search(r"目标推荐数量[^：:]*[：:]\s*(\d{1,2})", q)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None

    # 兜底：推荐/TopN/前N个
    m2 = re.search(r"(?:top|TOP)\s*(\d{1,2})", q)
    if m2:
        try:
            return int(m2.group(1))
        except Exception:
            return None

    m3 = re.search(r"推荐\s*(\d{1,2})\s*[个只款]", q)
    if m3:
        try:
            return int(m3.group(1))
        except Exception:
            return None

    return None


def _extract_profile_weights(profile_text: str) -> dict[str, float]:
    """
    从画像文本提取：
    - 理财占比
    - 债券型基金占比
    - 少量混合型基金占比（如果文本未含则给默认 0.145）
    """
    s = (profile_text or "").strip()
    if not s:
        return {"wealth": 0.527, "bond": 0.214, "hybrid": 0.145}

    def _pick(key: str, default: float) -> float:
        # 支持：xx占比52.7%
        m = re.search(rf"{re.escape(key)}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*%", s)
        if m:
            v = _safe_float(m.group(1))
            if v is not None:
                return float(v) / 100.0
        return default

    # 理财占比
    wealth = _pick("理财占比", 0.527)
    # 债券型基金占比
    bond = _pick("债券型基金占比", 0.214)
    # 混合型基金占比（文本中常写“混合型基金（当前占比14.5%）”）
    hybrid = _pick("混合型基金", 0.145)

    # 归一化（防止文本中缺失/重复导致和不为1）
    total = wealth + bond + hybrid
    if total <= 0:
        return {"wealth": 0.527, "bond": 0.214, "hybrid": 0.145}
    return {"wealth": wealth / total, "bond": bond / total, "hybrid": hybrid / total}


def _parse_customer_profile(question: str) -> str:
    """
    从 question 中尽量提取“客户画像”原文。
    - 若 question 不包含，则直接返回全量 question（有助于下游/调试）
    """
    q = (question or "").strip()
    if not q:
        return ""
    m = re.search(r"客户画像[:：]\s*([\s\S]*?)\n(?:目标|候选|用户问题|$)", q)
    if m:
        return (m.group(1) or "").strip()
    return q


def _horizon_key_from_question(question: str) -> str:
    """
    保守型画像更偏向“稳定性优先”，默认按近1年做收益近似。
    """
    q = (question or "").strip()
    if any(k in q for k in ("近1年", "近一年", "1年")):
        return "y1"
    if any(k in q for k in ("近半年", "半年", "6个月")):
        return "m6"
    if any(k in q for k in ("近三月", "近3月", "三个月", "3个月")):
        return "m3"
    # 默认
    return "y1"


def _name_to_category(name: str) -> tuple[str, list[str]]:
    """
    将基金名称映射到画像类型：
    - wealth：偏现金/货币/短债/超短债（更贴近理财稳健与流动性）
    - bond：纯债/债券（更贴近“优质债券基金”）
    - hybrid：混合/偏债混合（允许少量）
    """
    n = (name or "").strip()
    tags: list[str] = []

    hybrid_kw = ["混合", "偏股混合", "偏债混合", "二级债基", "灵活配置"]
    if any(k in n for k in hybrid_kw):
        tags.append("混合")
        return "hybrid", tags

    bond_kw = ["纯债", "信用债", "债券", "中短债", "利率债", "可转债"]
    if any(k in n for k in bond_kw):
        tags.append("债券")
        return "bond", tags

    wealth_kw = ["货币", "现金管理", "现金", "超短债", "短债", "同业存单"]
    if any(k in n for k in wealth_kw):
        tags.append("理财/现金类")
        return "wealth", tags

    # 未命中则默认 wealth（保守起见）
    tags.append("未知→理财类兜底")
    return "wealth", tags


def _allocate_counts(recommend_count: int, weights: dict[str, float]) -> dict[str, int]:
    """
    约束规则：
    - 混合型为“少量”，最多 1（当 recommend_count >= 3）
    - 债券型至少 1（当 recommend_count >= 2）
    - 其它填充到 wealth
    """
    n = max(1, min(10, int(recommend_count)))

    hybrid_max = 1 if n >= 3 else 0
    bond_min = 1 if n >= 2 else 0

    bond_count = max(bond_min, int(round(n * float(weights.get("bond") or 0.214))))
    bond_count = min(bond_count, n - hybrid_max)

    hybrid_count = min(hybrid_max, max(0, n - bond_count))

    wealth_count = n - bond_count - hybrid_count
    if wealth_count <= 0:
        # 修正：确保 wealth 至少 1（保守型优先给“理财/现金类”兜底）
        wealth_count = 1
        if bond_count > 1:
            bond_count -= 1
        else:
            hybrid_count = max(0, hybrid_count - 1)

    return {"wealth": wealth_count, "bond": bond_count, "hybrid": hybrid_count}


def _pick_horizon_col_index(horizon_key: str) -> int:
    """
    复用 product_query 中的字段索引约定：
    - 0 排名 1 代码 2 名称 3 日期 4 单位净值 5 累计净值 6 日增长率
    - 7 近1周 8 近1月 9 近3月 10 近6月 11 近1年 12 近2年 13 近3年
    - 14 今年来 15 成立来 16 自定义 17 手续费
    """
    return {
        "day": 6,
        "week": 7,
        "month": 8,
        "m3": 9,
        "m6": 10,
        "y1": 11,
        "y2": 12,
        "y3": 13,
        "this_year": 14,
        "since_est": 15,
    }.get(horizon_key, 11)


def _df_records(df: Any, limit: int = 200) -> list[dict[str, Any]]:
    try:
        if df is None:
            return []
        if hasattr(df, "head") and hasattr(df, "to_dict"):
            return df.head(limit).to_dict(orient="records")  # type: ignore[no-any-return]
    except Exception:
        return []
    return []


async def _safe_to_thread(fn: Callable[..., Any], **kwargs: Any) -> tuple[bool, Any]:
    try:
        res = await asyncio.to_thread(fn, **kwargs)
        return True, res
    except Exception as e:
        return False, str(e)


def _extract_basic_extracted(basic_info: dict[str, Any]) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    try:
        data = basic_info.get("data")
        if not isinstance(data, list):
            return extracted
        # 常见基本信息结构：[{item: "...", value:"..."}...]
        for row in data[:80]:
            if not isinstance(row, dict):
                continue
            item = str(row.get("item") or "").strip()
            value = row.get("value")
            if not item or value is None:
                continue
            key = item
            if "风险" in item:
                extracted["risk_text"] = str(value).strip()
            if "申赎" in item or "赎回" in item or "申购" in item:
                extracted["redemption_text"] = str(value).strip()
            if "基金类型" in item or "投资类型" in item:
                extracted["fund_type_text"] = str(value).strip()
            if "规模" in item:
                extracted["size_text"] = str(value).strip()
            if "成立" in item:
                extracted["established_text"] = str(value).strip()
    except Exception:
        return extracted
    return extracted


def _extract_profit_sample(prob_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    从 fund_individual_profit_probability_xq 的表里尝试抽取：
    - 胜率/盈亏概率
    - 平均收益
    由于字段名随版本变动，所以尽量用“位置+关键词”兜底。
    """
    sample: dict[str, Any] = {}
    try:
        if not prob_rows:
            return sample
        first = prob_rows[0]
        if not isinstance(first, dict):
            return sample

        keys = list(first.keys())
        # 可能存在：胜率/盈亏概率/平均收益 等列
        # 使用关键词优先
        for k in keys:
            lk = str(k)
            if "胜率" in lk or "赢" in lk or "概率" in lk:
                v = _safe_float(first.get(k))
                if v is not None:
                    # 若概率是 0~1，转成 0~100
                    sample["win_rate"] = v * 100.0 if v <= 1.0 else v
            if "平均" in lk or "均值" in lk or "收益" in lk:
                v = _safe_float(first.get(k))
                if v is not None:
                    sample["avg_return"] = v

        # 兜底：若未提取到，则按前3个字段取
        if "win_rate" not in sample and len(keys) >= 2:
            v = _safe_float(first.get(keys[1]))
            if v is not None:
                sample["win_rate"] = v * 100.0 if v <= 1.0 else v
        if "avg_return" not in sample and len(keys) >= 3:
            v = _safe_float(first.get(keys[2]))
            if v is not None:
                sample["avg_return"] = v
    except Exception:
        return {}
    return sample


def _score_candidate(
    *,
    win_rate: float | None,
    return_horizon_pct: float | None,
    risk_text: str | None,
    category: str,
) -> float:
    # win_rate 越高越好；return_horizon 作为次要参考
    w = float(win_rate or 0.0)
    r = float(return_horizon_pct or 0.0)

    # 风险文本尽量做轻微惩罚
    risk_penalty = 0.0
    if risk_text:
        m = re.search(r"R\s*([1-5])", str(risk_text))
        if m:
            risk_penalty = int(m.group(1)) * 0.02

    # wealth/bond：更保守一些；hybrid：允许略高的收益倾向
    if category == "hybrid":
        return w * 0.65 + r * 0.35 - risk_penalty
    if category == "bond":
        return w * 0.75 + r * 0.25 - risk_penalty
    return w * 0.8 + r * 0.2 - risk_penalty


def _topn_sorted(items: Iterable[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    ls = list(items)
    ls.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return ls[:n]


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    产品推荐 skill：
    - 解析 question 内的“客户画像 + 推荐数量”
    - akshare 拉取基金排行候选
    - 依照画像偏好挑选 wealth/bond/hybrid 类候选，并用 profit_probability_xq 提取“胜率”做稳定性评分
    - 取 basic_info 提取风险与申赎（流动性）线索
    - 输出选出的候选产品列表（尽量长度=recommend_count）
    """
    q = (question or "").strip()
    profile_text = _parse_customer_profile(q)
    weights = _extract_profile_weights(profile_text)

    recommend_count = _extract_recommend_count(q) or 3
    recommend_count = max(1, min(10, int(recommend_count)))

    horizon_key = _horizon_key_from_question(q)
    horizon_col_index = _pick_horizon_col_index(horizon_key)

    target_counts = _allocate_counts(recommend_count, weights)

    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "mode": "recommend_candidates",
                "message": "缺少 akshare 依赖，请在后端环境安装：pip install akshare pandas",
                "error": str(e),
                "akshare_interfaces_used": ["ak.fund_open_fund_rank_em"],
            },
            ensure_ascii=False,
        )

    # 1) 拉取排行：候选 pool
    try:
        df_rank = await _safe_to_thread(ak.fund_open_fund_rank_em, symbol="全部")  # type: ignore[misc]
        ok_rank, df_or_err = df_rank
        if not ok_rank:
            raise RuntimeError(df_or_err)
        df = df_or_err
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "mode": "recommend_candidates",
                "message": f"fund_open_fund_rank_em 失败: {e}",
                "akshare_interfaces_used": ["ak.fund_open_fund_rank_em"],
            },
            ensure_ascii=False,
        )

    # 约定：rank df 常见列顺序（product_query 使用同样逻辑）
    items: list[dict[str, Any]] = []
    try:
        values = getattr(df, "values", None)
        if values is None:
            raise ValueError("rank df 无 values")
        # 限制候选规模，控制后续接口调用次数
        for row in values[:3000]:
            try:
                code = str(row[1]).strip()
                name = str(row[2]).strip()
                date = str(row[3]).strip()
                ret_h = _safe_float(row[horizon_col_index])
                ret_day = _safe_float(row[6])
                if not code or code == "nan" or code == "None":
                    continue
                cat, tags = _name_to_category(name)
                items.append(
                    {
                        "symbol": code,
                        "name": name,
                        "date": date,
                        "return_horizon_pct": ret_h,
                        "return_day_pct": ret_day,
                        "category": cat,
                        "name_keyword_tags": tags,
                    }
                )
            except Exception:
                continue
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "mode": "recommend_candidates",
                "message": f"解析 rank df 失败: {e}",
            },
            ensure_ascii=False,
        )

    # 根据“收益近似”先做粗筛，减少 profit_probability 调用数量
    items = [x for x in items if x.get("return_horizon_pct") is not None]
    items.sort(key=lambda x: float(x.get("return_horizon_pct") or -10_000), reverse=True)
    candidates_pool = items[:60]

    # 2) 对每类分别取“候选top M”，再用胜率+风险做评分
    #    并发限制，避免拖慢整体请求
    sem = asyncio.Semaphore(4)

    async def _fetch_profit(symbol: str) -> dict[str, Any]:
        async with sem:
            try:
                df_prob = await asyncio.wait_for(
                    asyncio.to_thread(ak.fund_individual_profit_probability_xq, symbol=symbol), timeout=6.0  # type: ignore[misc]
                )
                rows = _df_records(df_prob, limit=50)
                sample = _extract_profit_sample(rows)
                return {"ok": True, "sample": sample, "rows_preview": rows[:3]}
            except asyncio.TimeoutError:
                return {"ok": False, "message": "fund_individual_profit_probability_xq 超时"}
            except Exception as e:
                return {"ok": False, "message": f"fund_individual_profit_probability_xq 失败: {e}"}

    async def _fetch_basic(symbol: str) -> dict[str, Any]:
        async with sem:
            try:
                df_basic = await asyncio.wait_for(
                    asyncio.to_thread(ak.fund_individual_basic_info_xq, symbol=symbol), timeout=6.0  # type: ignore[misc]
                )
                rows = _df_records(df_basic, limit=120)
                extracted = _extract_basic_extracted({"data": rows})
                return {"ok": True, "extracted": extracted, "rows_preview": rows[:5]}
            except asyncio.TimeoutError:
                return {"ok": False, "message": "fund_individual_basic_info_xq 超时"}
            except Exception as e:
                return {"ok": False, "message": f"fund_individual_basic_info_xq 失败: {e}"}

    # 为了控制调用量：每类先取不超过 12 个，再精筛
    per_category_need = {"wealth": target_counts["wealth"], "bond": target_counts["bond"], "hybrid": target_counts["hybrid"]}
    per_category_take = {k: min(12, max(6, v * 4)) for k, v in per_category_need.items() if v >= 0}

    pool_by_cat: dict[str, list[dict[str, Any]]] = {"wealth": [], "bond": [], "hybrid": []}
    for it in candidates_pool:
        cat = it.get("category")
        if cat in pool_by_cat:
            pool_by_cat[cat].append(it)

    selected_by_cat: list[dict[str, Any]] = []
    to_score: list[dict[str, Any]] = []
    for cat, need in per_category_need.items():
        if need <= 0:
            continue
        pool = pool_by_cat.get(cat) or []
        to_score.extend(pool[: per_category_take.get(cat, 12)])

    # 去重（同一 symbol 只打一次）
    seen_sym: set[str] = set()
    uniq_to_score: list[dict[str, Any]] = []
    for it in to_score:
        sym = str(it.get("symbol") or "").strip()
        if not sym or sym in seen_sym:
            continue
        seen_sym.add(sym)
        uniq_to_score.append(it)

    # 上限：避免一次打太多接口
    uniq_to_score = uniq_to_score[:40]

    # 3) 并发拉取 profit/basic，并计算 score
    async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
        sym = str(it.get("symbol") or "")
        cat = str(it.get("category") or "wealth")

        profit_task = asyncio.create_task(_fetch_profit(sym))
        basic_task = asyncio.create_task(_fetch_basic(sym))
        profit = await profit_task
        basic = await basic_task

        win_rate = None
        try:
            if profit.get("ok") is True:
                sample = profit.get("sample") or {}
                if isinstance(sample, dict):
                    win_rate = _safe_float(sample.get("win_rate"))
                    if win_rate is not None and 0 <= win_rate <= 1:
                        win_rate = win_rate * 100.0
        except Exception:
            win_rate = None

        risk_text = None
        try:
            if basic.get("ok") is True:
                extracted = basic.get("extracted") or {}
                if isinstance(extracted, dict):
                    risk_text = extracted.get("risk_text")
        except Exception:
            risk_text = None

        score = _score_candidate(
            win_rate=win_rate,
            return_horizon_pct=_safe_float(it.get("return_horizon_pct")),
            risk_text=risk_text,
            category=cat,
        )

        return {
            **it,
            "score": score,
            "profit_probability": profit,
            "basic_info": basic,
        }

    try:
        enriched = await asyncio.gather(*[_enrich(it) for it in uniq_to_score], return_exceptions=False)
    except Exception as e:
        logger.warning("product_recommend skill enrich failed: %s", e)
        enriched = []

    # 4) 按类别取 top，尽量满足配额
    by_cat: dict[str, list[dict[str, Any]]] = {"wealth": [], "bond": [], "hybrid": []}
    for it in enriched:
        cat = it.get("category")
        if cat in by_cat:
            by_cat[cat].append(it)

    for cat in by_cat:
        by_cat[cat] = _topn_sorted(by_cat[cat], per_category_take.get(cat, 12))

    selected: list[dict[str, Any]] = []
    for cat in ("wealth", "bond", "hybrid"):
        need = target_counts.get(cat, 0)
        if need <= 0:
            continue
        selected.extend(by_cat.get(cat, [])[:need])

    # 兜底：如果不足 recommend_count，则从全部候选池补齐（偏向 wealth/bond）
    if len(selected) < recommend_count:
        remain = recommend_count - len(selected)
        selected_syms = {str(x.get("symbol") or "") for x in selected}
        # 优先 wealth->bond->hybrid，且按 score 降序
        fallback_order = [("wealth", 0.5), ("bond", 0.3), ("hybrid", 0.2)]
        all_scored = []
        for cat, _w in fallback_order:
            all_scored.extend(by_cat.get(cat, []))
        # 去重
        dedup: list[dict[str, Any]] = []
        seen = set()
        for it in all_scored:
            sym = str(it.get("symbol") or "")
            if not sym or sym in seen or sym in selected_syms:
                continue
            seen.add(sym)
            dedup.append(it)
        selected.extend(dedup[:remain])

    # 最终截断
    selected = selected[:recommend_count]

    out = {
        "ok": True,
        "mode": "recommend_candidates",
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "recommend_count": recommend_count,
        "target_allocation": weights,
        "target_counts": target_counts,
        "selected_candidates": [
            {
                "category": it.get("category"),
                "symbol": it.get("symbol"),
                "name": it.get("name"),
                "score": it.get("score"),
                "return_horizon_pct": it.get("return_horizon_pct"),
                "profit_probability": it.get("profit_probability"),
                "basic_info": it.get("basic_info"),
                "name_keyword_tags": it.get("name_keyword_tags"),
            }
            for it in selected
        ],
        "akshare_interfaces_used": [
            "ak.fund_open_fund_rank_em",
            "ak.fund_individual_profit_probability_xq",
            "ak.fund_individual_basic_info_xq",
        ],
        "note": f"horizon_key={horizon_key}；低风险/稳健使用胜率(盈亏概率)做近似，并结合风险文本做轻微惩罚。",
    }

    return json.dumps(out, ensure_ascii=False)

