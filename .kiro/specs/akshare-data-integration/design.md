# AkShare 数据集成设计文档

## 设计概述

本设计文档描述了如何将 AkShare 真实基金数据集成到现有的多模态输出系统中。设计遵循分层架构原则，将数据获取、转换和展示三层解耦，确保系统的可维护性和可扩展性。

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端展示层                                 │
│  FundAnalysis.vue (已存在)                                        │
│    ├─ InfoCard.vue (卡片)                                        │
│    ├─ TableSection.vue (表格)                                    │
│    ├─ ChartRenderer.vue (图表)                                   │
│    └─ TextSection.vue (文本)                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                        JSON 数据流
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         Agent 编排层                              │
│  ProductInterpretAgent (单基金) ← 修改                            │
│  ProductCompareAgent (多基金对比) ← 修改                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
┌──────────────────────────┐  ┌──────────────────────────┐
│    数据转换层              │  │    LLM 生成层             │
│  fund_formatter.py        │  │  model_gateway           │
│  (已存在，需增强)          │  │                          │
└──────────────────────────┘  └──────────────────────────┘
                ↑
                │ 原始数据
                ↓
┌─────────────────────────────────────────────────────────────────┐
│                      数据获取层（新增）                            │
│  AkShareClient                                                   │
│    ├─ get_basic_info()      - 基本信息                           │
│    ├─ get_achievement()     - 业绩表现                           │
│    ├─ get_analysis()        - 风险指标                           │
│    ├─ get_detail_hold()     - 资产配置                           │
│    ├─ get_detail_info()     - 费率信息                           │
│    ├─ get_nav_data()        - 净值走势                           │
│    ├─ get_industry_allocation() - 行业配置                       │
│    └─ get_portfolio_hold()  - 持仓明细                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      外部数据源                                    │
│  AkShare (雪球 + 东方财富)                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 架构分层说明

1. **数据获取层**（新增）
   - 职责：封装 AkShare API 调用，提供统一的数据访问接口
   - 核心类：`AkShareClient`
   - 特性：重试、限流、缓存、异常处理

2. **数据转换层**（增强）
   - 职责：将 AkShare 原始数据转换为前端可渲染的结构化 JSON
   - 核心模块：`fund_formatter.py`
   - 特性：字段映射、数据清洗、格式化、默认值处理

3. **Agent 编排层**（修改）
   - 职责：协调数据获取、转换和 LLM 生成
   - 核心类：`ProductInterpretAgent`、`ProductCompareAgent`
   - 特性：异步编排、错误处理、兜底机制

4. **前端展示层**（已存在）
   - 职责：渲染结构化数据为多模态界面
   - 核心组件：`FundAnalysis.vue` 及其子组件
   - 特性：响应式、交互式、兜底展示

## 模块设计


### 模块 1: AkShareClient（数据获取层）

**文件路径**：`backend/pkg/akshare_client.py`

**职责**：
- 封装 AkShare API 调用
- 提供统一的数据访问接口
- 处理网络异常和数据格式异常
- 实现重试、限流、缓存机制

**类设计**：

```python
from typing import Optional, Dict, Any, List
import akshare as ak
import logging
from functools import lru_cache
import time
import asyncio

class AkShareClient:
    """AkShare 数据获取客户端。
    
    特性：
    - 重试机制：失败时重试 3 次，指数退避
    - 限流机制：请求间隔 0.5-1 秒
    - 缓存机制：使用 lru_cache，TTL 1 小时
    - 异常处理：网络异常、数据格式异常
    """
    
    def __init__(self, 
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 request_interval: float = 0.5):
        """初始化客户端。
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒）
            request_interval: 请求间隔（秒）
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_interval = request_interval
        self.logger = logging.getLogger(__name__)
        self._last_request_time = 0
    
    async def _rate_limit(self):
        """限流：确保请求间隔。"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            await asyncio.sleep(self.request_interval - elapsed)
        self._last_request_time = time.time()
    
    async def _retry_call(self, func, *args, **kwargs) -> Dict[str, Any]:
        """带重试的 API 调用。
        
        Returns:
            {"ok": True, "data": [...]} 或 {"ok": False, "message": "..."}
        """
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                result = await asyncio.to_thread(func, *args, **kwargs)
                return {"ok": True, "data": result.to_dict(orient="records")}
            except Exception as e:
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {e}",
                    extra={"func": func.__name__, "args": args}
                )
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"All retries failed: {e}")
                    return {"ok": False, "message": str(e)}
    
    async def get_basic_info(self, symbol: str) -> Dict[str, Any]:
        """获取基金基本信息。"""
        return await self._retry_call(
            ak.fund_individual_basic_info_xq, 
            symbol=symbol
        )
    
    async def get_achievement(self, symbol: str) -> Dict[str, Any]:
        """获取业绩表现数据。"""
        return await self._retry_call(
            ak.fund_individual_achievement_xq,
            symbol=symbol
        )
    
    async def get_analysis(self, symbol: str) -> Dict[str, Any]:
        """获取风险指标数据。"""
        return await self._retry_call(
            ak.fund_individual_analysis_xq,
            symbol=symbol
        )
    
    async def get_detail_hold(self, symbol: str) -> Dict[str, Any]:
        """获取资产配置数据。"""
        return await self._retry_call(
            ak.fund_individual_detail_hold_xq,
            symbol=symbol
        )
    
    async def get_detail_info(self, symbol: str) -> Dict[str, Any]:
        """获取费率信息数据。"""
        return await self._retry_call(
            ak.fund_individual_detail_info_xq,
            symbol=symbol
        )
    
    async def get_nav_data(self, 
                          symbol: str, 
                          period: str = "1年") -> Dict[str, Any]:
        """获取净值走势数据。
        
        Args:
            symbol: 基金代码
            period: 时间周期，可选 "1月", "3月", "6月", "1年", "3年", "成立来"
        """
        return await self._retry_call(
            ak.fund_open_fund_info_em,
            symbol=symbol,
            indicator="单位净值走势",
            period=period
        )
    
    async def get_industry_allocation(self, 
                                     symbol: str,
                                     date: str = "2023") -> Dict[str, Any]:
        """获取行业配置数据。"""
        return await self._retry_call(
            ak.fund_portfolio_industry_allocation_em,
            symbol=symbol,
            date=date
        )
    
    async def get_portfolio_hold(self,
                                symbol: str,
                                date: str = "2023") -> Dict[str, Any]:
        """获取持仓明细数据。"""
        return await self._retry_call(
            ak.fund_portfolio_hold_em,
            symbol=symbol,
            date=date
        )
    
    async def get_all_data(self, symbol: str) -> Dict[str, Any]:
        """并发获取单只基金的所有数据。
        
        Returns:
            {
                "symbol": "000001",
                "basic_info": {...},
                "achievement": {...},
                "analysis": {...},
                "detail_hold": {...},
                "detail_info": {...},
                "nav_data": {...}
            }
        """
        tasks = [
            self.get_basic_info(symbol),
            self.get_achievement(symbol),
            self.get_analysis(symbol),
            self.get_detail_hold(symbol),
            self.get_detail_info(symbol),
            self.get_nav_data(symbol),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "symbol": symbol,
            "basic_info": results[0] if not isinstance(results[0], Exception) else {"ok": False},
            "achievement": results[1] if not isinstance(results[1], Exception) else {"ok": False},
            "analysis": results[2] if not isinstance(results[2], Exception) else {"ok": False},
            "detail_hold": results[3] if not isinstance(results[3], Exception) else {"ok": False},
            "detail_info": results[4] if not isinstance(results[4], Exception) else {"ok": False},
            "nav_data": results[5] if not isinstance(results[5], Exception) else {"ok": False},
        }
```

