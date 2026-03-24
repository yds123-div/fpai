# -*- coding: utf-8 -*-
"""
基金名称转代码 Skill 执行入口。

根据用户输入的基金名称，查询并返回对应的基金代码。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 简单的基金名称缓存，避免频繁请求
_fund_list_cache: list[dict[str, Any]] | None = None
_cache_time: float = 0
_CACHE_TTL = 3600  # 缓存1小时


def _extract_name_keywords(text: str) -> list[str]:
    """从问题中提取可能的基金名称关键词"""
    t = (text or "").strip()
    # 移除常见问题词
    stop_words = [
        "基金", "查询", "看看", "这只", "这只基金", "这个", "请问", "帮我", "分析",
        "对比", "比较", "推荐", "哪些", "有没有", "排行", "排名", "筛选"
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
    keywords = _extract_name_keywords(question)
    if not keywords:
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
            import akshare as ak
            df = ak.fund_basic_info_em()
            if df is not None and hasattr(df, 'to_dict'):
                fund_list = df.to_dict(orient="records")
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
    
    # 模糊匹配基金名称
    matches: list[dict[str, Any]] = []
    for fund in fund_list:
        fund_name = str(fund.get("name") or fund.get("fund_name") or "")
        fund_code = str(fund.get("code") or fund.get("fund_code") or "")
        fund_type = str(fund.get("type") or fund.get("fund_type") or "")
        
        # 跳过无效记录
        if not fund_code or not fund_name:
            continue
        
        # 检查任意关键词是否匹配
        for kw in keywords:
            if kw in fund_name:
                matches.append({
                    "code": fund_code,
                    "name": fund_name,
                    "type": fund_type
                })
                break  # 一个基金只匹配一次
    
    # 去重并限制返回数量
    seen_codes = set()
    unique_matches = []
    for m in matches:
        if m["code"] not in seen_codes:
            seen_codes.add(m["code"])
            unique_matches.append(m)
    
    unique_matches = unique_matches[:10]  # 最多返回10个
    
    if not unique_matches:
        return json.dumps({
            "ok": False,
            "mode": "no_match",
            "message": f"未找到包含关键词 '{keywords[0]}' 的基金",
            "matches": [],
            "keywords": keywords
        }, ensure_ascii=False)
    
    return json.dumps({
        "ok": True,
        "mode": "name_to_code",
        "message": f"找到 {len(unique_matches)} 个匹配的基金",
        "matches": unique_matches,
        "keywords": keywords
    }, ensure_ascii=False)
