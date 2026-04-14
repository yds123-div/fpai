# 日志优化说明

## 优化目标

解决日志输出过多、不易阅读的问题：
1. 减少第三方库的 DEBUG 日志噪音
2. 简化性能监控日志输出
3. 使用 emoji 和简短格式提升可读性
4. 支持通过环境变量灵活控制日志级别

## 优化内容

### 1. 抑制第三方库日志

**问题**：httpcore、urllib3、openai 等库输出大量 DEBUG 日志

**解决方案**：
- 在 `config/logging_config.py` 中新增 `suppress_third_party_logs()` 函数
- 默认将第三方库日志级别提升到 WARNING
- 可通过环境变量 `THIRD_PARTY_LOG_LEVEL` 控制

```python
# .env
THIRD_PARTY_LOG_LEVEL=WARNING  # 可选：DEBUG, INFO, WARNING, ERROR
```

### 2. 抑制已知警告

**问题**：JWT 密钥长度警告、AgentScope 未知参数警告

**解决方案**：
- 在 `config/warnings_filter.py` 中新增 `suppress_known_warnings()` 函数
- 自动过滤已知的第三方库警告
- JWT 密钥已更新为 32+ 字符（生产环境必须）

**被抑制的警告**：
- `InsecureKeyLengthWarning`: JWT 密钥长度警告
- `Unknown keyword arguments: ['enable_thinking']`: AgentScope 参数警告

### 2. 简化性能监控日志

**问题**：每个请求输出 10+ 行 PERF 日志，信息冗余

**解决方案**：

#### 紧凑模式（默认）
只输出关键信息，一行显示：
```
🚀 [bf444b76] 请求开始: 000032和000037的对比
📋 [bf444b76] 任务规划完成: 1个任务 (13.42s)
🤖 [bf444b76] Agent执行完成 (42.34s)
✅ [bf444b76] 请求完成 总耗时 55.86s
📊 🤖 LLM: 2次调用, 679tokens | ⏱️  最慢: agent.ProductCompareAgent (42.34s)
```

#### 详细模式（可选）
输出完整的性能指标（原有格式）：
```
================================================================================
性能监控摘要
================================================================================

【API 调用指标】
  fund_individual_achievement_xq:
    调用次数: 2 (成功: 2, 超时: 0, 错误: 0)
    超时率: 0.00%
    平均耗时: 0.611s, P95: 0.612s, P99: 0.612s
...
```

**控制方式**：
```python
# .env
PERF_LOG_MODE=compact  # 或 verbose
```

### 3. 优化日志格式

**变化对比**：

| 原格式 | 新格式 | 说明 |
|--------|--------|------|
| `[PERF][bf444b76-dcdd-42f1-9aa6-d3be615a7d3c] API /chat 请求到达 \| stream=True` | `📨 [bf444b76] /chat 请求 stream=True` | 使用 emoji，缩短 trace_id |
| `[PERF][bf444b76...] 任务规划完成 \| 耗时=13.418s \| 累计=13.419s \| tasks=1` | `📋 [bf444b76] 任务规划完成: 1个任务 (13.42s)` | 去掉累计时间，更简洁 |
| `[PERF][bf444b76...] Agent 执行完成 \| 耗时=42.335s \| 累计=55.796s \| reply_len=6318` | `🤖 [bf444b76] Agent执行完成 (42.34s)` | 只保留关键耗时 |

**Emoji 图例**：
- 🚀 请求开始
- 📋 任务规划
- 🤖 Agent 执行
- 🔍 合规检查
- 📝 审计落库
- ✅ 请求完成
- 📊 性能摘要
- ⚠️  性能瓶颈/警告
- ⏱️  耗时提醒

### 4. 智能日志过滤

**原则**：只记录重要或异常的步骤

- **初始化**：超过 1 秒才记录
- **合规检查**：超过 0.5 秒才记录
- **审计落库**：超过 0.5 秒才记录
- **性能瓶颈**：总耗时超过 10 秒才警告

**示例**：
```python
# 只在耗时较长时记录
if t_now - t_last > 1.0:
    logger.info(f"⏱️  [{tid[:8]}] 初始化耗时 {t_now - t_last:.2f}s")
```

### 5. 降低内部日志级别

**原则**：内部初始化、调试信息使用 DEBUG 级别