**关键设计决策**：
1. 使用异步 API（asyncio）提升性能
2. 统一返回格式：`{"ok": bool, "data": [...], "message": str}`
3. 使用 `lru_cache` 实现内存缓存（可选，后续可改为 Redis）
4. 限流使用简单的时间间隔控制


### 模块 2: fund_formatter 增强（数据转换层）

**文件路径**：`backend/pkg/fund_formatter.py`（已存在，需增强）

**增强内容**：

1. **新增函数：处理 AkShare 净值走势数据**

```python
def format_nav_chart_from_akshare(
    nav_data: Dict[str, Any],
    symbol: str
) -> ChartConfig | None:
    """从 AkShare 净值数据生成折线图配置。
    
    Args:
        nav_data: AkShare get_nav_data() 返回的数据
        symbol: 基金代码
    
    Returns:
        ChartConfig 或 None（数据不足时）
    """
    if not nav_data.get("ok"):
        return None
    
    records = nav_data.get("data", [])
    if len(records) < 2:
        return None
    
    # 提取日期和净值
    dates = [r.get("净值日期") for r in records]
    nav_values = [float(r.get("单位净值", 0)) for r in records]
    
    # 计算累计收益率
    if nav_values[0] > 0:
        returns = [(v / nav_values[0] - 1) * 100 for v in nav_values]
    else:
        returns = [0] * len(nav_values)
    
    return {
        "id": f"nav_{symbol}",
        "title": "净值走势",
        "type": "line",
        "description": f"近{len(records)}个交易日",
        "data": {
            "xAxis": dates,
            "series": [{
                "name": symbol,
                "data": returns,
                "color": DEFAULT_COLORS[0]
            }]
        },
        "options": {
            "showLegend": True,
            "showGrid": True,
            "yAxisLabel": "累计收益率(%)"
        }
    }
```

2. **新增函数：处理行业配置数据**

```python
def format_industry_chart(
    industry_data: Dict[str, Any],
    symbol: str
) -> ChartConfig | None:
    """从 AkShare 行业配置数据生成柱状图配置。
    
    Args:
        industry_data: AkShare get_industry_allocation() 返回的数据
        symbol: 基金代码
    
    Returns:
        ChartConfig 或 None
    """
    if not industry_data.get("ok"):
        return None
    
    records = industry_data.get("data", [])
    if not records:
        return None
    
    # 取前 10 大行业
    top_industries = sorted(
        records,
        key=lambda x: float(x.get("占净值比例", 0)),
        reverse=True
    )[:10]
    
    labels = [r.get("行业类别", "") for r in top_industries]
    values = [float(r.get("占净值比例", 0)) for r in top_industries]
    
    return {
        "id": f"industry_{symbol}",
        "title": "行业配置",
        "type": "bar",
        "description": "前10大行业配置",
        "data": {
            "xAxis": labels,
            "series": [{
                "name": "占净值比例",
                "data": values,
                "color": DEFAULT_COLORS[0]
            }]
        },
        "options": {
            "showLegend": False,
            "showGrid": True,
            "yAxisLabel": "占净值比例(%)"
        }
    }
```

3. **新增函数：处理持仓明细数据**

```python
def format_holding_table(
    holding_data: Dict[str, Any],
    symbol: str
) -> TableSection | None:
    """从 AkShare 持仓数据生成表格配置。
    
    Args:
        holding_data: AkShare get_portfolio_hold() 返回的数据
        symbol: 基金代码
    
    Returns:
        TableSection 或 None
    """
    if not holding_data.get("ok"):
        return None
    
    records = holding_data.get("data", [])
    if not records:
        return None
    
    # 取前 10 大重仓股
    top_holdings = records[:10]
    
    rows = []
    for idx, r in enumerate(top_holdings, 1):
        rows.append({
            "序号": idx,
            "股票代码": r.get("股票代码", ""),
            "股票名称": r.get("股票名称", ""),
            "占净值比例": f"{r.get('占净值比例', 0):.2f}%",
            "持仓市值": f"{r.get('持仓市值', 0):.2f}万元"
        })
    
    return {
        "id": f"holding_{symbol}",
        "title": "前十大重仓股",
        "type": "table",
        "table": {
            "headers": ["序号", "股票代码", "股票名称", "占净值比例", "持仓市值"],
            "rows": rows
        }
    }
```

