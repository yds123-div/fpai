# 性能分析与优化建议

## 请求耗时分析（000042的信息）

### 总耗时：61.077s

| 阶段 | 耗时 | 占比 | 优化优先级 |
|------|------|------|-----------|
| 任务规划 | 13.526s | 22% | 中 |
| 输入合规检查 | 0.003s | 0% | - |
| **Agent 执行** | **47.465s** | **78%** | **高** |
| 输出合规检查 | 0.020s | 0% | - |
| 审计落库 | 0.061s | 0% | - |

## Agent 执行详细分析（47.465s）

### 1. 数据获取阶段：~20s

```
11:28:41.042 - 开始第1个请求（danjuanfunds.com）
11:28:41.419 - 完成第1个请求（0.377s）
11:28:41.430 - 开始第2个请求
[19秒超时/重试]
11:29:00.524 - 开始第3个请求
11:29:01.695 - 完成所有数据获取（总计~20s）
```

**问题**：
- 6个 API 调用串行执行
- 其中一个请求超时（19秒）
- 没有并行优化

### 2. LLM 生成阶段：~27s

```
11:29:01.720 - 开始 LLM 调用
11:29:07.786 - 收到响应头（6s）
11:29:28.350 - 流式输出完成（21s）
```

**问题**：
- LLM 响应时间长
- 流式输出耗时21秒

## 优化建议

### 高优先级优化

#### 1. 并行化数据获取（预计节省 15-18s）

**当前实现**（串行）：
```python
# 串行调用，总耗时 = 所有请求耗时之和
data1 = await fetch_api1()  # 2s
data2 = await fetch_api2()  # 19s (超时)
data3 = await fetch_api3()  # 1s
# 总计：22s
```

**优化后**（并行）：
```python
# 并行调用，总耗时 = 最慢请求的耗时
results = await asyncio.gather(
    fetch_api1(),  # 2s
    fetch_api2(),  # 19s (超时)
    fetch_api3(),  # 1s
)
# 总计：19s（节省3s）
```

**实施位置**：
- `backend/agents/fund_agent/product_interpret/agent.py`
- `backend/agents/skills/product_interpret/runtime.py`

#### 2. 添加 API 超时和重试策略（预计节省 10-15s）

**问题**：某个 API 请求超时19秒

**优化方案**：
```python
import httpx

async def fetch_with_timeout(url, timeout=5.0):
    """带超时的 API 调用"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.json()
    except httpx.TimeoutException:
        logger.warning(f"API timeout: {url}")
        return None  # 返回默认值或跳过
```

**配置建议**：
- 单个 API 超时：3-5秒
- 总超时：15秒
- 失败后降级：使用缓存或跳过非关键数据

#### 3. 数据缓存（预计节省 5-10s）

**实施方案**：
```python
from functools import lru_cache
import time

@lru_cache(maxsize=1000)
def get_fund_data_cached(fund_code: str, cache_key: str):
    """缓存基金数据（5分钟有效期）"""
    return fetch_fund_data(fund_code)

# 或使用 Redis
async def get_fund_data_redis(fund_code: str):
    cache_key = f"fund:{fund_code}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    data = await fetch_fund_data(fund_code)
    await redis.setex(cache_key, 300, json.dumps(data))  # 5分钟
    return data
```

### 中优先级优化

#### 4. 优化任务规划（预计节省 3-5s）

**当前耗时**：13.526s

**优化方案**：
- 使用更快的模型（如 MiniMax-M2.5-highspeed 已经是最快的）
- 减少 prompt 长度
- 缓存常见问题的规划结果

```python
# 简单问题直接分类，跳过 LLM
def quick_classify(question: str) -> str | None:
    """快速分类，避免 LLM 调用"""
    if re.match(r'^\d{6}的信息$', question):
        return 'product_interpret'
    if re.match(r'^\d{6}和\d{6}(的)?对比$', question):
        return 'product_compare'
    return None  # 需要 LLM 规划
```

#### 5. 流式输出优化

**当前问题**：LLM 流式输出21秒

**优化方案**：
- 已经使用流式输出（✓）
- 考虑使用更快的模型
- 减少生成内容长度（通过 prompt 控制）

### 低优先级优化

#### 6. 数据库查询优化

**审计落库**：0.061s（可接受）

**优化方案**：
- 异步落库（不阻塞响应）
- 批量插入

#### 7. 合规检查优化

**当前耗时**：0.023s（可接受）

## 优化效果预估

| 优化项 | 预计节省时间 | 实施难度 | 优先级 |
|--------|-------------|---------|--------|
| 并行化数据获取 | 15-18s | 中 | 高 |
| API 超时策略 | 10-15s | 低 | 高 |
| 数据缓存 | 5-10s | 中 | 高 |
| 优化任务规划 | 3-5s | 中 | 中 |
| 流式输出优化 | 2-5s | 高 | 低 |

**总计预期节省**：35-53s

**优化后预期总耗时**：8-26s（从61s降低）

## 实施计划

### Phase 1：快速优化（1-2天）

1. ✅ 添加进度提示中文映射
2. 添加 API 超时配置（3-5秒）
3. 并行化数据获取

### Phase 2：中期优化（3-5天）

1. 实现 Redis 缓存
2. 优化任务规划逻辑
3. 添加降级策略

### Phase 3：长期优化（1-2周）

1. 性能监控和告警
2. 自动化性能测试
3. 持续优化 LLM prompt

## 监控指标

### 关键指标

```python
# 在 orchestrator.run 中添加
logger.info(f"[PERF] 数据获取耗时: {data_fetch_time}s")
logger.info(f"[PERF] LLM 调用耗时: {llm_time}s")
logger.info(f"[PERF] 并行度: {parallel_count}")
```

### 告警阈值

- 单次请求总耗时 > 30s：警告
- 单次请求总耗时 > 60s：严重
- API 超时率 > 10%：警告
- 缓存命中率 < 50%：警告

## 相关文件

- `backend/agents/fund_agent/product_interpret/agent.py` - 产品解析 Agent
- `backend/agents/skills/product_interpret/runtime.py` - 数据获取逻辑
- `backend/orchestrator/run.py` - 编排器
- `docs/parallel_optimization.md` - 并行优化文档

## 更新日期

2026-04-10
