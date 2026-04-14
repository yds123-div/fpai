"""
基金分析结构化输出格式化工具。

将 Skill 返回的原始基金数据（AkShare）转换为前端可直接渲染的
FundAnalysisOutput JSON，不依赖 LLM 生成结构。

数据源约定：
- product_interpret skill: 每只基金含 basic_info, achievement, analysis,
  profit_probability, detail_hold, detail_info, risk 等模块
- product_compare skill: 每只基金含 basic_info, performance
  (achievement + profit_probability), asset_allocation, risk 等模块

每个模块结构：{ok: bool, data: list[dict] | dict, message?: str}
"""
from __future__ import annotations

import json
import logging
import re
import math
from typing import Any

from pkg.fund_types import (
    FUND_ANALYSIS_TYPE,
    ChartConfig,
    FundAnalysisOutput,
    InfoCard,
    TableSection,
    TextSection,
    is_fund_analysis,
)

logger = logging.getLogger(__name__)

# 环形图 / 折线图默认配色
DEFAULT_COLORS = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4"]


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _safe(val: Any, default: Any = "") -> Any:
    """取值为 None 时返回默认值。"""
    return val if val is not None else default


def _module_data(module: Any) -> list[dict[str, Any]] | None:
    """从模块对象中安全提取 data 列表。"""
    if not isinstance(module, dict):
        return None
    if not module.get("ok"):
        return None
    data = module.get("data")
    if isinstance(data, list):
        return data
    return None


def _module_data_dict(module: Any) -> dict[str, Any] | None:
    """从模块对象中安全提取 data（dict 形式，如 asset_allocation）。"""
    if not isinstance(module, dict) or not module.get("ok"):
        return None
    data = module.get("data")
    if isinstance(data, dict):
        return data
    return None


def _kv_lookup(records: list[dict[str, Any]], key: str) -> str:
    """在 [{item: ..., value: ...}] 结构中查找指定 key 的 value。"""
    for r in records:
        if not isinstance(r, dict):
            continue
        item_name = str(
            r.get("item")
            or r.get("项目")
            or r.get("name")
            or r.get("条件或名称")
            or r.get("费用类型")
            or r.get("收费项目")
            or ""
        )
        if item_name == key:
            return str(
                _safe(
                    r.get("value")
                    or r.get("数值")
                    or r.get("val")
                    or r.get("费率")
                    or r.get("费用")
                    or r.get("收费标准"),
                    "",
                )
            )
    return ""


def _kv_to_dict(records: list[dict[str, Any]]) -> dict[str, str]:
    """将 [{item: ..., value: ...}] 列表转为 {item: value} dict。"""
    out: dict[str, str] = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        # 兼容 AkShare 多种字段命名：item/value、费用类型/条件或名称/费率 等
        k = str(
            r.get("item")
            or r.get("项目")
            or r.get("name")
            or r.get("条件或名称")
            or r.get("费用类型")
            or r.get("收费项目")
            or ""
        ).strip()
        v = str(
            _safe(
                r.get("value")
                or r.get("数值")
                or r.get("val")
                or r.get("费率")
                or r.get("费用")
                or r.get("收费标准"),
                "",
            )
        ).strip()
        if k:
            out[k] = v
    return out


def _pct(val: Any) -> str:
    """尝试把数值转成百分比字符串，已经是字符串则原样返回。"""
    if val is None or val == "":
        return ""
    s = str(val).strip()
    if "%" in s:
        return s
    try:
        f = float(s)
        return f"{f:.2f}%"
    except (ValueError, TypeError):
        return s