4. **修改现有函数：支持 AkShare 数据格式**

```python
def format_asset_chart(fund_obj: dict[str, Any]) -> ChartConfig | None:
    """生成资产配置环形图（增强以支持 AkShare 数据）。"""
    sym = str(fund_obj.get("symbol") or "")
    
    # 优先使用 detail_hold 数据（AkShare 格式）
    detail_hold = fund_obj.get("detail_hold")
    if detail_hold and detail_hold.get("ok"):
        records = detail_hold.get("data", [])
        if records:
            labels = [r.get("资产类型", "") for r in records]
            values = [float(r.get("仓位占比", 0)) for r in records]
            
            if labels and values:
                colors = DEFAULT_COLORS[:len(labels)]
                return {
                    "id": f"asset_{sym}",
                    "title": "资产配置",
                    "type": "pie",
                    "data": {"labels": labels, "values": values, "colors": colors},
                    "options": {
                        "showPercentage": True,
                        "innerRadius": "50%"
                    }
                }
    
    # 兜底：使用原有逻辑
    # ... (保留原有代码)
```

**关键设计决策**：
1. 保持向后兼容：原有函数继续支持旧数据格式
2. 优先使用 AkShare 数据：新增判断逻辑，优先处理 AkShare 格式
3. 数据校验：检查 `ok` 字段和数据完整性
4. 优雅降级：数据不足时返回 None，由调用方决定是否隐藏模块


### 模块 3: ProductInterpretAgent 修改（Agent 编排层）

**文件路径**：`backend/agents/fund_agent/product_interpret/agent.py`

**修改内容**：

```python
from pkg.akshare_client import AkShareClient
from pkg.fund_formatter import (
    build_single_output,
    format_nav_chart_from_akshare,
    format_industry_chart,
    format_holding_table
)
import json
import logging

class ProductInterpretAgent:
    """单只基金解读 Agent（修改以使用 AkShare 数据）。"""
    
    def __init__(self):
        self.akshare_client = AkShareClient()
        self.logger = logging.getLogger(__name__)
    
    async def run(self, question: str, ctx: AgentRunContext) -> str:
        """执行基金解读任务。
        
        Args:
            question: 用户问题（包含基金代码或名称）
            ctx: 运行上下文
        
        Returns:
            JSON 字符串（FundAnalysisOutput）或纯文本（兜底）
        """
        # 1. 提取基金代码
        symbol = self._extract_symbol(question)
        if not symbol:
            return "请提供有效的基金代码或名称。"
        
        self.logger.info(
            f"Starting fund analysis for {symbol}",
            extra={"traceId": ctx.trace_id, "answerId": ctx.answer_id}
        )
        
        # 2. 获取 AkShare 数据
        try:
            fund_data = await self.akshare_client.get_all_data(symbol)
            
            # 检查是否有足够的数据
            if not self._has_sufficient_data(fund_data):
                self.logger.warning(
                    f"Insufficient data for {symbol}, falling back to text",
                    extra={"traceId": ctx.trace_id}
                )
                return await self._fallback_text_analysis(question, ctx)
            
        except Exception as e:
            self.logger.error(
                f"Failed to fetch data for {symbol}: {e}",
                extra={"traceId": ctx.trace_id}
            )
            return await self._fallback_text_analysis(question, ctx)
        
        # 3. 调用 LLM 生成分析文本
        llm_text = await self._generate_analysis_text(fund_data, question, ctx)
        
        # 4. 使用 fund_formatter 构建结构化输出
        try:
            # 添加额外的图表（净值走势、行业配置、持仓明细）
            nav_data = await self.akshare_client.get_nav_data(symbol, period="1年")
            industry_data = await self.akshare_client.get_industry_allocation(symbol)
            holding_data = await self.akshare_client.get_portfolio_hold(symbol)
            
            # 构建 supplier_data（兼容 fund_formatter 接口）
            supplier_data = {
                "payload": {
                    "funds": [fund_data]
                }
            }
            
            # 生成结构化输出
            structured_output = build_single_output(supplier_data, llm_text)
            
            # 添加额外图表
            if nav_chart := format_nav_chart_from_akshare(nav_data, symbol):
                structured_output["charts"].append(nav_chart)
            
            if industry_chart := format_industry_chart(industry_data, symbol):
                structured_output["charts"].append(industry_chart)
            
            if holding_table := format_holding_table(holding_data, symbol):
                structured_output["sections"].append(holding_table)
            
            return json.dumps(structured_output, ensure_ascii=False)
            
        except Exception as e:
            self.logger.error(
                f"Failed to build structured output: {e}",
                extra={"traceId": ctx.trace_id}
            )
            # 兜底：返回纯文本
            return llm_text
    
    def _extract_symbol(self, question: str) -> str | None:
        """从用户问题中提取基金代码。"""
        # 简单实现：查找 6 位数字
        import re
        match = re.search(r'\b\d{6}\b', question)
        return match.group(0) if match else None
    
    def _has_sufficient_data(self, fund_data: dict) -> bool:
        """检查是否有足够的数据生成分析。"""
        # 至少需要基本信息和业绩数据
        return (
            fund_data.get("basic_info", {}).get("ok") and
            fund_data.get("achievement", {}).get("ok")
        )
    
    async def _generate_analysis_text(
        self,
        fund_data: dict,
        question: str,
        ctx: AgentRunContext
    ) -> str:
        """调用 LLM 生成分析文本。"""
        # 构建 prompt
        system_prompt = """你是专业的基金分析师。请根据提供的基金数据，生成详细的分析报告。
        
报告应包含：
1. 基金概况
2. 业绩表现分析
3. 风险收益特征
4. 投资建议
5. 风险提示

请使用【标题】格式组织内容，便于前端解析。"""
        
        user_prompt = f"""用户问题：{question}

基金数据：
{json.dumps(fund_data, ensure_ascii=False, indent=2)}

请生成分析报告。"""
        
        # 调用 LLM（使用 model_gateway）
        from model_gateway import llm_chat
        
        response = await llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4",
            trace_id=ctx.trace_id
        )
        
        return response.get("content", "")
    
    async def _fallback_text_analysis(
        self,
        question: str,
        ctx: AgentRunContext
    ) -> str:
        """兜底：生成纯文本分析（不含图表）。"""
        system_prompt = "你是专业的基金分析师。请根据用户问题提供分析建议。"
        
        from model_gateway import llm_chat
        
        response = await llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            model="gpt-4",
            trace_id=ctx.trace_id
        )
        
        return response.get("content", "")
```

