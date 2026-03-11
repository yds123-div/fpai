"""
审计证据与事件类型，与 technical_design §3.3、GET /api/v1/evidence/{answerId} 契约一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AuditEvent:
    """单条审计事件。"""
    event_type: str
    payload: dict[str, Any]
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"event_type": self.event_type, "payload": self.payload}
        if self.created_at is not None:
            d["created_at"] = self.created_at.isoformat() + "Z" if self.created_at.tzinfo is None else self.created_at.isoformat()
        return d


@dataclass
class Evidence:
    """
    按 answerId 查询得到的证据：请求摘要、意图、数据源、检索证据片段、模型/策略版本、操作人、时间戳。
    与 GET /api/v1/evidence/{answerId} 的 data 结构对应。
    """
    answer_id: str
    session_id: str
    user_id: str
    intent: str | None = None
    model_version: str | None = None
    policy_version: str | None = None
    created_at: datetime | None = None
    cold_ref: str | None = None
    events: list[AuditEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_id": self.answer_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "intent": self.intent,
            "model_version": self.model_version,
            "policy_version": self.policy_version,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at and self.created_at.tzinfo is None else (self.created_at.isoformat() if self.created_at else None),
            "cold_ref": self.cold_ref,
            "events": [e.to_dict() for e in self.events],
        }
