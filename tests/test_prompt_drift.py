# -*- coding: utf-8 -*-
"""
ADR-0003 决策 5：prompt 漂移从 import 时 assert 降到测试时校验（仍被 CI 拦）。

T10 #28 原子切换后旧手写编排（coordinator / plan_validation / VALID_TASK_TYPES /
COORDINATOR_DEFAULT_SYSTEM_PROMPT）已同提交删除，原 coordinator prompt type 漂移校验
（== VALID_TASK_TYPES）随旧链路退役。本文件保留下列**仍存活**的 prompt 漂移/契约校验：

- 薄 loader 的 fail-fast 与缓存复用行为（ADR-0003 决策 1）。
- 统一 sys_prompt（新链路唯一权威 prompt）按取数形状切三档输出模式（T2 验收）。
- sys_prompt 的分析契约（Role/Rules/Output Format）与"工具只取数、不背分析契约"原则。

测试路径说明：backend/pyproject.toml 配置 testpaths=["../tests"]、pythonpath=["."]，
import 路径以 backend/ 为根。运行：cd backend && python -m pytest ../tests/test_prompt_drift.py -v
"""
from __future__ import annotations

import re

import pytest

from agents.prompts.loader import load_prompt, prompts_dir


# ---------------------------------------------------------------------------
# 薄 loader：fail-fast + 缓存复用（ADR-0003 决策 1）
# ---------------------------------------------------------------------------
def test_load_prompt_returns_nonempty_string() -> None:
    assert load_prompt("sys_prompt")


def test_load_prompt_missing_file_raises_filenotfound() -> None:
    """缺文件 fail-fast（决策 1：启动时读一次进内存，缺文件即启动失败）。"""
    with pytest.raises(FileNotFoundError):
        load_prompt("this_prompt_does_not_exist_xyz")


def test_load_prompt_caches_reuse() -> None:
    """缓存复用：同一 name 多次调用返回同一字符串对象（读一次进内存）。"""
    a = load_prompt("sys_prompt")
    b = load_prompt("sys_prompt")
    assert a is b


def test_prompts_dir_contains_sys_prompt_file() -> None:
    """prompts 目录下有 sys_prompt.md（新链路唯一权威 prompt）。"""
    names = {f.stem for f in prompts_dir().glob("*.md")}
    assert "sys_prompt" in names


# ---------------------------------------------------------------------------
# 统一 sys_prompt：按取数形状切三档输出模式（T2 验收，新链路权威）
# ---------------------------------------------------------------------------
def test_sys_prompt_has_three_output_modes() -> None:
    """统一 sys_prompt 按取数形状切三档输出模式：榜单 / 单只 / 多只。"""
    prompt = load_prompt("sys_prompt")
    assert "榜单" in prompt
    assert "单只" in prompt
    assert "多只" in prompt


def test_sys_prompt_carries_analysis_contract() -> None:
    """分析契约在 sys_prompt（Role/Rules/Output Format），三档模式各含分析结论与风险提示。"""
    prompt = load_prompt("sys_prompt")
    assert "基金分析专家" in prompt
    assert "Rules" in prompt
    assert "Output Format" in prompt
    # 三档输出模式各含【分析结论】与【风险提示】
    assert prompt.count("【分析结论】") >= 3
    assert prompt.count("【风险提示】") >= 3


def test_sys_prompt_tool_descriptions_only_describe_data() -> None:
    """工具描述只写"取什么数"，不背分析契约（T2 设计原则）。

    可用工具段的描述行（以 "- " 开头）不得含分析动词契约（评价/给出观点/综合分析等）--
    分析契约在 Skills/Rules/Output Format，工具只负责取数。
    """
    prompt = load_prompt("sys_prompt")
    assert "可用工具" in prompt
    # 提取"可用工具"段（到下一个 ## 标题 ## Skills 前）
    tool_section = prompt.split("可用工具", 1)[-1].split("## Skills", 1)[0]
    analysis_verbs = ("评价", "给出观点", "给出你的观点", "综合分析", "分析评价")
    for line in tool_section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            for verb in analysis_verbs:
                assert verb not in stripped, (
                    f"工具描述行背了分析契约（含分析动词 {verb}）：{stripped}"
                )