def _float_or(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    s = str(val).replace("%", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except Exception:
        try:
            return float(s.replace("%", "").strip())
        except Exception:
            return None


# ---------------------------------------------------------------------------
# 提取 payload + funds
# ---------------------------------------------------------------------------

def _extract_payload(supplier_data: Any) -> dict[str, Any] | None:
    """从 supplier_data 中提取 payload。支持多种包装形式。"""
    if not isinstance(supplier_data, dict):
        return None
    payload = supplier_data.get("payload")
    if isinstance(payload, dict):
        return payload
    if supplier_data.get("ok") is not None:
        return supplier_data
    return None


def _extract_funds(payload: dict[str, Any]) -> list[dict[str, Any]]:
    funds = payload.get("funds")
    if isinstance(funds, list):
        return [f for f in funds if isinstance(f, dict)]
    return []


# ---------------------------------------------------------------------------
# 卡片格式化
# ---------------------------------------------------------------------------

_BASIC_FIELDS = [
    ("基金简称", "name"), ("基金全称", "name"), ("基金名称", "name"),
    ("基金代码", "code"),
    ("基金类型", "type"), ("类型", "type"),
    ("基金经理", "manager"), ("经理", "manager"),
    ("基金规模", "scale"), ("规模", "scale"), ("资产净值", "scale"),
    ("风险等级", "riskLevel"), ("风险级别", "riskLevel"),
    ("成立日期", "establishDate"), ("成立时间", "establishDate"),
    ("申购状态", "purchaseStatus"), ("赎回状态", "redeemStatus"),
    ("状态", "status"),
]

_FEE_FIELDS = [
    ("管理费率", "managementFee"), ("管理费", "managementFee"),
    ("托管费率", "custodyFee"), ("托管费", "custodyFee"),
    ("申购费率", "subscriptionFee"), ("申购费", "subscriptionFee"),
    ("赎回费率", "redemptionFee"), ("赎回费", "redemptionFee"),
    ("销售服务费", "salesServiceFee"), ("销售服务费率", "salesServiceFee"),
]


def _build_basic_card(sym: str, records: list[dict[str, Any]]) -> InfoCard | None:
    kv = _kv_to_dict(records)
    if not kv:
        return None
    data: dict[str, Any] = {"code": sym}
    for src_key, dst_key in _BASIC_FIELDS:
        v = kv.get(src_key, "")
        if v and dst_key not in data:
            data[dst_key] = v
    if len(data) <= 1:
        return None
    return {"id": f"basic_{sym}", "title": "基本信息", "type": "basic", "data": data}


def _build_fee_card(sym: str, records: list[dict[str, Any]]) -> InfoCard | None:
    kv = _kv_to_dict(records)
    data: dict[str, Any] = {}
    for src_key, dst_key in _FEE_FIELDS:
        v = kv.get(src_key, "")
        if v and dst_key not in data:
            data[dst_key] = v
    if not data:
        return None
    return {"id": f"fee_{sym}", "title": "费率信息", "type": "fee", "data": data}


def _build_performance_card(sym: str, records: list[dict[str, Any]]) -> InfoCard | None:
    """从 achievement records 提取核心表现指标。"""
    if not records:
        return None
    kv = _kv_to_dict(records)
    data: dict[str, Any] = {}
    perf_mapping = [
        ("近1年", "return_1y"), ("近一年", "return_1y"), ("近1年收益率", "return_1y"),
        ("近3年", "return_3y"), ("近三年", "return_3y"), ("近3年收益率", "return_3y"),
        ("近6月", "return_6m"), ("近六月", "return_6m"), ("近6月收益率", "return_6m"),
        ("近1月", "return_1m"), ("近一月", "return_1m"), ("近1月收益率", "return_1m"),
        ("今年来", "return_ytd"), ("今年以来", "return_ytd"),
        ("成立来", "return_since_inception"), ("成立以来", "return_since_inception"),
        ("夏普比率", "sharpe"), ("夏普", "sharpe"),
        ("最大回撤", "maxDrawdown"),
        ("波动率", "volatility"), ("年化波动率", "volatility"),
    ]
    for src_key, dst_key in perf_mapping:
        v = kv.get(src_key, "")
        if v and dst_key not in data:
            data[dst_key] = v

    # 尝试从非 key-value 记录中提取（如果 records 是列式数据）
    if not data and records:
        first = records[0]
        for col_name in first:
            col_lower = str(col_name).lower()
            if "1年" in col_name or "1y" in col_lower:
                data.setdefault("return_1y", str(first[col_name]))
            elif "3年" in col_name or "3y" in col_lower:
                data.setdefault("return_3y", str(first[col_name]))
            elif "夏普" in col_name or "sharpe" in col_lower:
                data.setdefault("sharpe", str(first[col_name]))
            elif "回撤" in col_name or "drawdown" in col_lower:
                data.setdefault("maxDrawdown", str(first[col_name]))

    if not data:
        return None
    return {"id": f"performance_{sym}", "title": "核心表现", "type": "performance", "data": data}


def format_fund_cards(fund_obj: dict[str, Any]) -> list[InfoCard]:
    """为单只基金生成卡片列表。
    
    支持多种数据源：
    - AkShare: basic_info.data, detail_info.data, achievement.data
    - Skill: basic_info.data, detail_info.data, achievement.data, performance.achievement.data
    
    生成的卡片类型：
    - basic: 基本信息（名称、代码、类型、经理、规模等）
    - fee: 费率信息（管理费、托管费、申购费、赎回费等）
    - performance: 核心表现（近1年、近3年、夏普比率、最大回撤等）
    """
    sym = str(fund_obj.get("symbol") or "")
    cards: list[InfoCard] = []

    # basic_info（interpret 直接有；compare 也直接有；AkShare 也直接有）
    basic_records = _module_data(fund_obj.get("basic_info"))
    detail_records = _module_data(fund_obj.get("detail_info"))
    all_basic = (basic_records or []) + (detail_records or [])

    if all_basic:
        c = _build_basic_card(sym, all_basic)
        if c:
            cards.append(c)
        c = _build_fee_card(sym, all_basic)
        if c:
            cards.append(c)

    # achievement（interpret: 顶层 achievement；compare: performance.achievement；AkShare: 顶层 achievement）
    ach_records = _module_data(fund_obj.get("achievement"))
    if ach_records is None:
        perf = fund_obj.get("performance")
        if isinstance(perf, dict):
            ach_records = _module_data(perf.get("achievement"))
    if ach_records:
        c = _build_performance_card(sym, ach_records)
        if c:
            cards.append(c)

    return cards


# ---------------------------------------------------------------------------
# 表格格式化
# ---------------------------------------------------------------------------

def format_performance_table(funds: list[dict[str, Any]]) -> TableSection | None:
    """多基金业绩对比表格。
    
    支持多种数据源：
    - AkShare: achievement.data (业绩指标)
    - Skill: achievement.data, performance.achievement.data
    
    生成的表格包含：
    - 近1月、近3月、近6月、近1年、近3年收益率
    - 今年来、成立来收益率
    - 夏普比率、最大回撤、波动率等风险指标
    """
    if not funds:
        return None

    symbols = [str(f.get("symbol") or "") for f in funds]
    headers = ["指标"] + symbols

    # 收集每只基金的业绩指标（achievement + analysis 风险指标补充）
    perf_data: dict[str, dict[str, str]] = {}
    missing: list[dict[str, Any]] = []
    for fund in funds:
        sym = str(fund.get("symbol") or "")
        # 支持 AkShare 和 Skill 两种格式
        ach_records = _module_data(fund.get("achievement"))
        if ach_records is None:
            perf = fund.get("performance")
            if isinstance(perf, dict):
                ach_records = _module_data(perf.get("achievement"))
        if not ach_records:
            missing.append({
                "symbol": sym,
                "has_achievement_module": isinstance(fund.get("achievement"), dict),
                "achievement_ok": (fund.get("achievement") or {}).get("ok") if isinstance(fund.get("achievement"), dict) else None,
                "has_performance_module": isinstance(fund.get("performance"), dict),
                "performance_achievement_ok": ((fund.get("performance") or {}).get("achievement") or {}).get("ok")
                if isinstance(fund.get("performance"), dict) and isinstance((fund.get("performance") or {}).get("achievement"), dict)
                else None,
            })
            continue
        kv = _kv_to_dict(ach_records)
        # 补充：analysis 宽表里的“近1年”风险指标，写入固定展示行
        chosen_period, analysis_risk = _extract_analysis_risk_metrics(fund)
        label = chosen_period or "近1年"
        if analysis_risk.get("年化波动率"):
            kv.setdefault(f"{label}年化波动率", analysis_risk["年化波动率"])
        if analysis_risk.get("夏普比率"):
            kv.setdefault(f"{label}年化夏普比率", analysis_risk["夏普比率"])
        if analysis_risk.get("最大回撤"):
            kv.setdefault(f"{label}最大回撤", analysis_risk["最大回撤"])
        perf_data[sym] = kv

    if not perf_data:
        return None

    # 扩展优先级指标列表，增加更多维度
    priority = [
        "近1月", "近3月", "近6月", "近1年", "近2年", "近3年", "近5年",
        "今年来", "成立来",
        "近1年年化夏普比率", "近1年年化波动率", "近1年最大回撤",
        "近3年年化夏普比率", "近3年年化波动率", "近3年最大回撤",
        "成立以来年化夏普比率", "成立以来年化波动率", "成立以来最大回撤",
        "夏普比率", "最大回撤", "波动率", "索提诺比率", "卡玛比率",
        "年化收益", "年化波动", "信息比率", "跟踪误差",
        "阿尔法", "贝塔", "R平方"
    ]
    
    # 收集所有出现过的指标名
    all_metrics: list[str] = []
    seen: set[str] = set()
    for m in priority:
        for sym_kv in perf_data.values():
            if m in sym_kv and m not in seen:
                all_metrics.append(m)
                seen.add(m)
                break
    for sym_kv in perf_data.values():
        for m in sym_kv:
            if m not in seen:
                all_metrics.append(m)
                seen.add(m)

    if not all_metrics:
        return None

    rows: list[dict[str, Any]] = []
    cell_classes: dict[str, str] = {}
    cell_tooltips: dict[str, str] = {}

    def _parse_num(v: str) -> float | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s or s in {"-", "—"}:
            return None
        s = s.replace("%", "").strip()
        try:
            return float(s)
        except Exception:
            return None

    def _metric_prefers_high(metric: str) -> bool:
        return ("夏普" in metric) or ("信息比率" in metric) or ("索提诺" in metric) or ("卡玛" in metric) or ("阿尔法" in metric)

    def _metric_prefers_low(metric: str) -> bool:
        return ("波动" in metric) or ("回撤" in metric) or ("跟踪误差" in metric)

    # 增加显示指标数量到25个
    for metric in all_metrics[:25]:
        row: dict[str, Any] = {"指标": metric}
        for sym in symbols:
            row[sym] = perf_data.get(sym, {}).get(metric, "-")
        rows.append(row)

        # 单元格级别高亮：同一指标行内做最优/最劣标注
        if _metric_prefers_high(metric) or _metric_prefers_low(metric):
            vals: list[tuple[str, float]] = []
            for sym in symbols:
                n = _parse_num(str(row.get(sym, "")))
                if n is None:
                    continue
                # 最大回撤通常为负或已是绝对值，这里统一取绝对值参与比较（越小越好）
                if "回撤" in metric:
                    n = abs(n)
                vals.append((sym, n))
            if len(vals) >= 2:
                best_sym = None
                worst_sym = None
                if _metric_prefers_high(metric):
                    best_sym = max(vals, key=lambda x: x[1])[0]
                    worst_sym = min(vals, key=lambda x: x[1])[0]
                else:
                    best_sym = min(vals, key=lambda x: x[1])[0]
                    worst_sym = max(vals, key=lambda x: x[1])[0]
                ridx = len(rows) - 1
                if best_sym:
                    cell_classes[f"{ridx}|{best_sym}"] = "cell-good"
                    cell_tooltips[f"{ridx}|{best_sym}"] = "该指标在对比基金中更优"
                if worst_sym:
                    cell_classes[f"{ridx}|{worst_sym}"] = "cell-bad"
                    cell_tooltips[f"{ridx}|{worst_sym}"] = "该指标在对比基金中偏弱"

    return {
        "id": "performance_compare",
        "title": "业绩对比",
        "type": "table",
        "description": "说明：近1年年化波动率/年化夏普比率/最大回撤优先来自风险分析数据源；缺失显示为 - 。同一行内绿色为更优、红色为偏弱。",
        "table": {"headers": headers, "rows": rows, "highlight": symbols, "cell": {"classes": cell_classes, "tooltips": cell_tooltips}},
    }


def format_fee_table(funds: list[dict[str, Any]]) -> TableSection | None:
    """多基金费率对比表格。
    
    支持多种数据源：
    - AkShare: basic_info.data, detail_info.data (费率信息)
    - Skill: basic_info.data, detail_info.data
    
    生成的表格包含：
    - 管理费率、托管费率
    - 申购费率、赎回费率
    - 销售服务费率
    """
    symbols = [str(f.get("symbol") or "") for f in funds]
    headers = ["费用类型"] + symbols

    fee_map: dict[str, dict[str, str]] = {}
    for fund in funds:
        sym = str(fund.get("symbol") or "")
        # 支持 AkShare 和 Skill 两种格式
        records = _module_data(fund.get("basic_info")) or _module_data(fund.get("detail_info")) or []
        kv = _kv_to_dict(records)
        fees: dict[str, str] = {}
        for src_key, _ in _FEE_FIELDS:
            v = kv.get(src_key, "")
            if v:
                fees[src_key] = v
        fee_map[sym] = fees

    all_fee_keys: list[str] = []
    seen: set[str] = set()
    for sym_fees in fee_map.values():
        for k in sym_fees:
            if k not in seen:
                all_fee_keys.append(k)
                seen.add(k)

    if not all_fee_keys:
        return None

    rows: list[dict[str, Any]] = []
    for fk in all_fee_keys:
        row: dict[str, Any] = {"费用类型": fk}
        for sym in symbols:
            row[sym] = fee_map.get(sym, {}).get(fk, "-")
        rows.append(row)

    return {
        "id": "fee_compare",
        "title": "费率对比",
        "type": "table",
        "table": {"headers": headers, "rows": rows},
    }


def format_basic_info_table(funds: list[dict[str, Any]]) -> TableSection | None:
    """基金基本信息对比表格。
    
    包含：基金规模、成立日期、基金经理、基金公司、风险等级、评级等
    """
    if not funds:
        return None

    symbols = [str(f.get("symbol") or "") for f in funds]
    headers = ["基本信息"] + symbols

    # 要提取的基本信息字段
    info_fields = [
        "基金全称", "基金简称", "基金类型", "基金规模", "成立日期",
        "基金经理", "基金公司", "托管银行", "风险等级", "晨星评级",
        "投资风格", "业绩比较基准", "跟踪标的"
    ]

    info_map: dict[str, dict[str, str]] = {}
    for fund in funds:
        sym = str(fund.get("symbol") or "")
        records = _module_data(fund.get("basic_info")) or _module_data(fund.get("detail_info")) or []
        kv = _kv_to_dict(records)
        info_map[sym] = kv

    if not info_map:
        return None

    rows: list[dict[str, Any]] = []
    for field in info_fields:
        # 检查是否至少有一个基金有这个字段
        if any(field in kv for kv in info_map.values()):
            row: dict[str, Any] = {"基本信息": field}
            for sym in symbols:
                row[sym] = info_map.get(sym, {}).get(field, "-")
            rows.append(row)

    if not rows:
        return None

    return {
        "id": "basic_info_compare",
        "title": "基本信息对比",
        "type": "table",
        "table": {"headers": headers, "rows": rows},
    }


def format_standard_14_fields_table(fund_obj: dict[str, Any]) -> TableSection | None:
    """格式化基金标准14字段信息表格。
    
    输出包含以下14个字段的表格：
    1. 基金代码
    2. 基金名称
    3. 基金全称
    4. 成立时间
    5. 最新规模
    6. 基金公司
    7. 基金经理
    8. 托管银行
    9. 基金类型
    10. 评级机构
    11. 基金评级
    12. 投资策略
    13. 投资目标
    14. 业绩比较基准
    
    Args:
        fund_obj: 基金数据对象，包含 symbol 和 basic_info/detail_info 等模块
        
    Returns:
        TableSection 或 None（如果数据不足）
    """
    if not fund_obj:
        return None
    
    symbol = str(fund_obj.get("symbol") or "")
    if not symbol:
        return None
    
    # 合并 basic_info + detail_info，避免只取其一导致字段缺失
    basic_records = _module_data(fund_obj.get("basic_info")) or []
    detail_records = _module_data(fund_obj.get("detail_info")) or []
    records = basic_records + detail_records
    kv = _kv_to_dict(records)

    if not kv:
        return None
    
    def _compose_fee_summary(kv_data: dict[str, str]) -> str:
        """将费率信息合成为固定句式：费率方面：...；...。"""
        def _first_match_value(*keywords: str) -> str:
            for k, v in kv_data.items():
                key = str(k).strip()
                val = str(v).strip()
                if not val:
                    continue
                if all(kw in key for kw in keywords):
                    return val
            return ""

        management_fee = (
            kv_data.get("管理费率")
            or kv_data.get("管理费")
            or _first_match_value("管理", "费")
        )
        custody_fee = (
            kv_data.get("托管费率")
            or kv_data.get("托管费")
            or _first_match_value("托管", "费")
        )
        sales_service_fee = (
            kv_data.get("销售服务费率")
            or kv_data.get("销售服务费")
            or _first_match_value("销售", "服务", "费")
        )

        base_redemption_fee = (
            kv_data.get("赎回费率")
            or kv_data.get("赎回费")
            or _first_match_value("赎回", "费")
        )
        redemption_tiers: list[str] = []

        def _tier_order(text: str) -> int:
            if "7天内" in text:
                return 1
            if "7-30天" in text or "7至30天" in text:
                return 2
            if "30天以上" in text:
                return 3
            return 99

        for k, v in kv_data.items():
            key = str(k).strip()
            val = str(v).strip()
            if not key:
                continue
            # 分段赎回规则：如“持有7天内赎回收取”“持有7-30天收取”“持有30天以上免收赎回费”
            if "持有" in key:
                if "免收" in key and not val:
                    redemption_tiers.append(key)
                elif val:
                    redemption_tiers.append(f"{key}{val}")
                continue
            if key in {"赎回费", "赎回费率"}:
                continue
            if "赎回" in key and val:
                redemption_tiers.append(f"{key}{val}")

        annual_fee_parts: list[str] = []
        if management_fee:
            annual_fee_parts.append(f"管理费{management_fee}")
        if custody_fee:
            annual_fee_parts.append(f"托管费{custody_fee}")
        if sales_service_fee:
            annual_fee_parts.append(f"销售服务费{sales_service_fee}")

        redemption_tiers = sorted(redemption_tiers, key=_tier_order)

        annual_part = "，".join(annual_fee_parts) if annual_fee_parts else ""
        redemption_part = "，".join(redemption_tiers) if redemption_tiers else ""
        if not redemption_part and base_redemption_fee:
            redemption_part = f"赎回费{base_redemption_fee}"

        if annual_part and redemption_part:
            return f"费率方面：{annual_part}；{redemption_part}。"
        if annual_part:
            return f"费率方面：{annual_part}。"
        if redemption_part:
            return f"费率方面：{redemption_part}。"
        return "-"

    def _rating_from_rating_info(fund: dict[str, Any]) -> str:
        """当基础字段是'暂无评级'时，尝试从 rating_info 模块补充评级。"""
        ri = fund.get("rating_info")
        if not isinstance(ri, dict):
            return "暂无评级（评级数据不可用）"
        if not ri.get("ok"):
            data_obj = ri.get("data")
            if isinstance(data_obj, dict):
                msgs = []
                for k in ("sh", "zs", "ja"):
                    rec = data_obj.get(k)
                    if isinstance(rec, dict):
                        msg = str(rec.get("message") or "").strip()
                        if msg:
                            msgs.append(msg)
                if msgs and all("not found" in m.lower() for m in msgs):
                    return "暂无评级（该基金未纳入三方评级）"
            return "暂无评级（评级数据暂不可用）"
        data = ri.get("data")
        if not isinstance(data, dict):
            return "暂无评级（评级数据格式异常）"

        def _extract_stars(rec: dict[str, Any] | None) -> str:
            if not isinstance(rec, dict):
                return ""
            record = rec.get("record")
            if not isinstance(record, dict):
                return ""
            stars = record.get("stars")
            if isinstance(stars, dict) and stars:
                pairs = []
                for k, v in stars.items():
                    if v is None or str(v).strip() in {"", "0", "0.0"}:
                        continue
                    pairs.append(f"{k}:{v}")
                return "；".join(pairs)
            return ""

        parts: list[str] = []
        mapping = [("sh", "上海证券"), ("zs", "招商证券"), ("ja", "济安金信")]
        for k, agency in mapping:
            txt = _extract_stars(data.get(k))
            if txt:
                parts.append(f"{agency}({txt})")
        return " | ".join(parts) if parts else "暂无评级（该基金未纳入三方评级）"

    def _parse_days(val: Any) -> int:
        try:
            return int(float(str(val).strip()))
        except Exception:
            return 0

    def _parse_pct(val: Any) -> float | None:
        if val is None:
            return None
        s = str(val).replace("%", "").strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    def _annualized_return(penavgrowth_pct: float, days: int) -> float | None:
        if days <= 0:
            return None
        r = penavgrowth_pct / 100.0
        try:
            return (1.0 + r) ** (365.0 / float(days)) - 1.0
        except Exception:
            return None

    def _manager_metrics_text(fund: dict[str, Any]) -> tuple[str, str, str]:
        """返回：从业经验、管理本基金年限、任期年化回报（三个字符串）。"""
        career_text = "-"
        tenure_years_text = "-"
        tenure_ann_text = "-"

        # 1) 从业经验：manager_career.data 里按 name 聚合
        mc = fund.get("manager_career")
        if isinstance(mc, dict) and mc.get("ok") and isinstance(mc.get("data"), list):
            best: dict[str, Any] = {}
            for rec in mc.get("data") or []:
                if not isinstance(rec, dict):
                    continue
                nm = str(rec.get("name") or "").strip()
                career = rec.get("career")
                if not nm or career is None:
                    continue
                # 若出现多条，优先取数值更大的那条（通常为天数）
                try:
                    cnum = float(str(career).strip())
                except Exception:
                    cnum = None
                prev = best.get(nm)
                if prev is None:
                    best[nm] = career
                else:
                    try:
                        pnum = float(str(prev).strip())
                    except Exception:
                        pnum = None
                    if cnum is not None and (pnum is None or cnum > pnum):
                        best[nm] = career
            if best:
                career_text = "\n".join([f"{k}：{v}" for k, v in best.items()])

        # 2) 任期与任职回报：manager_tenure.data 取“在管”为主，否则取第一条
        mt = fund.get("manager_tenure")
        chosen: dict[str, Any] | None = None
        if isinstance(mt, dict) and mt.get("ok") and isinstance(mt.get("data"), list):
            items = [it for it in (mt.get("data") or []) if isinstance(it, dict)]
            # 优先选择包含在管经理（ISINOFFICE 里含 '1'）的记录
            for it in items:
                isin = str(it.get("ISINOFFICE") or "")
                if "1" in isin:
                    chosen = it
                    break
            if chosen is None and items:
                chosen = items[0]

        if chosen:
            days = _parse_days(chosen.get("DAYS"))
            mgr_names = str(chosen.get("MGRNAME") or "").strip()
            pen = _parse_pct(chosen.get("PENAVGROWTH"))
            tenure_years = days / 365.0 if days > 0 else None
            if tenure_years is not None:
                # 如果是多经理，这里给出“组合记录”的年限（天天基金接口本身是一段任期记录）
                tenure_years_text = f"{tenure_years:.2f} 年（{mgr_names}）" if mgr_names else f"{tenure_years:.2f} 年"
            if pen is not None and days > 0:
                ann = _annualized_return(pen, days)
                if ann is not None:
                    tenure_ann_text = f"{ann * 100:.2f}%（任职回报{pen:.2f}%，{days}天）"
            elif days > 0:
                tenure_ann_text = "暂无数据（缺少任职回报字段）"

        return career_text, tenure_years_text, tenure_ann_text

    career_text, tenure_years_text, tenure_ann_text = _manager_metrics_text(fund_obj)

    # 定义详细字段及其可能的源字段名称（新增“费率”）
    standard_fields = [
        ("基金名称", ["基金名称", "基金简称", "名称"]),
        ("成立时间", ["成立时间", "成立日期", "设立日期"]),
        ("最新规模", ["最新规模", "基金规模", "规模", "资产净值"]),
        ("基金公司", ["基金公司", "基金管理人", "管理人"]),
        ("基金经理", ["基金经理", "经理"]),
        ("托管银行", ["托管银行", "基金托管人", "托管人"]),
        ("基金类型", ["基金类型", "类型", "基金分类"]),
        ("基金评级", ["基金评级", "评级", "晨星评级", "星级"]),
        ("投资策略", ["投资策略", "策略"]),
        ("投资目标", ["投资目标", "目标"]),
        ("基金经理从业经验", ["基金经理从业经验"]),
        ("基金经理管理本基金年限", ["基金经理管理本基金年限"]),
        ("基金经理管理本基金期间年化回报", ["基金经理管理本基金期间年化回报"]),
        ("费率", ["费率", "费率方面", "费率信息"]),
        ("业绩比较基准", ["业绩比较基准", "比较基准", "基准"]),
    ]
    
    # 构建表格行
    rows: list[dict[str, Any]] = []
    for field_name, source_keys in standard_fields:
        value = "-"
        # 尝试从多个可能的源字段中获取值
        for key in source_keys:
            if key in kv and kv[key]:
                value = kv[key]
                break
        
        # 特殊处理：经理相关 3 字段来自聚合模块
        if field_name == "基金经理从业经验":
            value = career_text
        elif field_name == "基金经理管理本基金年限":
            value = tenure_years_text
        elif field_name == "基金经理管理本基金期间年化回报":
            value = tenure_ann_text
        elif field_name == "基金评级" and value in {"-", "", "暂无评级"}:
            value = _rating_from_rating_info(fund_obj)
        # 特殊处理：费率优先由 detail_info 规则合成
        elif field_name == "费率" and value == "-":
            value = _compose_fee_summary(kv)
        
        rows.append({
            "字段": field_name,
            "内容": value
        })
    
    return {
        "id": f"standard_14_fields_{symbol}",
        "title": f"基金详细信息",
        "type": "table",
        "table": {
            "headers": ["字段", "内容"],
            "rows": rows
        },
    }


# ---------------------------------------------------------------------------
# 图表格式化
# ---------------------------------------------------------------------------

def format_asset_chart(fund_obj: dict[str, Any]) -> ChartConfig | None:
    """生成资产配置环形图（单只基金）。
    
    支持多种数据源：
    - AkShare: analysis.data (资产配置数据)
    - Skill: analysis.data, asset_allocation.data, detail_hold.data
    """
    sym = str(fund_obj.get("symbol") or "")

    # interpret: analysis.data 可能含资产配置；compare: asset_allocation.data
    analysis_records = _module_data(fund_obj.get("analysis"))
    alloc_dict = _module_data_dict(fund_obj.get("asset_allocation"))

    labels: list[str] = []
    values: list[float] = []

    # 尝试从 analysis records 提取（interpret skill + AkShare）
    if analysis_records:
        for r in analysis_records:
            if not isinstance(r, dict):
                continue
            # 支持多种字段名（AkShare + Skill）
            item = str(
                r.get("item") or 
                r.get("项目") or 
                r.get("资产类型") or 
                r.get("类型") or 
                r.get("type") or 
                ""
            )
            val = (
                r.get("value") or 
                r.get("比例") or 
                r.get("占比") or 
                r.get("占净值比例") or 
                r.get("ratio")
            )
            # 仅匹配资产配置相关行
            if item and any(k in item for k in ["股票", "债券", "现金", "基金", "其他", "银行", "货币"]):
                labels.append(item)
                values.append(_float_or(val))

    # 尝试从 asset_allocation dict 提取（compare skill）
    if not labels and alloc_dict:
        for key, val in alloc_dict.items():
            if key and any(k in key for k in ["股票", "债券", "现金", "基金", "其他", "银行", "货币"]):
                labels.append(key)
                values.append(_float_or(val))

    # 尝试从 detail_hold 提取（持仓明细作为兜底）
    if not labels:
        hold_records = _module_data(fund_obj.get("detail_hold"))
        if hold_records:
            for r in hold_records[:10]:
                if not isinstance(r, dict):
                    continue
                name = str(
                    r.get("资产类型") or
                    r.get("股票名称") or 
                    r.get("名称") or 
                    r.get("item") or 
                    r.get("name") or 
                    ""
                )
                ratio = (
                    r.get("仓位占比") or
                    r.get("占净值比例") or 
                    r.get("占比") or 
                    r.get("比例") or 
                    r.get("value") or 
                    r.get("ratio")
                )
                if name and ratio is not None:
                    labels.append(name)
                    values.append(_float_or(ratio))

    if not labels or not values:
        return None

    colors = DEFAULT_COLORS[: len(labels)]
    series = [
        {"name": labels[i], "value": values[i], "color": colors[i]}
        for i in range(len(labels))
    ]
    return {
        "id": f"asset_{sym}",
        "title": "资产配置",
        "type": "donut",
        "data": {"series": series},
    }


def format_nav_chart_from_akshare(
    nav_data: dict[str, Any],
    symbol: str,
) -> ChartConfig | None:
    """从 AkShare 净值数据生成折线图配置。
    
    解析 AkShare get_nav_data() 返回的时序净值数据，
    计算累计收益率，并进行数据降采样（最多 100 个点）。
    
    Args:
        nav_data: AkShare get_nav_data() 返回的数据，格式：
            {"ok": True, "data": [{"净值日期": "2024-01-01", "单位净值": 1.234, ...}, ...]}
        symbol: 基金代码
    
    Returns:
        ChartConfig 或 None（数据不足时）
    
    Example:
        >>> nav_data = {"ok": True, "data": [
        ...     {"净值日期": "2024-01-01", "单位净值": 1.0},
        ...     {"净值日期": "2024-01-02", "单位净值": 1.05},
        ... ]}
        >>> chart = format_nav_chart_from_akshare(nav_data, "000001")
        >>> assert chart["type"] == "line"
    """
    if not nav_data or not isinstance(nav_data, dict):
        return None
    
    if not nav_data.get("ok"):
        return None
    
    records = nav_data.get("data", [])
    if not isinstance(records, list) or len(records) < 2:
        return None
    
    # 提取日期和净值
    dates: list[str] = []
    nav_values: list[float] = []
    
    for r in records:
        if not isinstance(r, dict):
            continue
        date = r.get("净值日期") or r.get("日期")
        nav = r.get("单位净值") or r.get("净值")
        if date and nav is not None:
            dates.append(str(date))
            nav_values.append(_float_or(nav))
    
    if len(dates) < 2 or len(nav_values) < 2:
        return None
    
    # 计算累计收益率
    base_nav = nav_values[0]
    if base_nav <= 0:
        return None
    
    returns = [(v / base_nav - 1) * 100 for v in nav_values]
    
    # 数据降采样：如果数据点超过 100 个，均匀采样
    if len(dates) > 100:
        step = len(dates) // 100
        dates = dates[::step][:100]
        returns = returns[::step][:100]
    
    return {
        "id": f"nav_{symbol}",
        "title": "净值走势",
        "type": "line",
        "description": f"近{len(dates)}个交易日累计收益率",
        "data": {
            "xAxis": dates,
            "series": [{
                "name": symbol,
                "data": returns,
                "color": DEFAULT_COLORS[0],
            }],
        },
        "options": {
            "showLegend": True,
            "showGrid": True,
            "yAxisLabel": "累计收益率(%)",
        },
    }


def format_industry_chart(
    industry_data: dict[str, Any],
    symbol: str,
) -> ChartConfig | None:
    """从 AkShare 行业配置数据生成柱状图配置。
    
    解析 AkShare get_industry_allocation() 返回的行业配置数据，
    取前 10 大行业，生成柱状图配置。
    
    Args:
        industry_data: AkShare get_industry_allocation() 返回的数据，格式：
            {"ok": True, "data": [{"行业类别": "制造业", "占净值比例": 25.5, ...}, ...]}
        symbol: 基金代码
    
    Returns:
        ChartConfig 或 None（数据不足时）
    
    Example:
        >>> industry_data = {"ok": True, "data": [
        ...     {"行业类别": "制造业", "占净值比例": 25.5},
        ...     {"行业类别": "金融业", "占净值比例": 18.3},
        ... ]}
        >>> chart = format_industry_chart(industry_data, "000001")
        >>> assert chart["type"] == "bar"
    """
    if not industry_data or not isinstance(industry_data, dict):
        return None
    
    if not industry_data.get("ok"):
        return None
    
    records = industry_data.get("data", [])
    if not isinstance(records, list) or len(records) == 0:
        return None
    
    # 提取行业类别和占比
    industries: list[tuple[str, float]] = []
    
    for r in records:
        if not isinstance(r, dict):
            continue
        
        # 支持多种字段名
        industry = (
            r.get("行业类别") or 
            r.get("行业名称") or 
            r.get("行业") or 
            r.get("industry")
        )
        ratio = (
            r.get("占净值比例") or 
            r.get("占比") or 
            r.get("比例") or 
            r.get("ratio")
        )
        
        if industry and ratio is not None:
            industries.append((str(industry), _float_or(ratio)))
    
    if len(industries) == 0:
        return None
    
    # 按占比降序排序，取前 10 大行业
    industries.sort(key=lambda x: x[1], reverse=True)
    top_industries = industries[:10]
    
    labels = [ind[0] for ind in top_industries]
    values = [ind[1] for ind in top_industries]
    
    return {
        "id": f"industry_{symbol}",
        "title": "行业配置",
        "type": "bar",
        "description": f"前{len(labels)}大行业配置",
        "data": {
            "xAxis": labels,
            "series": [{
                "name": "占净值比例",
                "data": values,
                "color": DEFAULT_COLORS[0],
            }],
        },
        "options": {
            "showLegend": False,
            "showGrid": True,
            "yAxisLabel": "占净值比例(%)",
        },
    }


def format_holding_table(
    holding_data: dict[str, Any],
    symbol: str,
) -> TableSection | None:
    """从 AkShare 持仓明细数据生成表格配置。
    
    解析 AkShare get_portfolio_hold() 返回的持仓明细数据，
    取前 10 大重仓股，生成表格配置。
    
    Args:
        holding_data: AkShare get_portfolio_hold() 返回的数据，格式：
            {"ok": True, "data": [{"股票代码": "600519", "股票名称": "贵州茅台", 
             "占净值比例": 8.5, "持仓市值": 12500.0, ...}, ...]}
        symbol: 基金代码
    
    Returns:
        TableSection 或 None（数据不足时）
    
    Example:
        >>> holding_data = {"ok": True, "data": [
        ...     {"股票代码": "600519", "股票名称": "贵州茅台", "占净值比例": 8.5},
        ...     {"股票代码": "300750", "股票名称": "宁德时代", "占净值比例": 6.2},
        ... ]}
        >>> table = format_holding_table(holding_data, "000001")
        >>> assert table["type"] == "table"
    """
    if not holding_data or not isinstance(holding_data, dict):
        return None
    
    if not holding_data.get("ok"):
        return None
    
    records = holding_data.get("data", [])
    if not isinstance(records, list) or len(records) == 0:
        return None
    
    # 取前 10 大重仓股
    top_holdings = records[:10]
    
    rows: list[dict[str, Any]] = []
    for idx, r in enumerate(top_holdings, 1):
        if not isinstance(r, dict):
            continue
        
        # 支持多种字段名
        stock_code = (
            r.get("股票代码") or 
            r.get("代码") or 
            r.get("code") or 
            ""
        )
        stock_name = (
            r.get("股票名称") or 
            r.get("名称") or 
            r.get("name") or 
            ""
        )
        ratio = (
            r.get("占净值比例") or 
            r.get("占比") or 
            r.get("比例") or 
            r.get("ratio")
        )
        market_value = (
            r.get("持仓市值") or 
            r.get("市值") or 
            r.get("value")
        )
        
        # 至少需要股票名称或代码
        if not stock_code and not stock_name:
            continue
        
        row: dict[str, Any] = {"序号": idx}
        
        if stock_code:
            row["股票代码"] = str(stock_code)
        if stock_name:
            row["股票名称"] = str(stock_name)
        
        # 格式化占比
        if ratio is not None:
            ratio_val = _float_or(ratio)
            row["占净值比例"] = f"{ratio_val:.2f}%"
        else:
            row["占净值比例"] = "-"
        
        # 格式化市值
        if market_value is not None:
            mv_val = _float_or(market_value)
            if mv_val >= 10000:
                row["持仓市值"] = f"{mv_val / 10000:.2f}亿元"
            else:
                row["持仓市值"] = f"{mv_val:.2f}万元"
        else:
            row["持仓市值"] = "-"
        
        rows.append(row)
    
    if len(rows) == 0:
        return None
    
    # 动态生成表头（根据实际有的字段）
    headers = ["序号"]
    if any("股票代码" in row for row in rows):
        headers.append("股票代码")
    if any("股票名称" in row for row in rows):
        headers.append("股票名称")
    headers.extend(["占净值比例", "持仓市值"])
    
    return {
        "id": f"holding_{symbol}",
        "title": "前十大重仓股",
        "type": "table",
        "table": {
            "headers": headers,
            "rows": rows,
        },
    }


def format_nav_chart(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成净值走势折线图（多基金对比）。

    AkShare 的 achievement 数据通常是汇总指标而非时序数据，
    因此此函数将可用的各期收益指标按时间轴排列为折线。
    如果没有足够数据，返回 None。
    """
    time_keys = ["近1月", "近3月", "近6月", "近1年", "近3年", "成立来"]

    series_list: list[dict[str, Any]] = []
    available_keys: list[str] = []
    fund_kv_list: list[tuple[str, dict[str, str]]] = []

    for fund in funds:
        sym = str(fund.get("symbol") or "")
        ach_records = _module_data(fund.get("achievement"))
        if ach_records is None:
            perf = fund.get("performance")
            if isinstance(perf, dict):
                ach_records = _module_data(perf.get("achievement"))
        if not ach_records:
            continue
        kv = _kv_to_dict(ach_records)
        fund_kv_list.append((sym, kv))

    if not fund_kv_list:
        return None

    # 确定可用的时间轴
    for tk in time_keys:
        if any(tk in kv for _, kv in fund_kv_list):
            available_keys.append(tk)

    if len(available_keys) < 2:
        return None

    for idx, (sym, kv) in enumerate(fund_kv_list):
        data_points = [_float_or(kv.get(tk)) for tk in available_keys]
        color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        series_list.append({"name": sym, "data": data_points, "color": color})

    return {
        "id": "nav_trend",
        "title": "各期收益对比",
        "type": "line",
        "data": {"xAxis": available_keys, "series": series_list},
    }


def format_style_radar(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成投资风格雷达图。

    尝试从 analysis 模块提取风格数据（如大盘、中盘、小盘、成长、价值等）。
    """
    style_keywords = ["大盘", "中盘", "小盘", "成长", "价值", "平衡"]

    series_list: list[dict[str, Any]] = []
    found_indicators: list[str] = []

    for idx, fund in enumerate(funds):
        sym = str(fund.get("symbol") or "")
        analysis_records = _module_data(fund.get("analysis"))
        if not analysis_records:
            continue

        kv = _kv_to_dict(analysis_records)
        if not found_indicators:
            for sk in style_keywords:
                for k in kv:
                    if sk in k:
                        found_indicators.append(k)
                        break

        if not found_indicators:
            continue

        data_points = [_float_or(kv.get(ind)) for ind in found_indicators]
        if all(v == 0 for v in data_points):
            continue

        color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        series_list.append({"name": sym, "data": data_points, "color": color})

    if not found_indicators or not series_list:
        return None

    max_val = max(max(s["data"]) for s in series_list) if series_list else 100
    max_val = max(max_val, 1)
    indicators = [{"name": ind, "max": round(max_val * 1.2, 1)} for ind in found_indicators]

    return {
        "id": "style_radar",
        "title": "投资风格对比",
        "type": "radar",
        "data": {"indicators": indicators, "series": series_list},
    }


def format_return_bar_chart(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成收益率柱状图对比。
    
    展示各基金在不同时间段的收益率对比（近1月、近3月、近6月、近1年）。
    """
    if not funds:
        return None

    time_periods = ["近1月", "近3月", "近6月", "近1年"]
    series_list: list[dict[str, Any]] = []

    for idx, fund in enumerate(funds):
        sym = str(fund.get("symbol") or "")
        ach_records = _module_data(fund.get("achievement"))
        if ach_records is None:
            perf = fund.get("performance")
            if isinstance(perf, dict):
                ach_records = _module_data(perf.get("achievement"))
        if not ach_records:
            continue

        kv = _kv_to_dict(ach_records)
        data_points = [_float_or(kv.get(tp)) for tp in time_periods]
        
        # 至少有一个非零值才添加
        if any(v != 0 for v in data_points):
            color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
            series_list.append({"name": sym, "data": data_points, "color": color})

    if not series_list:
        return None

    return {
        "id": "return_bar",
        "title": "各期收益率对比",
        "type": "bar",
        "data": {"xAxis": time_periods, "series": series_list},
    }


def format_fee_donut_chart(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成费率环形图。
    
    展示第一只基金的费率结构（管理费、托管费、销售服务费等）。
    """
    if not funds:
        return None

    # 只展示第一只基金的费率结构
    fund = funds[0]
    sym = str(fund.get("symbol") or "")
    
    records = _module_data(fund.get("basic_info")) or _module_data(fund.get("detail_info")) or []
    kv = _kv_to_dict(records)

    # 提取费率数据
    fee_items = [
        ("管理费率", "管理费率"),
        ("托管费率", "托管费率"),
        ("销售服务费率", "销售服务费率"),
        ("申购费率", "申购费率"),
    ]

    data_points: list[dict[str, Any]] = []
    for idx, (key, name) in enumerate(fee_items):
        val_str = kv.get(key, "")
        if val_str and val_str != "-":
            # 尝试提取数字（去除%等符号）
            val = _float_or(val_str.replace("%", "").replace("‰", ""))
            if val > 0:
                color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
                data_points.append({"name": name, "value": val, "color": color})

    if not data_points:
        return None

    return {
        "id": f"fee_donut_{sym}",
        "title": f"{sym} 费率结构",
        "type": "donut",
        "data": {"series": data_points},
    }


def format_risk_indicator_chart(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成风险指标柱状图。
    
    展示各基金的风险指标对比（最大回撤、波动率、夏普比率）。
    """
    if not funds:
        return None

    risk_metrics = ["最大回撤", "波动率", "夏普比率"]
    series_list: list[dict[str, Any]] = []

    for idx, fund in enumerate(funds):
        sym = str(fund.get("symbol") or "")
        ach_records = _module_data(fund.get("achievement"))
        if ach_records is None:
            perf = fund.get("performance")
            if isinstance(perf, dict):
                ach_records = _module_data(perf.get("achievement"))
        if not ach_records:
            continue

        kv = _kv_to_dict(ach_records)
        data_points = []
        for metric in risk_metrics:
            val = _float_or(kv.get(metric))
            # 最大回撤通常是负数，取绝对值便于展示
            if metric == "最大回撤":
                val = abs(val)
            data_points.append(val)
        
        if any(v != 0 for v in data_points):
            color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
            series_list.append({"name": sym, "data": data_points, "color": color})

    if not series_list:
        return None

    return {
        "id": "risk_indicator",
        "title": "风险指标对比",
        "type": "bar",
        "data": {"xAxis": risk_metrics, "series": series_list},
    }


# ---------------------------------------------------------------------------
# 文本 Section 辅助
# ---------------------------------------------------------------------------

_SECTION_PATTERN = re.compile(r"【(.+?)】")


def _split_llm_text_to_sections(llm_text: str) -> list[TextSection]:
    """将 LLM 输出的文本按【xxx】标题拆分为多个 TextSection。"""
    if not llm_text or not llm_text.strip():
        return []

    # 去掉 <think> 块
    text = re.sub(r"<think>[\s\S]*?</think>", "", llm_text, flags=re.IGNORECASE).strip()
    if not text:
        return []

    parts = _SECTION_PATTERN.split(text)
    sections: list[TextSection] = []
    idx = 0

    # parts[0] = before first 【】 (usually empty or summary)
    if parts[0].strip():
        sections.append({
            "id": "intro",
            "title": "概述",
            "type": "text",
            "content": parts[0].strip(),
        })
    idx = 1

    while idx < len(parts) - 1:
        title = parts[idx].strip()
        content = parts[idx + 1].strip() if idx + 1 < len(parts) else ""
        sid = re.sub(r"\W+", "_", title)
        tags: list[str] = []
        if "风险" in title:
            tags.append("风险提示")
        elif "结论" in title:
            tags.append("专家观点")

        if content:
            section: TextSection = {"id": sid, "title": title, "type": "text", "content": content}
            if tags:
                section["tags"] = tags
            sections.append(section)
        idx += 2

    return sections


def _extract_summary(llm_text: str) -> str:
    """从 LLM 文本中提取摘要（取第一段或前 100 字）。"""
    text = re.sub(r"<think>[\s\S]*?</think>", "", llm_text or "", flags=re.IGNORECASE).strip()
    if not text:
        return ""
    first_section = _SECTION_PATTERN.split(text)[0].strip()
    if first_section and len(first_section) > 10:
        return first_section[:200]
    lines = text.split("\n")
    for line in lines:
        clean = line.strip()
        if clean and len(clean) > 10:
            return clean[:200]
    return text[:200]


STRUCTURED_PERF_DELIM = "---\n"


def _achievement_val_pct(val: Any) -> str:
    """将业绩接口中的数值格式化为百分比字符串（兼容 AkShare 雪球宽表）。"""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.endswith("%"):
        return s
    try:
        return f"{float(s):.2f}%"
    except ValueError:
        return s


def _normalize_pct_text(val: Any) -> str:
    """将风险指标中的百分比类数值统一规范为带 % 的文本。"""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.endswith("%"):
        return s
    try:
        return f"{float(s):.2f}%"
    except ValueError:
        return s


def _extract_analysis_risk_metrics(fund: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """
    从 analysis 宽表中提取风险指标。

    AkShare `fund_individual_analysis_xq` 常见结构为宽表：
    周期 / 年化波动率 / 年化夏普比率 / 最大回撤 ...
    这里优先取“近1年”，其次取第一条有效记录。
    """
    rows = _module_data(fund.get("analysis"))
    if not rows:
        return "", {}
    dict_rows = [r for r in rows if isinstance(r, dict)]
    if not dict_rows:
        return "", {}
    chosen = next((r for r in dict_rows if str(r.get("周期") or "").strip() == "近1年"), dict_rows[0])
    chosen_period = str(chosen.get("周期") or "").strip()
    volatility = _normalize_pct_text(chosen.get("年化波动率") or chosen.get("波动率") or chosen.get("年化波动"))
    sharpe = str(chosen.get("年化夏普比率") or chosen.get("夏普比率") or chosen.get("夏普") or "").strip()
    drawdown = _normalize_pct_text(chosen.get("最大回撤"))
    out: dict[str, str] = {}
    if volatility:
        out["年化波动率"] = volatility
    if sharpe:
        out["夏普比率"] = sharpe
    if drawdown:
        out["最大回撤"] = drawdown
    return chosen_period, out


def _extract_analysis_risk_matrix(fund: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从 analysis 宽表中提取“按周期”的风险指标矩阵。
    返回行列表：{"周期":..., "年化波动率": "...%", "年化夏普比率": "...", "最大回撤": "...%"}。
    """
    rows = _module_data(fund.get("analysis"))
    if not rows:
        return []
    dict_rows = [r for r in rows if isinstance(r, dict)]
    if not dict_rows:
        return []
    out: list[dict[str, Any]] = []
    for r in dict_rows:
        period = str(r.get("周期") or "").strip()
        if not period:
            continue
        out.append({
            "周期": period,
            "年化波动率": _normalize_pct_text(r.get("年化波动率") or r.get("波动率") or r.get("年化波动")),
            "年化夏普比率": str(r.get("年化夏普比率") or r.get("夏普比率") or r.get("夏普") or "").strip(),
            "最大回撤": _normalize_pct_text(r.get("最大回撤")),
        })
    return out


def format_risk_metrics_matrix_section(fund: dict[str, Any]) -> TableSection | None:
    """单基金：风险指标矩阵（按周期）。给基金经理使用，口径清晰、可复制。"""
    sym = str(fund.get("symbol") or "")
    matrix = _extract_analysis_risk_matrix(fund)
    if not matrix:
        return None

    # 常用展示顺序：近1年/近3年/成立以来，其他周期放后面（若存在）
    order = ["近6月", "近1年", "近2年", "近3年", "近5年", "成立以来"]
    rank = {p: i for i, p in enumerate(order)}
    matrix.sort(key=lambda r: rank.get(str(r.get("周期") or ""), 999))

    headers = ["周期", "年化波动率（该周期）", "年化夏普比率（该周期）", "最大回撤（该周期）", "备注"]
    rows: list[dict[str, Any]] = []
    cell_classes: dict[str, str] = {}
    cell_tooltips: dict[str, str] = {}

    def set_cell(i: int, h: str, cls: str | None = None, tip: str | None = None) -> None:
        key = f"{i}|{h}"
        if cls:
            cell_classes[key] = cls
        if tip:
            cell_tooltips[key] = tip

    for i, r in enumerate(matrix):
        period = str(r.get("周期") or "")
        vol = str(r.get("年化波动率") or "").strip()
        sharpe = str(r.get("年化夏普比率") or "").strip()
        dd = str(r.get("最大回撤") or "").strip()

        note_parts: list[str] = []
        if not vol:
            vol = "—"
            note_parts.append("年化波动率缺失（数据源未提供）")
            set_cell(i, "年化波动率（该周期）", "cell-muted")
        if not sharpe:
            sharpe = "—"
            note_parts.append("年化夏普比率缺失（数据源未提供）")
            set_cell(i, "年化夏普比率（该周期）", "cell-muted")
        if not dd:
            dd = "—"
            note_parts.append("最大回撤缺失（数据源未提供）")
            set_cell(i, "最大回撤（该周期）", "cell-muted")

        note = "；".join(note_parts) if note_parts else ""
        rows.append({
            "周期": period,
            "年化波动率（该周期）": vol,
            "年化夏普比率（该周期）": sharpe,
            "最大回撤（该周期）": dd,
            "备注": note,
        })

        set_cell(i, "年化波动率（该周期）", tip=f"年化波动率：收益率波动程度（越低越稳）。口径=该行周期（{period}）。")
        set_cell(i, "年化夏普比率（该周期）", tip=f"年化夏普比率：单位风险收益（越高越好）。口径=该行周期（{period}）。")
        set_cell(i, "最大回撤（该周期）", tip=f"最大回撤：峰谷最大跌幅（越小越好）。口径=该行周期（{period}）。")

    return {
        "id": f"risk_matrix_{sym}",
        "title": "风险指标矩阵（按周期）",
        "type": "table",
        "description": "口径说明：按“周期”统计的年化波动率/年化夏普比率/最大回撤。用于评估风险-收益质量与稳定性。",
        "table": {
            "headers": headers,
            "rows": rows,
            "cell": {"classes": cell_classes, "tooltips": cell_tooltips},
        },
    }


def format_volatility_trend_chart(fund: dict[str, Any]) -> ChartConfig | None:
    """单基金：年化波动率随周期变化趋势（折线）。"""
    sym = str(fund.get("symbol") or "")
    matrix = _extract_analysis_risk_matrix(fund)
    if not matrix:
        return None
    order = ["近6月", "近1年", "近2年", "近3年", "近5年", "成立以来"]
    rank = {p: i for i, p in enumerate(order)}
    matrix.sort(key=lambda r: rank.get(str(r.get("周期") or ""), 999))

    x: list[str] = []
    y: list[float | None] = []
    for r in matrix:
        period = str(r.get("周期") or "").strip()
        vol_s = str(r.get("年化波动率") or "").strip().replace("%", "")
        if not period:
            continue
        x.append(period)
        y.append(_float_or_none(vol_s))

    if len(x) < 2:
        return None

    return {
        "id": f"vol_trend_{sym}",
        "title": "年化波动率趋势（按周期）",
        "type": "line",
        "description": "用于观察不同周期下的波动水平变化（数值越低通常越稳健）。",
        "data": {"xAxis": x, "series": [{"name": sym or "本基金", "data": y, "color": DEFAULT_COLORS[0]}]},
    }


def _build_structured_achievement_block(fund: dict[str, Any]) -> str:
    """从 achievement 模块生成结构化业绩行，供前端 PerformanceSummary 稳定解析（含历年最大回撤）。"""
    rows = _module_data(fund.get("achievement"))
    if not rows:
        return ""
    first = next((r for r in rows if isinstance(r, dict)), None)
    if not first:
        return ""
    lines: list[str] = []

    # AkShare fund_individual_achievement_xq：宽表（周期 / 本产品区间收益 / 周期收益同类排名 / 本产品最大回撒）
    if "周期" in first or "本产品区间收益" in first:
        for r in rows:
            if not isinstance(r, dict):
                continue
            period = str(r.get("周期") or "").strip()
            if not period:
                continue
            ret = _achievement_val_pct(r.get("本产品区间收益"))
            rank = str(r.get("周期收益同类排名") or "").strip()
            dd = _achievement_val_pct(
                r.get("本产品最大回撒") or r.get("本产品最大回撤")
            )
            typ = str(r.get("业绩类型") or "").strip()
            if typ == "年度业绩":
                if len(period) == 4 and period.isdigit():
                    parts: list[str] = [f"{period}年收益率：{ret}"]
                    if rank:
                        parts.append(f"同类排名：{rank}")
                    if dd:
                        parts.append(f"最大回撤：{dd}")
                    lines.append("，".join(parts))
                elif period in ("今年以来", "今年来", "成立来", "成立以来"):
                    label = "今年以来" if period in ("今年来", "今年以来") else "成立以来"
                    parts = [f"{label}收益率：{ret}"]
                    if rank:
                        parts.append(f"同类排名：{rank}")
                    if dd:
                        parts.append(f"最大回撤：{dd}")
                    lines.append("，".join(parts))
            elif typ == "阶段业绩" and period in (
                "近1月",
                "近3月",
                "近6月",
                "近1年",
                "近2年",
                "近3年",
                "近5年",
            ):
                parts = [f"{period}收益率：{ret}"]
                if rank:
                    parts.append(f"同类排名：{rank}")
                lines.append("，".join(parts))
    else:
        kv = _kv_to_dict(rows)
        ordered = [
            "近1月",
            "近3月",
            "近6月",
            "近1年",
            "近3年",
            "近5年",
            "今年来",
            "今年以来",
            "成立来",
            "成立以来",
            "夏普比率",
            "最大回撤",
            "波动率",
            "年化波动率",
        ]
        for k in ordered:
            if k not in kv:
                continue
            v = kv[k]
            if k in ("夏普比率", "最大回撤", "波动率", "年化波动率"):
                lines.append(f"{k}：{v}")
            else:
                lines.append(f"{k}收益率：{v}")

    if not lines:
        return ""
    chosen_period, analysis_metrics = _extract_analysis_risk_metrics(fund)
    existing_text = "\n".join(lines)
    prefix = f"{chosen_period}" if chosen_period else ""
    if analysis_metrics.get("夏普比率") and "夏普比率" not in existing_text and "夏普：" not in existing_text:
        lines.append(f"{prefix}年化夏普比率：{analysis_metrics['夏普比率']}" if prefix else f"年化夏普比率：{analysis_metrics['夏普比率']}")
    if analysis_metrics.get("年化波动率") and "年化波动率" not in existing_text and "波动率" not in existing_text:
        lines.append(f"{prefix}年化波动率：{analysis_metrics['年化波动率']}" if prefix else f"年化波动率：{analysis_metrics['年化波动率']}")
    if analysis_metrics.get("最大回撤") and "最大回撤" not in existing_text:
        lines.append(f"{prefix}最大回撤：{analysis_metrics['最大回撤']}" if prefix else f"最大回撤：{analysis_metrics['最大回撤']}")
    return "【结构化业绩数据】\n" + "\n".join(lines) + "\n"


def _inject_structured_achievement_into_perf_sections(
    sections: list[Any],
    fund: dict[str, Any],
) -> None:
    """在【业绩表现】文本前注入结构化行，便于前端解析；LLM 原文保留在 --- 之后。"""
    block = _build_structured_achievement_block(fund)
    if not block:
        return
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        if sec.get("type") != "text":
            continue
        title = str(sec.get("title") or "")
        if "业绩" not in title:
            continue
        prev = str(sec.get("content") or "")
        sec["content"] = block + STRUCTURED_PERF_DELIM + prev
        break


# ---------------------------------------------------------------------------
# 顶层构建
# ---------------------------------------------------------------------------

def build_single_output(
    supplier_data: Any,
    llm_text: str,
) -> FundAnalysisOutput:
    """组装单基金解读的 FundAnalysisOutput。"""
    payload = _extract_payload(supplier_data)
    funds = _extract_funds(payload) if payload else []

    # 用户要求：不再输出卡片（cards）
    cards: list[InfoCard] = []
    charts: list[ChartConfig] = []
    table_sections: list[Any] = []

    for fund in funds:
        # cards disabled by requirement
        chart = format_asset_chart(fund)
        if chart:
            charts.append(chart)
        
        # 添加14字段标准信息表格
        standard_table = format_standard_14_fields_table(fund)
        if standard_table:
            table_sections.append(standard_table)

        # 风险指标矩阵（按周期）
        risk_matrix = format_risk_metrics_matrix_section(fund)
        if risk_matrix:
            table_sections.append(risk_matrix)

        # 可选增强：年化波动率趋势
        vol_trend = format_volatility_trend_chart(fund)
        if vol_trend:
            charts.append(vol_trend)

    # 单基金也可展示收益走势
    nav = format_nav_chart(funds)
    if nav:
        charts.append(nav)

    # 雷达图（有数据时才展示）
    radar = format_style_radar(funds)
    if radar:
        charts.append(radar)

    # LLM 文本拆分为 sections
    text_sections: list[Any] = _split_llm_text_to_sections(llm_text)
    fund0 = funds[0] if funds else None
    if fund0:
        _inject_structured_achievement_into_perf_sections(text_sections, fund0)
    perf_sections = [
        s for s in text_sections
        if isinstance(s, dict) and s.get("type") == "text" and "业绩" in str(s.get("title") or "")
    ]
    ach_rows = _module_data(fund0.get("achievement")) if isinstance(fund0, dict) else None
    analysis_rows = _module_data(fund0.get("analysis")) if isinstance(fund0, dict) else None
    analysis_kv = _kv_to_dict(analysis_rows) if isinstance(analysis_rows, list) else {}
    analysis_keys = list(analysis_kv.keys())[:20]
    analysis_first_row_keys = list((analysis_rows[0].keys() if analysis_rows and isinstance(analysis_rows[0], dict) else []))[:20] if isinstance(analysis_rows, list) else []
    analysis_first_row_preview = {str(k): str((analysis_rows[0] or {}).get(k))[:80] for k in analysis_first_row_keys[:8]} if isinstance(analysis_rows, list) and analysis_rows and isinstance(analysis_rows[0], dict) else {}
    analysis_has_sharpe = any("夏普" in str(k) or "sharpe" in str(k).lower() for k in analysis_keys)
    analysis_has_volatility = any("波动" in str(k) or "vol" in str(k).lower() for k in analysis_keys)
    analysis_sharpe_value = next((str(v) for k, v in analysis_kv.items() if "夏普" in str(k) or "sharpe" in str(k).lower()), "")
    analysis_volatility_value = next((str(v) for k, v in analysis_kv.items() if "波动" in str(k) or "vol" in str(k).lower()), "")
    struct_block = _build_structured_achievement_block(fund0) if isinstance(fund0, dict) else ""
    struct_lines = len(struct_block.splitlines()) if struct_block else 0
    # 合并: 先表格，后文本
    all_sections: list[Any] = table_sections + text_sections

    summary = _extract_summary(llm_text)

    return {
        "type": FUND_ANALYSIS_TYPE,
        "mode": "single",
        "summary": summary,
        "cards": cards,
        "sections": all_sections,
        "charts": charts,
        "text": llm_text,
    }


def build_compare_output(
    supplier_data: Any,
    llm_text: str,
) -> FundAnalysisOutput:
    """组装基金对比的 FundAnalysisOutput。"""
    payload = _extract_payload(supplier_data)
    funds = _extract_funds(payload) if payload else []

    # 用户要求：不再输出卡片（cards）
    cards: list[InfoCard] = []
    charts: list[ChartConfig] = []
    table_sections: list[Any] = []

    for fund in funds:
        # cards disabled by requirement
        
        # 为每只基金添加14字段标准信息表格
        standard_table = format_standard_14_fields_table(fund)
        if standard_table:
            table_sections.append(standard_table)

    # 对比表格 - 增加基本信息表格
    if len(funds) >= 2:
        # 基本信息对比
        basic_table = format_basic_info_table(funds)
        if basic_table:
            table_sections.append(basic_table)
        
        # 业绩对比
        perf_table = format_performance_table(funds)
        if perf_table:
            table_sections.append(perf_table)
        
        # 费率对比
        fee_table = format_fee_table(funds)
        if fee_table:
            table_sections.append(fee_table)

    # 图表 - 增加更多图表类型
    # 1. 净值走势折线图
    nav = format_nav_chart(funds)
    if nav:
        charts.append(nav)
    
    # 2. 收益率柱状图
    return_bar = format_return_bar_chart(funds)
    if return_bar:
        charts.append(return_bar)
    
    # 3. 风险指标柱状图
    risk_bar = format_risk_indicator_chart(funds)
    if risk_bar:
        charts.append(risk_bar)
    
    # 4. 投资风格雷达图
    radar = format_style_radar(funds)
    if radar:
        charts.append(radar)
    
    # 5. 资产配置饼图（每只基金）
    for fund in funds:
        chart = format_asset_chart(fund)
        if chart:
            charts.append(chart)
    
    # 6. 费率环形图（第一只基金）
    if funds:
        fee_donut = format_fee_donut_chart(funds)
        if fee_donut:
            charts.append(fee_donut)

    # LLM 文本 sections
    text_sections = _split_llm_text_to_sections(llm_text)

    # 合并: 先表格，后文本
    all_sections: list[Any] = table_sections + text_sections

    summary = _extract_summary(llm_text)

    return {
        "type": FUND_ANALYSIS_TYPE,
        "mode": "compare",
        "summary": summary,
        "cards": cards,
        "sections": all_sections,
        "charts": charts,
        "text": llm_text,
    }

    # 合并: 先表格，后文本
    all_sections: list[Any] = table_sections + text_sections

    summary = _extract_summary(llm_text)

    return {
        "type": FUND_ANALYSIS_TYPE,
        "mode": "compare",
        "summary": summary,
        "cards": cards,
        "sections": all_sections,
        "charts": charts,
        "text": llm_text,
    }


# ---------------------------------------------------------------------------
# 安全解析：从字符串中提取 FundAnalysisOutput
# ---------------------------------------------------------------------------

def try_parse_fund_analysis(text: str) -> dict[str, Any] | None:
    """尝试将字符串解析为 FundAnalysisOutput dict，失败返回 None。"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
        if is_fund_analysis(obj):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def extract_text_for_compliance(reply_text: str) -> str:
    """从 reply_text 中提取纯文本用于合规检查。

    如果 reply_text 是 fund_analysis JSON，提取 text 字段；否则原样返回。
    """
    parsed = try_parse_fund_analysis(reply_text)
    if parsed:
        return parsed.get("text") or parsed.get("summary") or reply_text
    return reply_text
