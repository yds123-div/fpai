"""
合规策略与黑白名单配置。

一期为内存配置，支持从环境变量或代码中注入；T014 config 模块可后续从 MySQL/配置文件加载。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class CompliancePolicy:
    """
    合规策略：黑白名单与审查开关。

    - blacklist_keywords: 命中即触发拒答或复核（按策略可配置为 reject/review）
    - whitelist_keywords: 可选，用于放宽误拦（如白名单短语不触发黑名单）
    - enable_llm_input_check: 是否启用输入大模型审查（提示注入、越权等）
    - enable_llm_output_check: 是否启用输出大模型审查（承诺收益、夸大宣传、敏感主题等）
    - policy_version: 策略版本，写入审计
    """
    blacklist_keywords: Sequence[str] = ()
    whitelist_keywords: Sequence[str] = ()
    enable_llm_input_check: bool = False
    enable_llm_output_check: bool = False
    policy_version: str = "v1"

    def __post_init__(self) -> None:
        self._bl_set: set[str] = set(
            k.strip().lower() for k in self.blacklist_keywords if (k and k.strip())
        )
        self._wl_set: set[str] = set(
            k.strip().lower() for k in self.whitelist_keywords if (k and k.strip())
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompliancePolicy":
        """从 config 模块返回的 dict（如 MySQL config_value）构造；用于 T014 从 MySQL 加载。"""
        return cls(
            blacklist_keywords=tuple(d.get("blacklist_keywords") or []),
            whitelist_keywords=tuple(d.get("whitelist_keywords") or []),
            enable_llm_input_check=bool(d.get("enable_llm_input_check", False)),
            enable_llm_output_check=bool(d.get("enable_llm_output_check", False)),
            policy_version=str(d.get("policy_version") or "v1"),
        )

    def blacklist_matches(self, text: str) -> list[str]:
        """返回命中的黑名单词（已转小写），空列表表示未命中。"""
        if not text or not self._bl_set:
            return []
        lower = text.lower()
        return [k for k in self._bl_set if k in lower]

    def is_whitelisted(self, text: str) -> bool:
        """若文本包含白名单短语则视为放行（用于减少误拦）。"""
        if not text or not self._wl_set:
            return False
        lower = text.lower()
        return any(w in lower for w in self._wl_set)


# 默认策略：示例黑名单，实际由配置或 T014 加载
DEFAULT_POLICY = CompliancePolicy(
    blacklist_keywords=[
        "保本保息",
        "稳赚不赔",
        "承诺收益",
        "绝对收益",
    ],
    whitelist_keywords=(),
    enable_llm_input_check=False,
    enable_llm_output_check=False,
    policy_version="v1",
)