**优化的日志**：
- `AkShareClient initialized` → DEBUG
- `ProductCompareAgent initialized` → DEBUG
- `ProductInterpretAgent initialized` → DEBUG
- `Falling back to original skill logic` → DEBUG
- `seed builtin agents failed` → DEBUG
- `通过 AgentScope 模型调用` → DEBUG（详细的请求/响应）

**效果**：在 INFO 级别下，这些内部日志不再显示

### 开发环境（详细日志）

```bash
# .env
LOG_LEVEL=DEBUG
THIRD_PARTY_LOG_LEVEL=INFO
PERF_LOG_MODE=verbose
```

### 生产环境（简洁日志）

```bash
# .env
LOG_LEVEL=INFO
THIRD_PARTY_LOG_LEVEL=WARNING
PERF_LOG_MODE=compact
```

### 调试特定问题

```bash
# 只看第三方库日志
THIRD_PARTY_LOG_LEVEL=DEBUG

# 只看性能详情
PERF_LOG_MODE=verbose

# 只看 AkShare 日志
AKSHARE_LOG_LEVEL=DEBUG
```

## 效果对比

### 优化前（一个请求约 50+ 行日志）

```
2026-04-13 14:32:15,960 [INFO] api.routes.chat trace_id=bf444b76-dcdd-42f1-9aa6-d3be615a7d3c [PERF][unknown] API /chat 请求到达 | stream=True
2026-04-13 14:32:15,961 [INFO] api.routes.chat trace_id=bf444b76-dcdd-42f1-9aa6-d3be615a7d3c [PERF][unknown] 开始并行初始化 | 耗时=0.000s
2026-04-13 14:32:20,059 [INFO] api.routes.chat trace_id=bf444b76-dcdd-42f1-9aa6-d3be615a7d3c [PERF][unknown] 并行初始化完成 | 累计=4.099s
...（省略 40+ 行）
2026-04-13 14:33:28,284 [INFO] pkg.metrics trace_id=bf444b76-dcdd-42f1-9aa6-d3be615a7d3c ================================================================================
...（省略详细性能指标）
```

### 优化后（一个请求约 5-10 行日志）

```
2026-04-13 14:40:50 [INFO] 📨 [unknown] /chat 请求 stream=True
2026-04-13 14:41:07 [INFO] 🚀 [259f8882] 请求开始: 000029和000037对比
2026-04-13 14:41:15 [INFO] 📋 [259f8882] 任务规划完成: 1个任务 (8.89s)
2026-04-13 14:42:01 [INFO] 🤖 [259f8882] Agent执行完成 (45.29s)
2026-04-13 14:42:01 [INFO] ✅ [259f8882] 请求完成 总耗时 54.29s
2026-04-13 14:42:01 [INFO] 📊 ⚠️  API异常: fund_portfolio_hold_em: 1错误 0超时 | ⏱️  最慢: agent.ProductCompareAgent (45.29s)
```

**减少约 90% 的日志行数，同时保留关键信息！**

**注意**：
- 不再显示 JWT 密钥长度警告
- 不再显示 AgentScope 未知参数警告
- 不再显示内部初始化日志
- 不再显示第三方库 DEBUG 日志

## 注意事项

1. **向后兼容**：所有日志功能保持兼容，只是默认输出更简洁
2. **灵活控制**：可随时通过环境变量切换详细/简洁模式
3. **关键信息不丢失**：错误、警告、性能瓶颈仍会完整记录
4. **trace_id 保留**：虽然显示时缩短，但完整 trace_id 仍在日志中

## 相关文件

- `backend/config/logging_config.py` - 日志配置（新增 suppress_third_party_logs）
- `backend/config/warnings_filter.py` - 警告过滤（新增）
- `backend/pkg/metrics.py` - 性能监控（新增紧凑模式）
- `backend/orchestrator/run.py` - 编排器日志优化
- `backend/api/routes/chat.py` - API 路由日志优化
- `backend/model_gateway/llm.py` - 模型网关日志优化
- `backend/agents/agent_store.py` - Agent 存储日志优化
- `backend/agents/fund_agent/product_compare/agent.py` - 对比 Agent 日志优化
- `backend/agents/fund_agent/product_interpret/agent.py` - 解读 Agent 日志优化
- `backend/pkg/akshare_client.py` - AkShare 客户端日志优化
- `backend/.env` - 环境变量配置（更新 JWT_SECRET）
- `backend/.env.example` - 环境变量示例
