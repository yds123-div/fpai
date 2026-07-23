# -*- coding: utf-8 -*-
"""
基金名称转代码 Skill 执行入口。

根据用户输入的基金名称，查询并返回对应的基金代码。
"""

from __future__ import annotations

import json
import re
from typing import Any
from difflib import SequenceMatcher

# 简单的基金名称缓存，避免频繁请求
_fund_list_cache: list[dict[str, Any]] | None = None
_cache_time: float = 0
_CACHE_TTL = 3600  # 缓存1小时


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


def _build_query_candidates(text: str) -> list[str]:
    """
    构建查询候选：优先使用更长、更像基金名的片段，提升命中率。
    """
    t = (text or "").strip()
    if not t:
        return []
    cands: list[str] = []
    # 1) 原句去掉常见提示词后的片段
    cleaned = t
    for sw in ("请帮我", "帮我", "请问", "麻烦", "看看", "查询", "查下", "解析", "分析", "对比", "比较", "基金", "代码"):
        cleaned = cleaned.replace(sw, " ")
    for seg in re.split(r"[，,。！？!?\s]+", cleaned):
        seg = seg.strip()
        if len(seg) >= 2 and not seg.isdigit():
            cands.append(seg)
    # 2) 关键词兜底
    cands.extend(_extract_name_keywords(t))
    # 去重保序
    uniq: list[str] = []
    seen: set[str] = set()
    for x in cands:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    # 长词优先
    uniq.sort(key=len, reverse=True)
    return uniq


def _pick_field(row: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _load_fund_list() -> list[dict[str, Any]]:
    """
    兼容不同 AkShare 版本：
    - 优先 fund_name_em（较常见）
    - 回退 fund_open_fund_rank_em
    返回统一结构：[{code,name,type}]
    """
    import akshare as ak

    rows: list[dict[str, Any]] = []

    # 1) fund_name_em
    fn_name = getattr(ak, "fund_name_em", None)
    if callable(fn_name):
        try:
            df = fn_name()
            if df is not None and hasattr(df, "to_dict"):
                for r in df.to_dict(orient="records"):
                    if not isinstance(r, dict):
                        continue
                    code = _pick_field(r, ["基金代码", "code", "fund_code"])
                    name = _pick_field(r, ["基金简称", "基金名称", "name", "fund_name"])
                    typ = _pick_field(r, ["基金类型", "type", "fund_type"])
                    if code and name:
                        rows.append({"code": code, "name": name, "type": typ})
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
                for r in df.to_dict(orient="records"):
                    if not isinstance(r, dict):
                        continue
                    code = _pick_field(r, ["基金代码", "代码", "code", "fund_code"])
                    name = _pick_field(r, ["基金简称", "基金名称", "名称", "name", "fund_name"])
                    typ = _pick_field(r, ["基金类型", "类型", "type", "fund_type"])
                    if code and name:
                        rows.append({"code": code, "name": name, "type": typ})
        except Exception:
            pass

    return rows


def _extract_name_keywords(text: str) -> list[str]:
    """从问题中提取可能的基金名称关键词"""
    t = (text or "").strip()
    # 移除常见问题词
    stop_words = [
        "基金", "查询", "看看", "这只", "这只基金", "这个", "请问", "帮我", "分析", "解析",
        "对比", "比较", "推荐", "哪些", "有没有", "排行", "排名", "筛选", "代码", "是多少",
    ]
    for sw in stop_words:
        t = t.replace(sw, " ")
    
    # 提取可能的基金名称（去除纯数字和标点）
    keywords = []
    parts = re.split(r"[\s,，。、]+", t)
    for p in parts:
        p = p.strip()
        if p and len(p) >= 2 and not p.isdigit() and not re.match(r"^[\d]+$", p):
            keywords.append(p)
    
    return keywords


def _score_match(query: str, fund_name: str) -> float:
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


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    根据基金名称查询基金代码。
    
    输入：用户问题（可能包含基金名称）
    输出：JSON 字符串，包含匹配结果列表
    """
    global _fund_list_cache, _cache_time
    
    import time
    
    # 检查是否已有6位基金代码
    codes = re.findall(r"(?<!\d)\d{6}(?!\d)", (question or ""))
    if codes:
        # 已有基金代码，不需要查询名称
        return json.dumps({
            "ok": True,
            "mode": "code_provided",
            "message": "用户已提供基金代码，无需名称查询",
            "codes": codes
        }, ensure_ascii=False)
    
    # 提取基金名称关键词
    candidates = _build_query_candidates(question)
    if not candidates:
        return json.dumps({
            "ok": False,
            "mode": "no_keyword",
            "message": "未识别到有效的基金名称关键词",
            "matches": []
        }, ensure_ascii=False)
    
    # 尝试获取基金列表
    fund_list: list[dict[str, Any]] = []
    current_time = time.time()
    
    if _fund_list_cache is not None and (current_time - _cache_time) < _CACHE_TTL:
        fund_list = _fund_list_cache
    else:
        try:
            fund_list = _load_fund_list()
            if fund_list:
                _fund_list_cache = fund_list
                _cache_time = current_time
        except Exception as e:
            return json.dumps({
                "ok": False,
                "mode": "fetch_error",
                "message": f"获取基金列表失败: {str(e)}",
                "matches": []
            }, ensure_ascii=False)
    
    if not fund_list:
        return json.dumps({
            "ok": False,
            "mode": "no_data",
            "message": "基金列表为空",
            "matches": []
        }, ensure_ascii=False)
    
    # 多策略匹配基金名称（精确/包含/去份额后缀/相似度）
    scored_matches: list[tuple[float, dict[str, Any]]] = []
    for fund in fund_list:
        fund_name = str(fund.get("name") or "")
        fund_code = str(fund.get("code") or "")
        fund_type = str(fund.get("type") or "")
        
        # 跳过无效记录
        if not fund_code or not fund_name:
            continue
        
        best = 0.0
        for cand in candidates[:8]:
            score = _score_match(cand, fund_name)
            if score > best:
                best = score
        # 阈值：避免把完全无关基金拉进来
        if best >= 74.0:
            scored_matches.append(
                (
                    best,
                    {
                        "code": fund_code,
                        "name": fund_name,
                        "type": fund_type,
                        "score": round(best, 2),
                    },
                )
            )
    
    # 去重并限制返回数量
    scored_matches.sort(key=lambda x: x[0], reverse=True)
    seen_codes = set()
    unique_matches = []
    for _, m in scored_matches:
        code = m.get("code")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        unique_matches.append(m)
    
    unique_matches = unique_matches[:10]  # 最多返回10个
    
    if not unique_matches:
        return json.dumps({
            "ok": False,
            "mode": "no_match",
            "message": f"未找到与 '{candidates[0]}' 匹配的基金",
            "matches": [],
            "keywords": candidates[:5],
        }, ensure_ascii=False)
    
    return json.dumps({
        "ok": True,
        "mode": "name_to_code",
        "message": f"找到 {len(unique_matches)} 个匹配的基金",
        "matches": unique_matches,
        "keywords": candidates[:5],
    }, ensure_ascii=False)
