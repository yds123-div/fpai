# -*- coding: utf-8 -*-
"""
ADR-0003 决策 1：prompt 集中到 git 文件库的薄 loader。

- 启动时读一次进内存（lru_cache：首次调用读文件，后续走缓存）；
- 缺文件 fail-fast（FileNotFoundError，不静默降级）；
- prompt 是静态串（动态数据走 user message），不用模板引擎。

版本管理 = git（diff / review / rollback 即版本管理，不加显式版本号）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# prompt 文件目录（本模块同级 .md 文件）
_PROMPTS_DIR: Path = Path(__file__).resolve().parent


def prompts_dir() -> Path:
    """返回 prompt 文件目录（测试 / 诊断用）。"""
    return _PROMPTS_DIR


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """按名称加载 prompt 文件（name 不含扩展名，文件为 <name>.md）。

    - 首次调用读文件并缓存（lru_cache），后续调用直接返回缓存对象（读一次进内存）；
    - 缺文件 fail-fast：抛 FileNotFoundError，不返回空串或默认值；
    - 返回去掉首尾空白 的静态字符串（动态数据由调用方拼进 user message）。
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt 文件缺失：{path}（ADR-0003 决策 1：缺文件 fail-fast）")
    return path.read_text(encoding="utf-8").strip()
