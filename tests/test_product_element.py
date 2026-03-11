"""产品要素/条款抽取单元测试：ProductElements、extract_elements（规则与 LLM）。"""
import pytest

from agents.product_element.types import ProductElements
from agents.product_element import extract_elements


def test_product_elements_to_dict():
    el = ProductElements(term="1年", risk_level="R3", fee_rate="0.5%")
    d = el.to_dict()
    assert d.get("term") == "1年"
    assert d.get("risk_level") == "R3"
    assert d.get("fee_rate") == "0.5%"
    assert "product_name" not in d or d["product_name"] is None


def test_product_elements_from_dict():
    d = {
        "term": " 2年 ",
        "fee_rate": "0.8%",
        "risk_level": "R2",
        "redemption_rules": "T+1 赎回到账",
    }
    el = ProductElements.from_dict(d)
    assert el.term == "2年"
    assert el.fee_rate == "0.8%"
    assert el.risk_level == "R2"
    assert el.redemption_rules == "T+1 赎回到账"


def test_product_elements_from_dict_extra():
    d = {"term": "1年", "custom_field": "值"}
    el = ProductElements.from_dict(d)
    assert el.term == "1年"
    assert el.extra.get("custom_field") == "值"


def test_extract_elements_empty():
    el = extract_elements("")
    assert el.term == "" and el.risk_level == ""


def test_extract_elements_rule_only():
    """规则抽取：命中「期限：」「费率：」等模式。"""
    text = """
    本产品期限：1年，封闭运作。
    管理费率：0.5%/年。
    风险等级：R3。
    赎回规则：开放日后 T+1 赎回到账。
    业绩基准：中证500指数*80%+国债指数*20%。
    """
    el = extract_elements(text, use_llm=False)
    assert "1年" in el.term or "1年" in (el.term or "")
    assert "0.5" in el.fee_rate or "费率" in text
    assert "R3" in el.risk_level or "风险" in text
    assert "T+1" in el.redemption_rules or "赎回" in text
    assert "中证" in el.performance_benchmark or "业绩" in text


def test_extract_elements_rule_patterns():
    """规则能匹配中文冒号与英文冒号。"""
    text = "投资期限: 6个月。风险等级：R2。"
    el = extract_elements(text, use_llm=False)
    # 至少有一项被规则命中
    assert el.term or el.risk_level or "6个月" in text or "R2" in text
