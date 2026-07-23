# -*- coding: utf-8 -*-
"""
基金名称转代码 Skill 执行入口。

根据用户输入的基金名称，查询并返回对应的基金代码。

T3（#21）：可信集查询（akshare 基金列表 + 缓存 + is_trusted/resolve）已抽出到
``agents.skills.fund_code_registry``，本模块只保留问题解析（候选名抽取）与
匹配装配。确定性逻辑（查证 -> 可信集 -> 清洗 -> 查不到 abort）行为不变；
工具形态不改（工具化在 T5/#23）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents.skills.fund_code_registry import get_fund_list, score_match


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


async def run(question: str, ctx: dict[str, Any]) -> str:
    """
    根据基金名称查询基金代码。

    输入：用户问题（可能包含基金名称）
    输出：JSON 字符串，包含匹配结果列表
    """
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

    # 取可信集（registry 带 TTL 缓存，不每次打 akshare/网络）
    try:
        fund_list = get_fund_list()
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
        fund_name = fund.name
        fund_code = fund.code
        fund_type = fund.type

        # 跳过无效记录
        if not fund_code or not fund_name:
            continue

        best = 0.0
        for cand in candidates[:8]:
            s = score_match(cand, fund_name)
            if s > best:
                best = s
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
