# 性能监控指标说明

## 概述

为了验证性能优化效果，我们添加了完整的性能监控体系，覆盖：
- API 调用（akshare 等外部接口）
- LLM 调用（MiniMax 等模型）
- 模块耗时（数据获取、任务规划等）

## 监控指标

### 1. API 调用指标

每个 API 调用会记录：

| 指标 | 说明 | 用途 |
|------|------|------|
| **平均耗时** | 所有成功调用的平均时间 | 识别慢接口 |
| **P95 耗时** | 95% 的调用在此时间内完成 | 识别异常慢的调用 |
| **P99 耗时** | 99% 的调用在此时间内完成 | 识别极端情况 |
| **超时率** | 超时次数 / 总调用次数 | 评估接口稳定性 |
| **成功/超时/错误次数** | 各状态的调用次数 | 评估接口可用性 |

**示例输出**：
```
【API 调用指标】
  fund_individual_basic_info_xq:
    调用次数: 10 (成功: 8, 超时: 1, 错误: 1)
    超时率: 10.00%
    平均耗时: 0.450s, P95: 0.800s, P99: 1.200s
```

### 2. LLM 调用指标

每个 LLM 调用会记录：

| 指标 | 说明 | 用途 |
|------|------|------|
| **平均耗时** | LLM 调用总时间 | 评估模型响应速度 |
| **平均输入 tokens** | 输入文本的 token 数量 | 优化 prompt 长度 |
| **平均输出 tokens** | 输出文本的 token 数量 | 控制生成长度 |
| **平均首 token 延迟** | 从请求到第一个 token 的时间 | 优化用户体验（流式） |

**示例输出**：
```
【LLM 调用指标】
  MiniMax-M2.5-highspeed:
    调用次数: 5
    平均耗时: 15.234s
    平均输入 tokens: 1250
    平均输出 tokens: 450
    平均首 token 延迟: 2.345s
```

### 3. 模块耗时指标

识别性能瓶颈：

| 指标 | 说明 | 用途 |
|------|------|------|
| **平均耗时** | 模块的平均执行时间 | 识别慢模块 |
| **最大耗时** | 模块的最慢一次执行 | 识别异常情况 |
| **总耗时** | 模块的累计时间 | 评估整体影响 |

**示例输出**：
```
【模块耗时指标】
  fetch_performance_000042:
    调用次数: 1
    平均耗时: 5.234s, 最大耗时: 5.234s
  
  fetch_basic_info_000042:
    调用次数: 1
    平均耗时: 0.450s, 最大耗时: 0.450s
  
  ⚠️  最慢模块: fetch_performance_000042
```

## 使用方式

### 1. 在代码中记录指标

#### API 调用监控

```python
from pkg.metrics import get_metrics_collector
import time

metrics_collector = get_metrics_collector()

# 记录成功调用
start_time = time.time()
try:
    result = await api_call()
    duration = time.time() - start_time
    metrics_collector.record_api_success("api_name", duration)
except TimeoutError:
    metrics_collector.record_api_timeout("api_name")
except Exception:
    metrics_collector.record_api_error("api_name")
```

#### LLM 调用监控

```python
from pkg.metrics import get_metrics_collector
import time

metrics_collector = get_metrics_collector()

# 估算输入 tokens
input_text = "".join(m.get("content", "") for m in messages)
input_tokens = len(input_text) // 4

start_time = time.time()
first_token_time = None

# 流式调用
async for token in llm_stream():
    if first_token_time is None:
        first_token_time = time.time() - start_time
    # ...

duration = time.time() - start_time
output_tokens = len(output_text) // 4

metrics_collector.record_llm_call(
    llm_name="model_name",
    duration=duration,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    first_token_latency=first_token_time,
)
```

#### 模块耗时监控

```python
from pkg.metrics import Timer

# 方式 1：使用上下文管理器
with Timer("module_name"):
    # 执行模块代码
    result = await some_operation()

# 方式 2：手动记录
from pkg.metrics import get_metrics_collector
import time

metrics_collector = get_metrics_collector()
start = time.time()
result = await some_operation()
duration = time.time() - start
metrics_collector.record_module_duration("module_name", duration)
```

### 2. 查看监控摘要

监控摘要会在每次请求结束时自动打印到日志：

```python
from pkg.metrics import get_metrics_collector

metrics_collector = get_metrics_collector()
metrics_collector.print_summary()
```

### 3. 重置指标

如果需要清空历史数据：

```python
from pkg.metrics import get_metrics_collector

metrics_collector = get_metrics_collector()
metrics_collector.reset()
```

## 已集成的监控点

### 1. API 调用（`backend/agents/skills/product_compare/runtime.py`）

- `fund_individual_basic_info_xq` - 基本信息
- `fund_individual_achievement_xq` - 业绩概要
- `fund_individual_profit_probability_xq` - 盈亏概率
- `fund_portfolio_hold_em` - 资产配置

### 2. LLM 调用（`backend/agents/fund_agent/runtime.py`）

- 流式调用：记录首 token 延迟
- 非流式调用：记录总耗时

### 3. 模块耗时（`backend/orchestrator/run.py`）

- 初始化
- 任务规划
- 输入合规检查
- Agent 执行
- 输出合规检查
- 审计落库

## 性能告警阈值

建议设置以下告警阈值：

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| API 平均耗时 | > 3s | > 5s |
| API 超时率 | > 10% | > 30% |
| LLM 平均耗时 | > 20s | > 40s |
| 首 token 延迟 | > 5s | > 10s |
| 总请求耗时 | > 30s | > 60s |

## 优化前后对比

### 优化前（预期）

```
【API 调用指标】
  fund_individual_achievement_xq:
    调用次数: 1 (成功: 0, 超时: 1, 错误: 0)
    超时率: 100.00%
    平均耗时: N/A, P95: N/A, P99: N/A

【模块耗时指标】
  fetch_performance_000042:
    平均耗时: 19.500s, 最大耗时: 19.500s
  
  ⚠️  最慢模块: fetch_performance_000042

总耗时: 61.077s
```

### 优化后（预期）

```
【API 调用指标】
  fund_individual_achievement_xq:
    调用次数: 1 (成功: 1, 超时: 0, 错误: 0)
    超时率: 0.00%
    平均耗时: 0.450s, P95: 0.450s, P99: 0.450s

【模块耗时指标】
  fetch_performance_000042:
    平均耗时: 0.500s, 最大耗时: 0.500s
  
  ⚠️  最慢模块: llm_generation

总耗时: 32.000s
```

## 测试

运行测试验证监控功能：

```bash
pytest tests/test_metrics.py -v
```

## 相关文件

- `backend/pkg/metrics.py` - 监控指标收集器
- `backend/pkg/llm_monitor.py` - LLM 调用监控包装器
- `backend/agents/skills/product_compare/runtime.py` - API 调用监控
- `backend/agents/fund_agent/runtime.py` - LLM 调用监控
- `backend/orchestrator/run.py` - 模块耗时监控
- `tests/test_metrics.py` - 监控功能测试

## 更新日期

2026-04-10
