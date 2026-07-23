# -*- coding: utf-8 -*-
"""
ADR-0003 决策 5：prompt 漂移从 import 时 assert 降到测试时校验（仍被 CI 拦）。

本文件替代 fund_agent_framework.py 中原 import 时 assert（COORDINATOR_DEFAULT_SYSTEM_PROMPT
的 type 列表 == plan_validation.VALID_TASK_TYPES）：
- 加载 coordinator prompt 文件，校验 type 列表 == VALID_TASK_TYPES（ADR-0001 决策 6 防漂移）；
- 校验薄 loader 的 fail-fast 与缓存复用行为（ADR-0003 决策 1）；
- 校验统一 sys_prompt 按取数形状切三档输出模式（T2 验收）。

测试路径说明：backend/pyproject.toml 配置 testpaths=["../tests"]、pythonpath=["."]，
import 路径以 backend/ 为根。运行：cd backend && python -m pytest ../tests/test_prompt_drift.py -v
"""
from __future__ import annotations

import re

import pytest

from agents.plan_validation import VALID_TASK_TYPES
from agents.prompts.loader import load_prompt, prompts_dir


# ---------------------------------------------------------------------------
# ADR-0003 决策 5 + ADR-0001 决策 6：coordinator prompt type 列表 == VALID_TASK_TYPES
# ---------------------------------------------------------------------------
def test_coordinator_prompt_type_list_matches_valid_task_types() -> None:
    """coordinator prompt 文件中的 type 列表必须 == VALID_TASK_TYPES。

    替代 fund_agent_framework.py 中原 import 时 assert。若新增/改名 type 而忘了同步
    prompt，本测试失败被 CI 拦。
    """
    prompt = load_prompt("coordinator")
    # 提取 "- <type>：" 形式的 type 列表项（ASCII 词 + 全角冒号）。
    # coordinator prompt 的规则行以中文开头，不匹配 \w+，故只命中 4 个 type。
    types_found = re.findall(r"^-\s+(\w+)：", prompt, re.MULTILINE)
    assert set(types_found) == set(VALID_TASK_TYPES), (
        f"coordinator prompt type 列表 {sorted(set(types_found))} "
        f"!= VALID_TASK_TYPES {sorted(set(VALID_TASK_TYPES))}"
    )


def test_coordinator_prompt_mentions_every_task_type() -> None:
    """散文级保底：每个 VALID_TASK_TYPE 都在 coordinator prompt 中出现。"""
    prompt = load_prompt("coordinator")
    for tp in VALID_TASK_TYPES:
        assert tp in prompt, f"coordinator prompt 缺少 type: {tp}"


# ---------------------------------------------------------------------------
# 薄 loader：fail-fast + 缓存复用（ADR-0003 决策 1）
# ---------------------------------------------------------------------------
def test_load_prompt_returns_nonempty_string() -> None:
    assert load_prompt("coordinator")
    assert load_prompt("sys_prompt")


def test_load_prompt_missing_file_raises_filenotfound() -> None:
    """缺文件 fail-fast（决策 1：启动时读一次进内存，缺文件即启动失败）。"""
    with pytest.raises(FileNotFoundError):
        load_prompt("this_prompt_does_not_exist_xyz")


def test_load_prompt_caches_reuse() -> None:
    """缓存复用：同一 name 多次调用返回同一字符串对象（读一次进内存）。"""
    a = load_prompt("coordinator")
    b = load_prompt("coordinator")
    assert a is b


def test_prompts_dir_contains_prompt_files() -> None:
    """prompts 目录下有 coordinator.md 与 sys_prompt.md。"""
    names = {f.stem for f in prompts_dir().glob("*.md")}
    assert "coordinator" in names
    assert "sys_prompt" in names


# ---------------------------------------------------------------------------
# 统一 sys_prompt：三份业务 prompt 并集去重，按取数形状切输出模式（T2 验收）
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
    """工具描述只写"取什么数"，不背分析契约（T2 设计原则）。"""
    prompt = load_prompt("sys_prompt")
    # 工具段标记存在
    assert "可用工具" in prompt or "工具" in prompt
    # 工具描述不含分析动词契约（"评价/给出观点"只在 Role/Skills，不在工具描述行）
    tool_section = prompt.split("可用工具", 1)[-1].split("## Skills", 1)[0] if "可用工具" in prompt else ""
    if tool_section:
        # 工具行应是"取数"描述，不含"分析/评价/给出观点"
        for line in tool_section.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                assert "分析" not in stripped or "取" in stripped, (
                    f"工具描述行疑似背了分析契约：{stripped}"
                )
