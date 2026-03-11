# 产品要素/条款抽取（内部子能力）；供解读/对比/报告或 ingestion 调用
from agents.product_element.types import ProductElements
from agents.product_element.extract import extract_elements

__all__ = [
    "ProductElements",
    "extract_elements",
]