**关键设计决策**：
1. 异步执行：使用 async/await 提升性能
2. 分步骤：数据获取 → LLM 生成 → 结构化输出
3. 多层兜底：
   - 数据不足 → 纯文本分析
   - 结构化失败 → 返回 LLM 文本
   - 全部失败 → 返回错误提示
4. 日志记录：记录 traceId、answerId，便于排查问题


### 模块 4: ProductCompareAgent 修改（Agent 编排层）

**文件路径**：`backend/agents/fund_agent/product_compare/agent.py`

**修改内容**：

```python
from pkg.akshare_client import AkShareClient
from pkg.fund_formatter import build_compare_output
import json
import logging
import asyncio

class ProductCompareAgent:
    """多基金对比 Agent（修改以使用 AkShare 数据）。"""
    
    def __init__(self):
        self.akshare_client = AkShareClient()
        self.logger = logging.getLogger(__name__)
    
    async def run(self, question: str, ctx: AgentRunContext) -> str:
        """执行基金对比任务。
        
        Args:
            question: 用户问题（包含多个基金代码）
            ctx: 运行上下文
        
        Returns:
            JSON 字符串（FundAnalysisOutput）或纯文本（兜底）
        """
        # 1. 提取基金代码列表
        symbols = self._extract_symbols(question)
        if len(symbols) < 2:
            return "请提供至少 2 只基金的代码进行对比。"
        
        if len(symbols) > 5:
            symbols = symbols[:5]
            self.logger.warning(f"Too many symbols, limiting to 5")
        
        self.logger.info(
            f"Starting fund comparison for {symbols}",
            extra={"traceId": ctx.trace_id, "answerId": ctx.answer_id}
        )
        
        # 2. 并发获取多只基金数据
        try:
            tasks = [self.akshare_client.get_all_data(sym) for sym in symbols]
            funds_data = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 过滤失败的基金
            valid_funds = []
            for i, data in enumerate(funds_data):
                if isinstance(data, Exception):
                    self.logger.warning(f"Failed to fetch {symbols[i]}: {data}")
                elif self._has_sufficient_data(data):
                    valid_funds.append(data)
                else:
                    self.logger.warning(f"Insufficient data for {symbols[i]}")
            
            if len(valid_funds) < 2:
                self.logger.warning("Not enough valid funds for comparison")
                return await self._fallback_text_comparison(question, ctx)
            
        except Exception as e:
            self.logger.error(f"Failed to fetch comparison data: {e}")
            return await self._fallback_text_comparison(question, ctx)
        
        # 3. 调用 LLM 生成对比分析文本
        llm_text = await self._generate_comparison_text(valid_funds, question, ctx)
        
        # 4. 使用 fund_formatter 构建结构化输出
        try:
            supplier_data = {
                "payload": {
                    "funds": valid_funds
                }
            }
            
            structured_output = build_compare_output(supplier_data, llm_text)
            
            return json.dumps(structured_output, ensure_ascii=False)
            
        except Exception as e:
            self.logger.error(f"Failed to build comparison output: {e}")
            return llm_text
    
    def _extract_symbols(self, question: str) -> list[str]:
        """从用户问题中提取基金代码列表。"""
        import re
        matches = re.findall(r'\b\d{6}\b', question)
        return list(set(matches))  # 去重
    
    def _has_sufficient_data(self, fund_data: dict) -> bool:
        """检查是否有足够的数据。"""
        return (
            fund_data.get("basic_info", {}).get("ok") and
            fund_data.get("achievement", {}).get("ok")
        )
    
    async def _generate_comparison_text(
        self,
        funds_data: list[dict],
        question: str,
        ctx: AgentRunContext
    ) -> str:
        """调用 LLM 生成对比分析文本。"""
        system_prompt = """你是专业的基金分析师。请根据提供的多只基金数据，生成详细的对比分析报告。

报告应包含：
1. 基金概况对比
2. 业绩表现对比
3. 风险收益特征对比
4. 投资建议
5. 风险提示

请使用【标题】格式组织内容。"""
        
        user_prompt = f"""用户问题：{question}

基金数据：
{json.dumps(funds_data, ensure_ascii=False, indent=2)}

请生成对比分析报告。"""
        
        from model_gateway import llm_chat
        
        response = await llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4",
            trace_id=ctx.trace_id
        )
        
        return response.get("content", "")
    
    async def _fallback_text_comparison(
        self,
        question: str,
        ctx: AgentRunContext
    ) -> str:
        """兜底：生成纯文本对比分析。"""
        system_prompt = "你是专业的基金分析师。请根据用户问题提供对比分析建议。"
        
        from model_gateway import llm_chat
        
        response = await llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            model="gpt-4",
            trace_id=ctx.trace_id
        )
        
        return response.get("content", "")
```

