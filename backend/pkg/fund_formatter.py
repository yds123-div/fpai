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


def extract_funds(supplier_data: Any) -> list[dict[str, Any]]:
    """从 supplier_data 提取基金列表（公共 helper，供 collector 等复用）。

    统一 payload 形状的提取入口（``_extract_payload`` + ``_extract_funds``），
    避免调用方各自镜像这套逻辑（Duplicated Code -> Shotgun Surgery）。
    """
    payload = _extract_payload(supplier_data)
    if payload is None:
        return []
    return _extract_funds(payload)


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

    # 收集每只基金的业绩指标
    perf_data: dict[str, dict[str, str]] = {}
    for fund in funds:
        sym = str(fund.get("symbol") or "")
        # 支持 AkShare 和 Skill 两种格式
        ach_records = _module_data(fund.get("achievement"))
        if ach_records is None:
            perf = fund.get("performance")
            if isinstance(perf, dict):
                ach_records = _module_data(perf.get("achievement"))
        if not ach_records:
            continue
        kv = _kv_to_dict(ach_records)
        perf_data[sym] = kv

    if not perf_data:
        return None

    # 扩展优先级指标列表，增加更多维度
    priority = [
        "近1月", "近3月", "近6月", "近1年", "近2年", "近3年", "近5年",
        "今年来", "成立来",
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
    # 增加显示指标数量到25个
    for metric in all_metrics[:25]:
        row: dict[str, Any] = {"指标": metric}
        for sym in symbols:
            row[sym] = perf_data.get(sym, {}).get(metric, "-")
        rows.append(row)

    return {
        "id": "performance_compare",
        "title": "业绩对比",
        "type": "table",
        "table": {"headers": headers, "rows": rows, "highlight": symbols},
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
    """格式化基金详细信息表格。

    输出字段包含基金基础信息、评级信息、经理维度指标、费率与业绩基准；
    费率字段采用固定模板输出并带回退推断。

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

    # 若基础取数模块超时/失败，仍返回“空骨架”表格，避免前端误判为“没有基金/没有详细信息”
    # 至少保证基金代码可见，其他字段用 "-" 占位，并提示用户稍后重试。
    if not kv:
        rows = [{"字段": "基金代码", "内容": symbol}]
        for field_name in [
            "基金名称",
            "成立时间",
            "最新规模",
            "基金公司",
            "基金经理",
            "托管银行",
            "基金类型",
            "基金评级",
            "费率",
            "业绩比较基准",
        ]:
            rows.append({"字段": field_name, "内容": "-"})
        rows.append({"字段": "提示", "内容": "基金详细信息取数超时或失败，已展示可用字段；建议稍后重试。"})
        return {
            "id": f"standard_14_fields_{symbol}",
            "title": "基金详细信息",
            "type": "table",
            "table": {"headers": ["字段", "内容"], "rows": rows},
        }
    
    def _compose_fee_summary(kv_data: dict[str, str]) -> str:
        """严格固定模板输出费率，并对缺失分段做回退推断。"""

        def _normalize_percent(raw: Any) -> str:
            s = str(raw or "").strip()
            if not s:
                return "暂无数据"
            if "免收" in s:
                return "0%"
            m = re.search(r"(-?\d+(?:\.\d+)?)", s)
            if not m:
                return s
            try:
                return f"{float(m.group(1)):g}%"
            except Exception:
                return s

        def _pick_first_by_keywords(*keywords: str) -> str | None:
            for k, v in kv_data.items():
                key = str(k).strip()
                if all(kw in key for kw in keywords):
                    return _normalize_percent(v)
            return None

        def _is_redeem_key(key: str) -> bool:
            return ("赎回" in key) or ("持有" in key)

        management_fee = (
            _normalize_percent(kv_data.get("管理费率"))
            if kv_data.get("管理费率")
            else None
        )
        if not management_fee:
            management_fee = (
                _normalize_percent(kv_data.get("管理费"))
                if kv_data.get("管理费")
                else None
            )
        if not management_fee:
            management_fee = _pick_first_by_keywords("管理", "费")
        if not management_fee:
            management_fee = "暂无数据"

        custody_fee = (
            _normalize_percent(kv_data.get("托管费率"))
            if kv_data.get("托管费率")
            else None
        )
        if not custody_fee:
            custody_fee = (
                _normalize_percent(kv_data.get("托管费"))
                if kv_data.get("托管费")
                else None
            )
        if not custody_fee:
            custody_fee = _pick_first_by_keywords("托管", "费")
        if not custody_fee:
            custody_fee = "暂无数据"

        norm: dict[str, str] = {}
        for k, v in kv_data.items():
            key = str(k).strip()
            if not key:
                continue
            norm[key] = "0%" if "免收" in key else _normalize_percent(v)

        redeem_7d: str | None = None
        redeem_1y: str | None = None
        redeem_2y: str | None = None

        def _parse_day_interval(key: str) -> tuple[float, float] | None:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*天\s*[<≤]\s*持有期限\s*[<≤]\s*(\d+(?:\.\d+)?)\s*天",
                key,
            )
            if not m:
                return None
            try:
                left = float(m.group(1))
                right = float(m.group(2))
            except Exception:
                return None
            if right <= left:
                return None
            return (left, right)

        for key, val in norm.items():
            if not _is_redeem_key(key):
                continue
            interval = _parse_day_interval(key)
            if interval:
                left, right = interval
                if right <= 7:
                    redeem_7d = redeem_7d or val
                elif left >= 7 and right <= 365:
                    redeem_1y = redeem_1y or val
                elif left >= 365 and right <= 730:
                    redeem_2y = redeem_2y or val
            if ("7天内" in key) or ("7日内" in key):
                redeem_7d = redeem_7d or val
            if (
                ("7日-1年" in key)
                or ("7天-1年" in key)
                or ("7-365天" in key)
                or ("30天-1年" in key)
                or ("7-30天" in key)
                or ("7至30天" in key)
                or ("7天-30天" in key)
            ):
                redeem_1y = redeem_1y or val
            if ("1-2年" in key) or ("1年-2年" in key) or ("365-730天" in key):
                redeem_2y = redeem_2y or val

        cands = {k: v for k, v in norm.items() if _is_redeem_key(k)}

        def _pick_by_priority(patterns: list[str]) -> str | None:
            for p in patterns:
                for k, v in cands.items():
                    if p in k:
                        return v
            return None

        if not redeem_1y:
            redeem_1y = _pick_by_priority(
                [
                    "7-30天",
                    "7至30天",
                    "7天-30天",
                    "30天-1年",
                    "30日-1年",
                    "30天以上",
                    "30日以上",
                    "1年以内",
                    "1年以上",
                ]
            )
        if not redeem_2y:
            redeem_2y = _pick_by_priority(["1年-2年", "365-730天", "2年以上", "1年以上"])
        if not redeem_7d:
            redeem_7d = _pick_by_priority(["7天", "7日", "30天以内", "30日以内", "30天", "30日"])

        redeem_candidate_keys = [k for k in cands.keys()]
        if redeem_candidate_keys and not any([redeem_7d, redeem_1y, redeem_2y]):
            logger.warning(
                "[FEE_DEBUG] redemption tiers unresolved; keys=%s",
                redeem_candidate_keys[:20],
            )
        else:
            logger.info(
                "[FEE_DEBUG] redemption tier mapping resolved; 7d=%s, 1y=%s, 2y=%s, keys=%s",
                redeem_7d,
                redeem_1y,
                redeem_2y,
                redeem_candidate_keys[:20],
            )

        redeem_7d = redeem_7d or "暂无数据"
        redeem_1y = redeem_1y or "暂无数据"
        redeem_2y = redeem_2y or "暂无数据"

        return (
            f"费率方面：管理费 {management_fee}/年，托管费 {custody_fee}/年；"
            f"赎回费：7日内 {redeem_7d}，7日-1年 {redeem_1y}，1-2年 {redeem_2y}"
        )

    def _rating_from_rating_info(fund: dict[str, Any]) -> str:
        """提取第三方机构评级明细（上海证券/招商证券/济安金信）。"""
        ri = fund.get("rating_info")
        if not isinstance(ri, dict):
            return "暂无该项数据"
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
                    return "暂无该项数据"
            return "暂无该项数据"
        data = ri.get("data")
        if not isinstance(data, dict):
            return "暂无该项数据"

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
        return " | ".join(parts) if parts else "暂无该项数据"

    def _composite_rating_status(third_party_rating: str) -> str:
        """统一综合评级口径，避免与第三方分项评级冲突。"""
        if third_party_rating and third_party_rating != "暂无该项数据":
            return "暂无统一综合评级（当前仅提供第三方机构分项评级）"
        return "暂无统一综合评级"

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
        ("第三方评级（机构）", ["基金评级", "评级", "晨星评级", "星级"]),
        ("综合评级", ["综合评级"]),
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
        elif field_name == "第三方评级（机构）":
            if value in {"-", "", "暂无评级"}:
                value = _rating_from_rating_info(fund_obj)
        elif field_name == "综合评级":
            third_party_rating = next(
                (str(row.get("内容") or "") for row in rows if row.get("字段") == "第三方评级（机构）"),
                "暂无该项数据",
            )
            value = _composite_rating_status(third_party_rating)
        # 特殊处理：费率使用固定模板（含回退推断）
        elif field_name == "费率":
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
    fund_kv_list: list[tuple[str, dict[str, str], list[dict[str, Any]]]] = []

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
        fund_kv_list.append((sym, kv, ach_records))

    if not fund_kv_list:
        return None

    # 确定可用的时间轴
    for tk in time_keys:
        if any(tk in kv for _, kv, _ in fund_kv_list):
            available_keys.append(tk)

    if len(available_keys) < 2:
        return None

    for idx, (sym, kv, _) in enumerate(fund_kv_list):
        data_points = [_float_or(kv.get(tk)) for tk in available_keys]
        color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        series_list.append({"name": sym, "data": data_points, "color": color})

    return {
        "id": "nav_trend",
        "title": "各期收益对比",
        "type": "line",
        "data": {"xAxis": available_keys, "series": series_list},
    }


def format_volatility_trend_chart(funds: list[dict[str, Any]]) -> ChartConfig | None:
    """生成年化波动率趋势折线图（按周期）。"""
    if not funds:
        return None

    def _period_order(label: str) -> tuple[int, int]:
        l = (label or "").strip()
        order = {"近1月": 1, "近3月": 2, "近6月": 3, "近1年": 4, "近2年": 5, "近3年": 6, "近5年": 7, "成立以来": 8}
        if l in order:
            return (0, order[l])
        if l.isdigit() and len(l) == 4:
            return (1, -int(l))
        return (2, 0)

    per_fund: list[tuple[str, dict[str, float]]] = []
    all_periods: set[str] = set()
    for fund in funds:
        sym = str(fund.get("symbol") or "")
        analysis_records = _module_data(fund.get("analysis"))
        if not analysis_records:
            continue
        pmap: dict[str, float] = {}
        for r in analysis_records:
            if not isinstance(r, dict):
                continue
            p = str(r.get("周期") or "").strip()
            if not p:
                continue
            raw = r.get("年化波动率") or r.get("波动率")
            try:
                v = float(str(raw).replace("%", "").strip())
            except (TypeError, ValueError):
                continue
            pmap[p] = v
        if pmap:
            per_fund.append((sym, pmap))
            all_periods.update(pmap.keys())

    if not per_fund:
        return None
    x_axis = sorted([p for p in all_periods if p], key=_period_order)
    if len(x_axis) < 2:
        return None

    series_list: list[dict[str, Any]] = []
    for idx, (sym, pmap) in enumerate(per_fund):
        data = [_float_or(pmap.get(p)) for p in x_axis]
        if all(v == 0 for v in data):
            continue
        color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        series_list.append({"name": sym, "data": data, "color": color})

    if not series_list:
        return None
    return {
        "id": "volatility_trend",
        "title": "年化波动率趋势",
        "type": "line",
        "data": {"xAxis": x_axis, "series": series_list},
        "options": {"showLegend": True, "showGrid": True, "yAxisLabel": "波动率(%)"},
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


def _build_fetch_failure_sections(funds: list[dict[str, Any]]) -> list[TextSection]:
    """构建取数失败提示 section，供前端显式展示字段抓取异常。"""
    sections: list[TextSection] = []
    if not funds:
        return sections

    module_alias: dict[str, str] = {
        "basic_info": "基础信息",
        "achievement": "业绩表现",
        "analysis": "风险分析",
        "profit_probability": "盈亏概率",
        "detail_hold": "持仓明细",
        "detail_info": "费率详情",
        "nav_data": "净值走势",
        "manager_tenure": "经理任期",
        "manager_career": "经理从业经验",
        "rating_info": "第三方评级",
    }
    module_order = list(module_alias.keys())

    for idx, fund in enumerate(funds):
        if not isinstance(fund, dict):
            continue
        symbol = str(fund.get("symbol") or f"fund_{idx + 1}")
        lines: list[str] = []
        for key in module_order:
            module = fund.get(key)
            if not isinstance(module, dict):
                continue
            if module.get("ok", True):
                continue
            message = str(module.get("message") or "未知错误").strip()
            label = module_alias.get(key, key)
            lines.append(f"- {label}：抓取失败（{message}）")

        if not lines:
            continue

        content = (
            f"基金 {symbol} 有部分字段抓取失败，以下内容已降级展示，建议稍后重试：\n"
            + "\n".join(lines)
        )
        section: TextSection = {
            "id": f"fetch_status_{symbol}",
            "title": f"数据抓取状态（{symbol}）",
            "type": "text",
            "content": content,
            "tags": ["风险提示"],
        }
        sections.append(section)

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


def _build_structured_achievement_block(fund: dict[str, Any]) -> str:
    """从 achievement 模块生成结构化业绩行，供前端 PerformanceSummary 稳定解析（含历年最大回撤）。"""
    rows = _module_data(fund.get("achievement"))
    if not rows:
        return ""
    first = next((r for r in rows if isinstance(r, dict)), None)
    if not first:
        return ""
    lines: list[str] = []
    ach_periods: list[str] = []
    analysis_rows = _module_data(fund.get("analysis")) or []
    analysis_kv = _kv_to_dict(analysis_rows) if analysis_rows else {}
    risk_rows_preview: list[dict[str, str]] = []

    # AkShare fund_individual_achievement_xq：宽表（周期 / 本产品区间收益 / 周期收益同类排名 / 本产品最大回撒）
    if "周期" in first or "本产品区间收益" in first:
        for r in rows:
            if not isinstance(r, dict):
                continue
            period = str(r.get("周期") or "").strip()
            if not period:
                continue
            ach_periods.append(period)
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
        for ar in analysis_rows:
            if not isinstance(ar, dict):
                continue
            p = str(ar.get("周期") or "").strip()
            sharpe = str(ar.get("年化夏普比率") or ar.get("夏普比率") or ar.get("夏普") or "").strip()
            vol = str(ar.get("年化波动率") or ar.get("波动率") or "").strip()
            vol_fmt = _achievement_val_pct(vol) if vol else ""
            if p and sharpe:
                lines.append(f"{p}夏普比率：{sharpe}")
            if p and vol_fmt:
                lines.append(f"{p}年化波动率：{vol_fmt}")
            if p or sharpe or vol:
                risk_rows_preview.append({"period": p, "sharpe": sharpe, "volatility": vol_fmt or vol})
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

    # 单基金也可展示收益走势
    nav = format_nav_chart(funds)
    if nav:
        charts.append(nav)

    # 雷达图（有数据时才展示）
    radar = format_style_radar(funds)
    if radar:
        charts.append(radar)

    vol_trend = format_volatility_trend_chart(funds)
    if vol_trend:
        charts.append(vol_trend)

    # 日频净值走势（东方财富/AkShare，与雪球业绩表互补）
    daily_nav_added = 0
    for fund in funds:
        ndp = fund.get("nav_data_periods")
        if isinstance(ndp, dict):
            range_data: dict[str, Any] = {}
            period_options: list[str] = []
            sym = str(fund.get("symbol") or "")
            for label in ["近1月", "近3月", "近1年", "成立以来"]:
                one = ndp.get(label)
                if not isinstance(one, dict):
                    continue
                one_chart = format_nav_chart_from_akshare(one, sym)
                if not one_chart or not isinstance(one_chart.get("data"), dict):
                    continue
                range_data[label] = one_chart["data"]
                period_options.append(label)
            if period_options:
                default_period = "近1年" if "近1年" in period_options else period_options[0]
                default_data = range_data.get(default_period)
                if isinstance(default_data, dict):
                    charts.append(
                        {
                            "id": f"nav_{sym}",
                            "title": "净值走势",
                            "type": "line",
                            "description": "支持近1月/近3月/近1年/成立以来切换",
                            "data": default_data,
                            "options": {
                                "showLegend": True,
                                "showGrid": True,
                                "yAxisLabel": "累计收益率(%)",
                                "periodOptions": period_options,
                                "rangeData": range_data,
                            },
                        }
                    )
                    daily_nav_added += 1
                    continue
        nd = fund.get("nav_data")
        if isinstance(nd, dict) and nd.get("ok"):
            dch = format_nav_chart_from_akshare(nd, str(fund.get("symbol") or ""))
            if dch:
                charts.append(dch)
                daily_nav_added += 1

    # LLM 文本拆分为 sections
    text_sections: list[Any] = _split_llm_text_to_sections(llm_text)
    failure_sections = _build_fetch_failure_sections(funds)
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
    all_sections: list[Any] = table_sections + failure_sections + text_sections

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

    # 5. 年化波动率趋势图
    vol_trend = format_volatility_trend_chart(funds)
    if vol_trend:
        charts.append(vol_trend)
    
    # 6. 资产配置饼图（每只基金）
    for fund in funds:
        chart = format_asset_chart(fund)
        if chart:
            charts.append(chart)
    
    # 7. 费率环形图（第一只基金）
    if funds:
        fee_donut = format_fee_donut_chart(funds)
        if fee_donut:
            charts.append(fee_donut)

    # LLM 文本 sections
    text_sections = _split_llm_text_to_sections(llm_text)
    failure_sections = _build_fetch_failure_sections(funds)

    # 合并: 先表格，后文本
    all_sections: list[Any] = table_sections + failure_sections + text_sections

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
