# -*- coding: utf-8 -*-
"""
基金代码可信集 registry（栅栏 #1 基座）。

T3（#21）：从 fund_name_to_code/runtime.py 抽出共享模块，持有 akshare 基金列表 +
现行缓存，暴露 ``is_trusted`` / ``resolve``，供 name-to-code 工具与 fund-data 取数
工具共调。确定性逻辑（查证 -> 可信集 -> 清洗 -> 查不到 abort）不变，只是把可信集
查询抽成共享模块；工具形态不改（工具化在 T5/#23）。

G4（#7）锁定：名称转代码工具即可信集权威，强制方式 = 工具内自校验（非 middleware），
为此需要一个共享的可信集查询入口——本模块即是。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, cast

# 匹配阈值（与原 runtime 一致）：低于此分不视为命中
DEFAULT_MIN_SCORE = 74.0
# 缓存 1 小时，避免频繁请求 akshare
_CACHE_TTL = 3600


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FundRecord:
    """可信集中的一条基金记录。"""

    code: str
    name: str
    type: str


@dataclass(frozen=True)
class ResolveHit:
    """resolve 的单条命中。"""

    code: str
    name: str
    type: str
    score: float


@dataclass(frozen=True)
class ResolveResult:
    """resolve 的返回。

    ``matched`` 表示是否命中；``hits`` 为命中列表（按分降序）。
    """

    input: str
    matched: bool
    hits: list[ResolveHit]


# ---------------------------------------------------------------------------
# 缓存（模块级，进程内共享）
# ---------------------------------------------------------------------------
_fund_list_cache: list[FundRecord] | None = None
_cache_time: float = 0.0


def clear_cache() -> None:
    """清空缓存（主要供测试与强制刷新使用）。"""
    global _fund_list_cache, _cache_time
    _fund_list_cache = None
    _cache_time = 0.0


# ---------------------------------------------------------------------------
# 名称归一化 / 打分（从 fund_name_to_code/runtime.py 原样迁入，行为不变）
# ---------------------------------------------------------------------------
def _normalize_fund_name(name: str, *, strip_class_suffix: bool = False) -> str:
    s = (name or "").strip()
    if not s:
        return ""
    # 去掉常见分隔符/空白
    s = re.sub(r"[\s\-_/·\.,，。:：;；\(\)（）\[\]【】]+", "", s)
    # 统一大小写
    s = s.upper()
    # 去掉常见修饰词
    s = s.replace("证券投资", "").replace("投资基金", "")
    # 可选：去掉份额后缀（A/C/E等），用于兜底匹配
    if strip_class_suffix:
        s = re.sub(r"(人民币|美元|CNY|CNH)$", "", s)
        s = re.sub(r"(A类|B类|C类|D类|E类|F类)$", "", s)
        s = re.sub(r"[A-HJ-Z]$", "", s)
    return s


def score_match(query: str, fund_name: str) -> float:
    """单 query 对单 fund_name 的确定性打分（原 runtime._score_match，行为不变）。"""
    q = _normalize_fund_name(query, strip_class_suffix=False)
    q_base = _normalize_fund_name(query, strip_class_suffix=True)
    n = _normalize_fund_name(fund_name, strip_class_suffix=False)
    n_base = _normalize_fund_name(fund_name, strip_class_suffix=True)
    if not q or not n:
        return 0.0

    # 强匹配
    if q == n:
        return 120.0
    if q == n_base or q_base == n or (q_base and q_base == n_base):
        return 112.0

    # 包含匹配（优先）
    if q in n or n in q:
        base = 95.0
        ratio = min(len(q), len(n)) / max(len(q), len(n))
        return base + ratio * 10
    if q_base and (q_base in n_base or n_base in q_base):
        base = 90.0
        ratio = min(len(q_base), len(n_base)) / max(len(q_base), len(n_base))
        return base + ratio * 8

    # 相似度兜底
    r1 = SequenceMatcher(None, q, n).ratio()
    r2 = SequenceMatcher(None, q_base, n_base).ratio() if q_base and n_base else 0.0
    r = max(r1, r2)
    if r >= 0.90:
        return 88.0 + r * 10
    if r >= 0.82:
        return 78.0 + r * 10
    if r >= 0.74:
        return 68.0 + r * 10
    return 0.0


# ---------------------------------------------------------------------------
# akshare 基金列表加载（从 fund_name_to_code/runtime.py 原样迁入）
# ---------------------------------------------------------------------------
def _pick_field(row: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _load_fund_list() -> list[FundRecord]:
    """
    兼容不同 AkShare 版本：
    - 优先 fund_name_em（较常见）
    - 回退 fund_open_fund_rank_em
    返回统一结构：[FundRecord(code,name,type)]

    任何异常都吞掉返回 []（与原 runtime 行为一致），由上层决定如何处理空列表。
    """
    import akshare as ak  # type: ignore[import-not-found]  # 装在 venv，pyright 默认未指 venv

    rows: list[FundRecord] = []

    # 1) fund_name_em
    fn_name = getattr(ak, "fund_name_em", None)
    if callable(fn_name):
        try:
            df = fn_name()
            if df is not None and hasattr(df, "to_dict"):
                for r in cast(Any, df).to_dict(orient="records"):
                    if not isinstance(r, dict):
                        continue
                    code = _pick_field(r, ["基金代码", "code", "fund_code"])
                    name = _pick_field(r, ["基金简称", "基金名称", "name", "fund_name"])
                    typ = _pick_field(r, ["基金类型", "type", "fund_type"])
                    if code and name:
                        rows.append(FundRecord(code=code, name=name, type=typ))
        except Exception:
            pass

    if rows:
        return rows

    # 2) fund_open_fund_rank_em(symbol="全部")
    fn_rank = getattr(ak, "fund_open_fund_rank_em", None)
    if callable(fn_rank):
        try:
            df = fn_rank(symbol="全部")
            if df is not None and hasattr(df, "to_dict"):
                for r in cast(Any, df).to_dict(orient="records"):
                    if not isinstance(r, dict):
                        continue
                    code = _pick_field(r, ["基金代码", "代码", "code", "fund_code"])
                    name = _pick_field(r, ["基金简称", "基金名称", "名称", "name", "fund_name"])
                    typ = _pick_field(r, ["基金类型", "类型", "type", "fund_type"])
                    if code and name:
                        rows.append(FundRecord(code=code, name=name, type=typ))
        except Exception:
            pass

    return rows


def get_fund_list() -> list[FundRecord]:
    """返回可信集（akshare 基金列表），带 TTL 缓存。

    缓存命中时不触网；空结果不缓存（与原 runtime 一致，下次调用重试）。
    """
    global _fund_list_cache, _cache_time
    now = time.time()
    if _fund_list_cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _fund_list_cache
    rows = _load_fund_list()
    if rows:
        _fund_list_cache = rows
        _cache_time = now
    return rows


# ---------------------------------------------------------------------------
# 可信集查询入口（G4 #7 锁定的共享 API）
# ---------------------------------------------------------------------------
_CODE_RE = re.compile(r"^\d{6}$")


def is_trusted(code: str) -> bool:
    """代码是否在可信集内（6 位纯数字且存在于 akshare 基金列表）。"""
    c = (code or "").strip()
    if not _CODE_RE.match(c):
        return False
    for fund in get_fund_list():
        if fund.code == c:
            return True
    return False


def resolve(
    name_or_code: str,
    *,
    limit: int = 10,
    min_score: float = DEFAULT_MIN_SCORE,
) -> ResolveResult:
    """把名称或代码解析为可信基金记录。

    - 输入 6 位代码：在可信集内 -> 命中该条；不在 -> 未命中。
    - 输入名称：对可信集做确定性多策略匹配（精确/包含/去份额后缀/相似度），
      返回分数 >= ``min_score`` 的命中，按分降序，截断到 ``limit``。

    本函数是栅栏 #1 的共享查询入口，name-to-code 工具与 fund-data 取数工具共调。
    """
    raw = (name_or_code or "").strip()
    if not raw:
        return ResolveResult(input=raw, matched=False, hits=[])

    funds = get_fund_list()

    # 代码路径：精确查可信集
    if _CODE_RE.match(raw):
        for fund in funds:
            if fund.code == raw:
                return ResolveResult(
                    input=raw,
                    matched=True,
                    hits=[ResolveHit(code=fund.code, name=fund.name, type=fund.type, score=120.0)],
                )
        return ResolveResult(input=raw, matched=False, hits=[])

    # 名称路径：多策略匹配
    scored: list[ResolveHit] = []
    for fund in funds:
        if not fund.code or not fund.name:
            continue
        s = score_match(raw, fund.name)
        if s >= min_score:
            scored.append(
                ResolveHit(code=fund.code, name=fund.name, type=fund.type, score=round(s, 2))
            )
    scored.sort(key=lambda h: h.score, reverse=True)
    hits = scored[:limit] if limit and limit > 0 else scored
    return ResolveResult(input=raw, matched=bool(hits), hits=hits)
