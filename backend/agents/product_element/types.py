"""
产品要素/条款抽取结果类型。

与 technical_design、architecture 一致：期限、费率、风险、赎回规则、投向、业绩基准等。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductElements:
    """
    从文档/条款中抽取的结构化要素，供解读/对比/报告或 ingestion 使用。
    各字段为可选，未抽到则为空字符串或 None。
    """
    term: str = ""  # 期限
    fee_rate: str = ""  # 费率
    risk_level: str = ""  # 风险等级
    redemption_rules: str = ""  # 赎回规则
    investment_direction: str = ""  # 投向
    performance_benchmark: str = ""  # 业绩基准
    income_rules: str = ""  # 收益规则
    product_name: str = ""  # 产品名称（若有）
    extra: dict[str, str] = field(default_factory=dict)  # 其他键值

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "term": self.term or None,
            "fee_rate": self.fee_rate or None,
            "risk_level": self.risk_level or None,
            "redemption_rules": self.redemption_rules or None,
            "investment_direction": self.investment_direction or None,
            "performance_benchmark": self.performance_benchmark or None,
            "income_rules": self.income_rules or None,
            "product_name": self.product_name or None,
        }
        if self.extra:
            d["extra"] = dict(self.extra)
        return {k: v for k, v in d.items() if v is not None or k == "extra"}

    _KNOWN_KEYS = frozenset({
        "term", "fee_rate", "risk_level", "redemption_rules",
        "investment_direction", "performance_benchmark", "income_rules", "product_name", "extra",
    })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProductElements":
        """从 LLM 或规则解析得到的 dict 构造；未知键放入 extra。"""
        extra = dict(d.get("extra") or {})
        for k, v in d.items():
            if k not in cls._KNOWN_KEYS and v is not None and str(v).strip():
                extra[k] = str(v).strip()
        return cls(
            term=str(d.get("term") or "").strip(),
            fee_rate=str(d.get("fee_rate") or "").strip(),
            risk_level=str(d.get("risk_level") or "").strip(),
            redemption_rules=str(d.get("redemption_rules") or "").strip(),
            investment_direction=str(d.get("investment_direction") or "").strip(),
            performance_benchmark=str(d.get("performance_benchmark") or "").strip(),
            income_rules=str(d.get("income_rules") or "").strip(),
            product_name=str(d.get("product_name") or "").strip(),
            extra=extra,
        )
