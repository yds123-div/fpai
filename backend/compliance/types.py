"""
合规审查结果类型：通过/拒答/改写/补充提示。

与 technical_design §3.3 Orchestrator → Compliance 及 architecture 合规输出策略一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ComplianceAction(str, Enum):
    """合规审查动作。"""
    PASS = "pass"
    REJECT = "reject"
    REWRITE = "rewrite"
    SUPPLEMENT_PROMPT = "supplement_prompt"


@dataclass
class ComplianceDecision:
    """
    合规审查决策，供编排器/API 使用。

    - action: 通过 / 拒答 / 改写 / 补充提示
    - reason: 审查依据（可写审计）
    - suggestion: 可展示建议（如「建议转人工」）
    - rewritten_text: 当 action=rewrite 时的改写后文本
    - supplement_prompt: 当 action=supplement_prompt 时需追加的风险提示/免责内容
    - policy_version: 策略版本，便于审计与回滚
    """
    action: ComplianceAction
    reason: str = ""
    suggestion: str = ""
    rewritten_text: str | None = None
    supplement_prompt: str | None = None
    policy_version: str = ""

    def is_allowed(self) -> bool:
        """是否允许继续（通过或仅需补充提示时为 True）。"""
        return self.action in (ComplianceAction.PASS, ComplianceAction.SUPPLEMENT_PROMPT)

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化 dict，供 API 的 compliance 字段使用。"""
        d: dict[str, Any] = {
            "action": self.action.value,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "policy_version": self.policy_version,
        }
        if self.rewritten_text is not None:
            d["rewritten_text"] = self.rewritten_text
        if self.supplement_prompt is not None:
            d["supplement_prompt"] = self.supplement_prompt
        return d
