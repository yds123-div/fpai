"""
反馈类型：与 technical_design §2.3 POST /api/v1/feedback 及 MySQL feedback 表一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Rating(str, Enum):
    """反馈评级：useful / not_useful / inaccurate。"""
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    INACCURATE = "inaccurate"


@dataclass
class FeedbackRecord:
    """单条反馈记录。"""
    id: int
    answer_id: str
    user_id: str
    rating: str
    comment: str | None
    created_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "answer_id": self.answer_id,
            "user_id": self.user_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at and getattr(self.created_at, "isoformat", None) and not getattr(self.created_at, "tzinfo", None) else (self.created_at.isoformat() if self.created_at and getattr(self.created_at, "isoformat", None) else None),
        }