**关键设计决策**：
1. 并发获取：使用 `asyncio.gather` 同时获取多只基金数据
2. 容错处理：部分基金失败不影响其他基金
3. 数量限制：最多对比 5 只基金（避免性能问题）
4. 兜底机制：数据不足时返回纯文本对比


## 数据流设计

### 单基金解读数据流

```
用户输入 "分析基金 000001"
    ↓
ProductInterpretAgent.run()
    ↓
1. 提取基金代码: "000001"
    ↓
2. AkShareClient.get_all_data("000001")
    ├─ get_basic_info() → {"ok": True, "data": [...]}
    ├─ get_achievement() → {"ok": True, "data": [...]}
    ├─ get_analysis() → {"ok": True, "data": [...]}
    ├─ get_detail_hold() → {"ok": True, "data": [...]}
    ├─ get_detail_info() → {"ok": True, "data": [...]}
    └─ get_nav_data() → {"ok": True, "data": [...]}
    ↓
3. 检查数据完整性
    ├─ 数据充足 → 继续
    └─ 数据不足 → 兜底：纯文本分析
    ↓
4. LLM 生成分析文本
    ↓
5. fund_formatter.build_single_output()
    ├─ format_fund_cards() → 生成卡片
    ├─ format_asset_chart() → 生成资产配置图
    ├─ format_nav_chart_from_akshare() → 生成净值走势图
    ├─ format_industry_chart() → 生成行业配置图
    └─ format_holding_table() → 生成持仓明细表
    ↓
6. 返回 FundAnalysisOutput JSON
    ↓
前端解析并渲染
```

### 多基金对比数据流

```
用户输入 "对比基金 000001 和 000002"
    ↓
ProductCompareAgent.run()
    ↓
1. 提取基金代码列表: ["000001", "000002"]
    ↓
2. 并发获取数据
    ├─ AkShareClient.get_all_data("000001") → fund_data_1
    └─ AkShareClient.get_all_data("000002") → fund_data_2
    ↓
3. 过滤有效数据
    ├─ fund_data_1 有效 → 保留
    └─ fund_data_2 有效 → 保留
    ↓
4. 检查有效基金数量
    ├─ >= 2 → 继续
    └─ < 2 → 兜底：纯文本对比
    ↓
5. LLM 生成对比分析文本
    ↓
6. fund_formatter.build_compare_output()
    ├─ format_fund_cards() → 为每只基金生成卡片
    ├─ format_performance_table() → 生成业绩对比表
    ├─ format_fee_table() → 生成费率对比表
    ├─ format_nav_chart() → 生成净值走势对比图
    └─ format_style_radar() → 生成风格对比雷达图
    ↓
7. 返回 FundAnalysisOutput JSON (mode="compare")
    ↓
前端解析并渲染
```

## 接口设计

### AkShareClient 接口

```python
class AkShareClient:
    async def get_basic_info(symbol: str) -> Dict[str, Any]
    async def get_achievement(symbol: str) -> Dict[str, Any]
    async def get_analysis(symbol: str) -> Dict[str, Any]
    async def get_detail_hold(symbol: str) -> Dict[str, Any]
    async def get_detail_info(symbol: str) -> Dict[str, Any]
    async def get_nav_data(symbol: str, period: str = "1年") -> Dict[str, Any]
    async def get_industry_allocation(symbol: str, date: str = "2023") -> Dict[str, Any]
    async def get_portfolio_hold(symbol: str, date: str = "2023") -> Dict[str, Any]
    async def get_all_data(symbol: str) -> Dict[str, Any]
```

**返回格式**：
```python
{
    "ok": True,  # 或 False
    "data": [...],  # 数据列表或字典
    "message": "错误信息"  # 仅在 ok=False 时存在
}
```

### fund_formatter 新增接口

```python
def format_nav_chart_from_akshare(
    nav_data: Dict[str, Any],
    symbol: str
) -> ChartConfig | None

def format_industry_chart(
    industry_data: Dict[str, Any],
    symbol: str
) -> ChartConfig | None

def format_holding_table(
    holding_data: Dict[str, Any],
    symbol: str
) -> TableSection | None
```

### Agent 接口（保持不变）

```python
class ProductInterpretAgent:
    async def run(question: str, ctx: AgentRunContext) -> str

class ProductCompareAgent:
    async def run(question: str, ctx: AgentRunContext) -> str
```

## 错误处理设计

### 错误分类

1. **网络错误**
   - 场景：AkShare API 请求失败
   - 处理：重试 3 次，失败后返回 `{"ok": False, "message": "..."}`
   - 日志：ERROR 级别，记录 traceId、symbol、错误详情

2. **数据格式错误**
   - 场景：AkShare 返回数据格式异常
   - 处理：记录日志，返回 `{"ok": False, "message": "..."}`
   - 日志：WARNING 级别，记录原始数据（脱敏）

3. **数据不足错误**
   - 场景：关键数据缺失（如基本信息、业绩数据）
   - 处理：降级为纯文本分析
   - 日志：WARNING 级别，记录缺失的数据类型

4. **LLM 生成错误**
   - 场景：LLM 调用失败或超时
   - 处理：返回友好的错误提示
   - 日志：ERROR 级别，记录 traceId、错误详情

5. **结构化输出错误**
   - 场景：fund_formatter 处理失败
   - 处理：返回 LLM 生成的纯文本
   - 日志：ERROR 级别，记录异常堆栈

### 错误处理流程

