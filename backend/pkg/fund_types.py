"""
基金分析多模态输出类型定义。

前后端共享的数据契约——Python 侧用 TypedDict 约束，
前端 TypeScript 侧有对应 interface（见 frontend/src/types/fundAnalysis.ts）。
"""
from __future__ import annotations

from typing import Any, Literal, Union

from typing_extensions import NotRequired, TypedDict


# ---------------------------------------------------------------------------
# 置顶卡片
# ---------------------------------------------------------------------------

class InfoCard(TypedDict):
    id: str
    title: str
    type: Literal["basic", "performance", "risk", "fee"]
    data: dict[str, Any]


# ---------------------------------------------------------------------------
# 分析模块（Section）
# ---------------------------------------------------------------------------

class TableDef(TypedDict):
    headers: list[str]
    rows: list[dict[str, Any]]
    highlight: NotRequired[list[str]]


class TableSection(TypedDict):
    id: str
    title: str
    type: Literal["table"]
    description: NotRequired[str]
    table: TableDef


class TextSection(TypedDict):
    id: str
    title: str
    type: Literal["text"]
    content: str
    tags: NotRequired[list[str]]


AnalysisSection = Union[TableSection, TextSection]


# ---------------------------------------------------------------------------
# 图表配置
# ---------------------------------------------------------------------------

class PieChartData(TypedDict):
    labels: list[str]
    values: list[float]
    colors: NotRequired[list[str]]


class LineSeries(TypedDict):
    name: str
    data: list[float | int | None]
    color: NotRequired[str]
    style: NotRequired[Literal["solid", "dashed"]]


class LineChartData(TypedDict):
    xAxis: list[str]
    series: list[LineSeries]


class RadarIndicator(TypedDict):
    name: str
    max: int | float


class RadarSeries(TypedDict):
    name: str
    data: list[float | int]
    color: NotRequired[str]


class RadarChartData(TypedDict):
    indicators: list[RadarIndicator]
    series: list[RadarSeries]


class ChartConfig(TypedDict):
    id: str
    title: str
    type: Literal["pie", "donut", "line", "bar", "radar"]
    description: NotRequired[str]
    data: PieChartData | LineChartData | RadarChartData | dict[str, Any]
    options: NotRequired[dict[str, Any]]


# ---------------------------------------------------------------------------
# 顶层输出
# ---------------------------------------------------------------------------

class FundAnalysisOutput(TypedDict):
    type: Literal["fund_analysis"]
    mode: Literal["single", "compare"]
    summary: str
    cards: list[InfoCard]
    sections: list[AnalysisSection]
    charts: list[ChartConfig]
    text: str


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

FUND_ANALYSIS_TYPE = "fund_analysis"


def is_fund_analysis(data: Any) -> bool:
    """判断一个 dict / JSON-parsed 对象是否为 FundAnalysisOutput。"""
    return isinstance(data, dict) and data.get("type") == FUND_ANALYSIS_TYPE