```python
try:
    # 1. 获取数据
    fund_data = await akshare_client.get_all_data(symbol)
    
    # 2. 检查数据完整性
    if not has_sufficient_data(fund_data):
        logger.warning("Insufficient data, falling back")
        return await fallback_text_analysis(question, ctx)
    
    # 3. 生成分析
    llm_text = await generate_analysis_text(fund_data, question, ctx)
    
    # 4. 构建结构化输出
    structured_output = build_single_output(supplier_data, llm_text)
    
    return json.dumps(structured_output, ensure_ascii=False)
    
except AkShareAPIError as e:
    logger.error(f"AkShare API error: {e}", extra={"traceId": ctx.trace_id})
    return await fallback_text_analysis(question, ctx)
    
except LLMError as e:
    logger.error(f"LLM error: {e}", extra={"traceId": ctx.trace_id})
    return "抱歉，分析服务暂时不可用，请稍后再试。"
    
except Exception as e:
    logger.error(f"Unexpected error: {e}", extra={"traceId": ctx.trace_id})
    return "抱歉，系统出现异常，请稍后再试。"
```


## 性能优化设计

### 1. 缓存策略

**内存缓存（第一阶段）**：
```python
from functools import lru_cache
import time

class AkShareClient:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 3600  # 1 小时
    
    def _get_cache_key(self, func_name: str, *args, **kwargs) -> str:
        """生成缓存键。"""
        return f"{func_name}:{args}:{kwargs}"
    
    def _get_from_cache(self, key: str) -> Dict[str, Any] | None:
        """从缓存获取数据。"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return data
            else:
                del self._cache[key]
        return None
    
    def _set_to_cache(self, key: str, data: Dict[str, Any]):
        """设置缓存。"""
        self._cache[key] = (data, time.time())
    
    async def get_basic_info(self, symbol: str) -> Dict[str, Any]:
        """获取基本信息（带缓存）。"""
        cache_key = self._get_cache_key("basic_info", symbol)
        
        # 尝试从缓存获取
        if cached := self._get_from_cache(cache_key):
            return cached
        
        # 缓存未命中，调用 API
        result = await self._retry_call(
            ak.fund_individual_basic_info_xq,
            symbol=symbol
        )
        
        # 设置缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
```

**Redis 缓存（第二阶段，可选）**：
```python
import redis.asyncio as redis
import json

class AkShareClient:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.cache_ttl = 3600
    
    async def _get_from_redis(self, key: str) -> Dict[str, Any] | None:
        """从 Redis 获取缓存。"""
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def _set_to_redis(self, key: str, data: Dict[str, Any]):
        """设置 Redis 缓存。"""
        await self.redis.setex(
            key,
            self.cache_ttl,
            json.dumps(data, ensure_ascii=False)
        )
```

### 2. 并发优化

**并发获取多只基金数据**：
```python
async def get_multiple_funds(self, symbols: list[str]) -> list[Dict[str, Any]]:
    """并发获取多只基金数据。
    
    限制：最多 3 个并发请求（避免触发反爬）
    """
    semaphore = asyncio.Semaphore(3)
    
    async def fetch_with_limit(symbol: str):
        async with semaphore:
            return await self.get_all_data(symbol)
    
    tasks = [fetch_with_limit(sym) for sym in symbols]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### 3. 数据降采样

**净值数据降采样**（减少前端渲染压力）：
```python
def downsample_nav_data(records: list[dict], max_points: int = 100) -> list[dict]:
    """对净值数据进行降采样。
    
    Args:
        records: 原始净值数据
        max_points: 最大数据点数
    
    Returns:
        降采样后的数据
    """
    if len(records) <= max_points:
        return records
    
    # 使用均匀采样
    step = len(records) // max_points
    return records[::step]
```

### 4. 性能监控

**添加性能指标记录**：
```python
import time
from pkg.metrics import record_metric

class ProductInterpretAgent:
    async def run(self, question: str, ctx: AgentRunContext) -> str:
        start_time = time.time()
        
        # 1. 数据获取阶段
        fetch_start = time.time()
        fund_data = await self.akshare_client.get_all_data(symbol)
        fetch_duration = time.time() - fetch_start
        record_metric("akshare.fetch.duration", fetch_duration, {"symbol": symbol})
        
        # 2. LLM 生成阶段
        llm_start = time.time()
        llm_text = await self._generate_analysis_text(fund_data, question, ctx)
        llm_duration = time.time() - llm_start
        record_metric("llm.generate.duration", llm_duration)
        
        # 3. 格式化阶段
        format_start = time.time()
        structured_output = build_single_output(supplier_data, llm_text)
        format_duration = time.time() - format_start
        record_metric("formatter.build.duration", format_duration)
        
        # 总耗时
        total_duration = time.time() - start_time
        record_metric("agent.total.duration", total_duration, {"agent": "interpret"})
        
        return json.dumps(structured_output, ensure_ascii=False)
```

## 测试策略

### 1. 单元测试

**AkShareClient 测试**：
```python
# tests/test_akshare_client.py
import pytest
from unittest.mock import AsyncMock, patch
from pkg.akshare_client import AkShareClient

@pytest.mark.asyncio
async def test_get_basic_info_success():
    """测试成功获取基本信息。"""
    client = AkShareClient()
    
    with patch('akshare.fund_individual_basic_info_xq') as mock_ak:
        mock_ak.return_value = pd.DataFrame([
            {"item": "基金代码", "value": "000001"},
            {"item": "基金名称", "value": "华夏成长"}
        ])
        
        result = await client.get_basic_info("000001")
        
        assert result["ok"] is True
        assert len(result["data"]) == 2

@pytest.mark.asyncio
async def test_get_basic_info_retry():
    """测试重试机制。"""
    client = AkShareClient(max_retries=3)
    
    with patch('akshare.fund_individual_basic_info_xq') as mock_ak:
        # 前两次失败，第三次成功
        mock_ak.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            pd.DataFrame([{"item": "基金代码", "value": "000001"}])
        ]
        
        result = await client.get_basic_info("000001")
        
        assert result["ok"] is True
        assert mock_ak.call_count == 3

@pytest.mark.asyncio
async def test_get_all_data_concurrent():
    """测试并发获取所有数据。"""
    client = AkShareClient()
    
    result = await client.get_all_data("000001")
    
    assert "symbol" in result
    assert "basic_info" in result
    assert "achievement" in result
```

**fund_formatter 测试**：
```python
# tests/test_fund_formatter_akshare.py
import pytest
from pkg.fund_formatter import (
    format_nav_chart_from_akshare,
    format_industry_chart,
    format_holding_table
)

def test_format_nav_chart_from_akshare():
    """测试净值图表格式化。"""
    nav_data = {
        "ok": True,
        "data": [
            {"净值日期": "2023-01-01", "单位净值": 1.0, "日增长率": 0},
            {"净值日期": "2023-01-02", "单位净值": 1.01, "日增长率": 1.0},
            {"净值日期": "2023-01-03", "单位净值": 1.02, "日增长率": 0.99}
        ]
    }
    
    chart = format_nav_chart_from_akshare(nav_data, "000001")
    
    assert chart is not None
    assert chart["type"] == "line"
    assert len(chart["data"]["xAxis"]) == 3
    assert len(chart["data"]["series"][0]["data"]) == 3

def test_format_industry_chart():
    """测试行业配置图表格式化。"""
    industry_data = {
        "ok": True,
        "data": [
            {"行业类别": "制造业", "占净值比例": 56.58},
            {"行业类别": "信息技术", "占净值比例": 15.32}
        ]
    }
    
    chart = format_industry_chart(industry_data, "000001")
    
    assert chart is not None
    assert chart["type"] == "bar"
    assert len(chart["data"]["xAxis"]) == 2
```

### 2. 集成测试

```python
# tests/integration/test_fund_analysis_e2e.py
import pytest
from agents.fund_agent.product_interpret.agent import ProductInterpretAgent

@pytest.mark.asyncio
@pytest.mark.integration
async def test_single_fund_analysis_e2e():
    """端到端测试：单基金分析。"""
    agent = ProductInterpretAgent()
    ctx = AgentRunContext(trace_id="test-123", answer_id="ans-456")
    
    result = await agent.run("分析基金 000001", ctx)
    
    # 验证返回 JSON
    import json
    output = json.loads(result)
    
    assert output["type"] == "fund_analysis"
    assert output["mode"] == "single"
    assert len(output["cards"]) > 0
    assert len(output["charts"]) > 0

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fund_comparison_e2e():
    """端到端测试：基金对比。"""
    agent = ProductCompareAgent()
    ctx = AgentRunContext(trace_id="test-123", answer_id="ans-456")
    
    result = await agent.run("对比基金 000001 和 000002", ctx)
    
    import json
    output = json.loads(result)
    
    assert output["type"] == "fund_analysis"
    assert output["mode"] == "compare"
    assert len(output["sections"]) > 0  # 应包含对比表格
```

### 3. 性能测试

```python
# tests/performance/test_performance.py
import pytest
import time
from agents.fund_agent.product_interpret.agent import ProductInterpretAgent

@pytest.mark.performance
@pytest.mark.asyncio
async def test_single_fund_performance():
    """性能测试：单基金分析响应时间。"""
    agent = ProductInterpretAgent()
    ctx = AgentRunContext(trace_id="perf-test", answer_id="perf-ans")
    
    start = time.time()
    result = await agent.run("分析基金 000001", ctx)
    duration = time.time() - start
    
    # 验收标准：< 3 秒
    assert duration < 3.0, f"Response time {duration}s exceeds 3s limit"

@pytest.mark.performance
@pytest.mark.asyncio
async def test_cache_hit_rate():
    """性能测试：缓存命中率。"""
    agent = ProductInterpretAgent()
    ctx = AgentRunContext(trace_id="cache-test", answer_id="cache-ans")
    
    # 第一次请求（缓存未命中）
    await agent.run("分析基金 000001", ctx)
    
    # 第二次请求（应命中缓存）
    start = time.time()
    await agent.run("分析基金 000001", ctx)
    duration = time.time() - start
    
    # 缓存命中应该更快
    assert duration < 1.0, "Cache hit should be faster"
```


## 部署设计

### 1. 依赖管理

**requirements.txt 更新**：
```txt
# 现有依赖
...

# 新增依赖
akshare>=1.18.54
pandas>=2.0.0
redis>=5.0.0  # 可选，用于 Redis 缓存
```

**安装命令**：
```bash
pip install akshare>=1.18.54
```

### 2. 配置管理

**config/akshare_config.py**（新增）：
```python
from pydantic import BaseSettings

class AkShareConfig(BaseSettings):
    """AkShare 配置。"""
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 限流配置
    request_interval: float = 0.5
    max_concurrent: int = 3
    
    # 缓存配置
    cache_enabled: bool = True
    cache_ttl: int = 3600  # 1 小时
    cache_type: str = "memory"  # "memory" 或 "redis"
    redis_url: str = "redis://localhost:6379"
    
    # 数据配置
    default_nav_period: str = "1年"
    max_nav_points: int = 100  # 净值数据最大点数（降采样）
    
    class Config:
        env_prefix = "AKSHARE_"
        env_file = ".env"

# 全局配置实例
akshare_config = AkShareConfig()
```

**.env 配置示例**：
```bash
# AkShare 配置
AKSHARE_MAX_RETRIES=3
AKSHARE_RETRY_DELAY=1.0
AKSHARE_REQUEST_INTERVAL=0.5
AKSHARE_CACHE_ENABLED=true
AKSHARE_CACHE_TTL=3600
AKSHARE_CACHE_TYPE=memory
AKSHARE_REDIS_URL=redis://localhost:6379
```

### 3. 日志配置

**logging_config.py 更新**：
```python
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(traceId)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/akshare.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "default"
        }
    },
    "loggers": {
        "pkg.akshare_client": {
            "level": "INFO",
            "handlers": ["console", "file"]
        },
        "agents.fund_agent": {
            "level": "INFO",
            "handlers": ["console", "file"]
        }
    }
}
```

### 4. 监控配置

**Prometheus 指标**：
```python
from prometheus_client import Counter, Histogram

# AkShare API 调用指标
akshare_api_calls = Counter(
    "akshare_api_calls_total",
    "Total AkShare API calls",
    ["method", "status"]
)

akshare_api_duration = Histogram(
    "akshare_api_duration_seconds",
    "AkShare API call duration",
    ["method"]
)

# Agent 执行指标
agent_execution_duration = Histogram(
    "agent_execution_duration_seconds",
    "Agent execution duration",
    ["agent_type"]
)

# 缓存指标
cache_hits = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type"]
)

cache_misses = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type"]
)
```

## 安全设计

### 1. 输入验证

```python
def validate_symbol(symbol: str) -> bool:
    """验证基金代码格式。
    
    Args:
        symbol: 基金代码
    
    Returns:
        是否有效
    """
    import re
    # 基金代码：6 位数字
    return bool(re.match(r'^\d{6}$', symbol))

def sanitize_input(question: str) -> str:
    """清理用户输入，防止注入攻击。
    
    Args:
        question: 用户问题
    
    Returns:
        清理后的问题
    """
    # 移除特殊字符
    import re
    return re.sub(r'[^\w\s\u4e00-\u9fff]', '', question)
```

### 2. 敏感信息脱敏

```python
def mask_sensitive_data(data: dict) -> dict:
    """脱敏敏感数据（用于日志）。
    
    Args:
        data: 原始数据
    
    Returns:
        脱敏后的数据
    """
    masked = data.copy()
    
    # 脱敏用户 ID
    if "userId" in masked:
        masked["userId"] = masked["userId"][:4] + "****"
    
    # 脱敏手机号
    if "phone" in masked:
        masked["phone"] = masked["phone"][:3] + "****" + masked["phone"][-4:]
    
    return masked
```

### 3. 限流保护

```python
from collections import defaultdict
import time

class RateLimiter:
    """简单的限流器。"""
    
    def __init__(self, max_requests: int = 100, window: int = 60):
        """初始化限流器。
        
        Args:
            max_requests: 时间窗口内最大请求数
            window: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id: str) -> bool:
        """检查是否允许请求。
        
        Args:
            user_id: 用户 ID
        
        Returns:
            是否允许
        """
        now = time.time()
        
        # 清理过期请求
        self.requests[user_id] = [
            t for t in self.requests[user_id]
            if now - t < self.window
        ]
        
        # 检查是否超限
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        # 记录请求
        self.requests[user_id].append(now)
        return True
```

## 回滚计划

### 回滚触发条件

1. **数据获取成功率 < 90%**（持续 10 分钟）
2. **响应时间 > 5 秒**（P95，持续 10 分钟）
3. **错误率 > 5%**（持续 10 分钟）
4. **P0 级别 Bug**（影响核心功能）

### 回滚步骤

1. **立即回滚代码**：
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

2. **重启服务**：
   ```bash
   systemctl restart fund-analysis-service
   ```

3. **验证回滚**：
   - 检查服务状态
   - 验证核心功能
   - 检查监控指标

4. **通知相关人员**：
   - 发送回滚通知
   - 说明回滚原因
   - 提供临时解决方案

### 灰度发布计划

1. **阶段 1**：内部测试（1-2 天）
   - 部署到测试环境
   - 内部团队测试
   - 修复发现的问题

2. **阶段 2**：小流量灰度（3-5 天）
   - 5% 用户流量
   - 监控关键指标
   - 收集用户反馈

3. **阶段 3**：中流量灰度（3-5 天）
   - 30% 用户流量
   - 持续监控
   - 优化性能

4. **阶段 4**：全量发布（1 天）
   - 100% 用户流量
   - 密切监控
   - 准备回滚方案

## 相关文档

- [需求文档](./requirements.md)
- [AkShare 数据可用性分析](../../../docs/akshare_data_availability.md)
- [多模态输出设计文档](../../../docs/multimodal_output_design.md)
- [fund_formatter.py](../../../backend/pkg/fund_formatter.py)
- [Python 后端开发规范](../../steering/python-backend.md)

## 设计决策记录（ADR）

### ADR-1: 使用异步 API

**日期**：2026-04-10

**状态**：已接受

**背景**：
- 需要并发获取多只基金数据
- 需要提升系统响应速度

**决策**：
- 使用 asyncio 实现异步 API
- AkShareClient 所有方法都是异步的
- Agent 使用 async/await 编排

**后果**：
- 优点：性能提升，支持并发
- 缺点：代码复杂度增加，需要异步运行时

### ADR-2: 使用内存缓存（第一阶段）

**日期**：2026-04-10

**状态**：已接受

**背景**：
- 需要减少 AkShare API 调用
- 需要提升响应速度

**决策**：
- 第一阶段使用内存缓存（lru_cache）
- 第二阶段可选升级为 Redis 缓存
- TTL 设置为 1 小时

**后果**：
- 优点：实现简单，无额外依赖
- 缺点：多实例不共享缓存，重启后缓存丢失

### ADR-3: 保留兜底机制

**日期**：2026-04-10

**状态**：已接受

**背景**：
- AkShare 数据源可能不稳定
- 需要确保系统可用性

**决策**：
- 数据获取失败时返回纯文本分析
- 结构化输出失败时返回 LLM 文本
- 保留原有的纯文本分析能力

**后果**：
- 优点：系统稳定性高，用户体验好
- 缺点：需要维护两套逻辑

## 更新记录

| 日期 | 版本 | 修改内容 | 修改人 |
|------|------|----------|--------|
| 2026-04-10 | 1.0 | 初始版本 | AI Assistant |
