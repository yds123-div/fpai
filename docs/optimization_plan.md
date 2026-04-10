# 性能优化方案（完整版）

## 当前性能问题总结

从 `000042的信息` 请求分析（总耗时 61.077s）：

```
├── 任务规划：13.526s (22%)
│   └── LLM 调用：13.4s
├── Agent 执行：47.465s (78%) ⚠️
│   ├── 数据获取：20s（其中19s是超时）
│   └── LLM 生成：27s
└── 其他：<0.1s
```

---

## 🔥 Phase 1：立即优化（1-2天，节省 30-40s）

### 1. 添加 API 超时配置（节省 15-18s）

**问题**：akshare 调用超时19秒

**方案**：使用 `asyncio.wait_for` 添加超时

```python
# backend/agents/skills/product_compare/runtime.py

async def _fetch_with_timeout(coro, timeout=5.0, default=None):
    """带超时的异步调用"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"操作超时（{timeout}s）")
        return default
    except Exception as e:
        logger.warning(f"操作失败: {e}")
        return default

async def _fetch_basic_info(sym: str) -> dict[str, Any]:
    """获取基本信息（带超时）"""
    fn_basic_xq = _fn("fund_individual_basic_info_xq")
    if not callable(fn_basic_xq):
        return _module_fail("akshare 未提供 fund_individual_basic_info_xq")
    
    try:
        # 添加5秒超时
        df = await _fetch_with_timeout(
            asyncio.to_thread(fn_basic_xq, symbol=sym),
            timeout=5.0,
            default=None
        )
        if df is None:
            return _module_fail("获取基本信息超时")
        return _module_ok(_df_records(df, limit=200))
    except Exception as e:
        return _module_fail(f"fund_individual_basic_info_xq 失败: {e}")
```

**配置建议**：
- 单个 API 超时：3-5秒
- 整体数据获取超时：15秒
- 失败后降级：返回 `{"ok": false}`

### 2. 优化并行执行（节省 5-10s）

**问题**：虽然代码写了并行，但 akshare 是同步库，可能阻塞

**方案**：确保真正并行 + 添加进度反馈

```python
async def _fetch_single_fund(sym: str, ctx: AgentRunContext) -> dict[str, Any]:
    """并行获取单只基金的所有数据"""
    fund_obj: dict[str, Any] = {"symbol": sym}
    
    # 发送进度
    await _emit_progress(ctx, "data_fetching", message=f"正在获取 {sym} 数据...")
    
    # 并行获取三个模块（每个模块内部也并行）
    basic_info, performance, asset_allocation = await asyncio.gather(
        _fetch_basic_info(sym),
        _fetch_performance(sym),
        _fetch_asset_allocation(sym),
        return_exceptions=True,
    )
    
    # ... 处理结果
```

### 3. 添加数据缓存（节省 5-10s）

**方案**：使用 Redis 或内存缓存

```python
# backend/pkg/cache.py
from functools import lru_cache
import hashlib
import json

# 简单内存缓存（5分钟）
@lru_cache(maxsize=1000)
def _cache_key(func_name: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_data = f"{func_name}:{args}:{sorted(kwargs.items())}"
    return hashlib.md5(key_data.encode()).hexdigest()

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300  # 5分钟

async def cached_fetch(func_name: str, fetch_func, *args, **kwargs):
    """带缓存的数据获取"""
    import time
    
    cache_key = _cache_key(func_name, *args, **kwargs)
    
    # 检查缓存
    if cache_key in _CACHE:
        timestamp, data = _CACHE[cache_key]
        if time.time() - timestamp < _CACHE_TTL:
            logger.debug(f"缓存命中: {func_name}")
            return data
    
    # 获取数据
    data = await fetch_func(*args, **kwargs)
    
    # 存入缓存
    _CACHE[cache_key] = (time.time(), data)
    
    return data

# 使用示例
async def _fetch_basic_info(sym: str) -> dict[str, Any]:
    return await cached_fetch(
        "fund_basic_info",
        _do_fetch_basic_info,
        sym
    )
```

**Redis 版本**（推荐生产环境）：

```python
# backend/pkg/redis_cache.py
import redis.asyncio as redis
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

async def cached_fetch_redis(key: str, fetch_func, ttl=300):
    """Redis 缓存"""
    # 检查缓存
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    
    # 获取数据
    data = await fetch_func()
    
    # 存入缓存
    await redis_client.setex(key, ttl, json.dumps(data, ensure_ascii=False))
    
    return data
```

---

## ⚡ Phase 2：中期优化（3-5天，节省 5-10s）

### 4. 优化任务规划（节省 3-5s）

**方案 A**：快速分类，跳过 LLM

```python
# backend/agents/fund_agent_framework.py

def quick_classify(question: str) -> str | None:
    """快速分类简单问题，避免 LLM 调用"""
    q = question.strip()
    
    # 单只基金信息
    if re.match(r'^\d{6}(的)?(信息|详情|介绍|分析)$', q):
        return 'product_interpret'
    
    # 两只基金对比
    if re.match(r'^\d{6}和\d{6}(的)?(对比|比较)$', q):
        return 'product_compare'
    
    # 基金查询
    if re.search(r'(推荐|查询|有哪些|排行|榜单)', q):
        return 'product_query'
    
    return None  # 需要 LLM 规划

async def plan(self, question: str, ctx: AgentRunContext) -> dict[str, Any]:
    # 快速分类
    quick_type = quick_classify(question)
    if quick_type:
        codes = _extract_codes_from_text(question)
        return {
            "multi": False,
            "tasks": [{"type": quick_type, "question": question}],
            "final_instruction": "",
            "quick_classified": True,
        }
    
    # 复杂问题才调用 LLM
    # ...
```

**方案 B**：精简 Prompt

```python
# 当前 System Prompt: ~800 tokens
# 优化后: ~400 tokens

COORDINATOR_SYSTEM_PROMPT_LITE = """
你是任务规划助手，输出 JSON：

可用类型：
- product_compare: 基金对比（2+代码）
- product_interpret: 单只解读（1个代码）
- product_query: 榜单/推荐
- other: 其它

输出格式：
{"multi": false, "tasks": [{"type": "...", "question": "..."}], "final_instruction": "..."}

规则：
- 多任务时 multi=true
- 基金名称转为6位代码
""".strip()
```

### 5. 精简 LLM 生成内容（节省 2-5s）

**方案**：优化 System Prompt，减少输出长度

```python
# backend/agents/fund_agent/product_interpret/agent.py

# 当前输出要求：~1800字
# 优化为：~1200字

DEFAULT_SYSTEM_PROMPT_LITE = """
你是基金分析专家。根据数据输出分析报告（不超过1200字）。

## 输出格式
【基本信息】（80字）
【业绩表现】（100字）
【资产配置】（100字）
【分析结论】（150字）
【风险提示】（固定模板）

## 规则
- 仅陈述客观信息
- 不使用 markdown
- 日期格式：YYYY年MM月DD日
""".strip()
```

---

## 🚀 Phase 3：长期优化（1-2周）

### 6. 数据预加载

**方案**：热门基金数据预加载到缓存

```python
# backend/tasks/preload.py
import asyncio

POPULAR_FUNDS = ["000001", "000008", "000031", "000039", "000042", "000047"]

async def preload_popular_funds():
    """预加载热门基金数据"""
    for code in POPULAR_FUNDS:
        try:
            await fetch_fund_data(code)
            logger.info(f"预加载成功: {code}")
        except Exception as e:
            logger.warning(f"预加载失败 {code}: {e}")

# 在应用启动时调用
# backend/main.py
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(preload_popular_funds())
```

### 7. 使用更快的数据源

**方案**：替换或补充 akshare

```python
# 选项 A：直接调用 API（更快）
async def fetch_fund_data_direct(code: str):
    """直接调用蛋卷 API"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"https://danjuanfunds.com/djapi/fund/{code}"
        )
        return response.json()

# 选项 B：使用数据库
async def fetch_fund_data_db(code: str):
    """从数据库获取（需要定时同步）"""
    async with get_db_connection() as conn:
        result = await conn.fetchone(
            "SELECT * FROM fund_data WHERE code = ? AND updated_at > datetime('now', '-1 hour')",
            (code,)
        )
        return result
```

### 8. 流式优化

**方案**：边获取数据边生成

```python
async def run_streaming(question: str, ctx: AgentRunContext) -> str:
    """流式处理：边获取数据边生成"""
    
    # 1. 快速返回基本信息
    basic_data = await fetch_basic_info_fast(code)
    await stream_partial_response(ctx, format_basic_info(basic_data))
    
    # 2. 并行获取其他数据
    other_data = await fetch_other_data(code)
    await stream_partial_response(ctx, format_other_info(other_data))
    
    # 3. 生成结论
    conclusion = await generate_conclusion(basic_data, other_data)
    await stream_partial_response(ctx, conclusion)
```

---

## 📊 优化效果预估

| 优化项 | 预计节省 | 实施难度 | 优先级 | 实施时间 |
|--------|---------|---------|--------|---------|
| API 超时配置 | 15-18s | 低 | 🔥 高 | 0.5天 |
| 数据缓存 | 5-10s | 中 | 🔥 高 | 1天 |
| 优化并行执行 | 5-10s | 中 | 🔥 高 | 1天 |
| 快速分类 | 3-5s | 低 | ⚡ 中 | 0.5天 |
| 精简 Prompt | 2-5s | 低 | ⚡ 中 | 0.5天 |
| 数据预加载 | 5-10s | 中 | 🚀 低 | 2天 |
| 更快数据源 | 10-15s | 高 | 🚀 低 | 5天 |
| 流式优化 | 5-10s | 高 | 🚀 低 | 3天 |

**总计预期节省**：50-83s

**优化后预期总耗时**：8-11s（从61s降低）

---

## 🛠️ 实施步骤

### Week 1：快速优化

**Day 1-2**：
1. ✅ 添加进度提示中文映射（已完成）
2. 添加 API 超时配置
3. 实现内存缓存

**Day 3-4**：
1. 优化并行执行
2. 添加快速分类
3. 精简 Prompt

**Day 5**：
1. 测试和验证
2. 性能监控

### Week 2：中期优化

**Day 1-3**：
1. 实现 Redis 缓存
2. 数据预加载
3. 优化数据获取逻辑

**Day 4-5**：
1. 性能测试
2. 调优和修复

### Week 3+：长期优化

1. 评估更快的数据源
2. 实现流式优化
3. 持续监控和调优

---

## 📈 监控指标

### 关键指标

```python
# 在各阶段添加详细监控
logger.info(f"[PERF] 任务规划 - 快速分类: {quick_classified}")
logger.info(f"[PERF] 任务规划 - LLM耗时: {llm_time}s")
logger.info(f"[PERF] 数据获取 - 缓存命中: {cache_hit}")
logger.info(f"[PERF] 数据获取 - API耗时: {api_time}s")
logger.info(f"[PERF] 数据获取 - 超时次数: {timeout_count}")
logger.info(f"[PERF] LLM生成 - 输入tokens: {input_tokens}")
logger.info(f"[PERF] LLM生成 - 输出tokens: {output_tokens}")
logger.info(f"[PERF] LLM生成 - 耗时: {generation_time}s")
```

### 告警阈值

- 任务规划 > 10s：警告
- 数据获取 > 8s：警告
- 单个 API > 5s：警告
- API 超时率 > 10%：严重
- 缓存命中率 < 50%：警告
- LLM 生成 > 25s：警告
- 总耗时 > 30s：警告
- 总耗时 > 60s：严重

---

## 🧪 测试计划

### 性能测试

```python
# tests/test_performance.py
import pytest
import time

@pytest.mark.asyncio
async def test_chat_performance():
    """测试聊天性能"""
    start = time.time()
    
    result = await run_chat_turn_async(
        "000042的信息",
        session_id="test",
        user_id="test",
    )
    
    elapsed = time.time() - start
    
    # 断言总耗时 < 30s
    assert elapsed < 30, f"耗时过长: {elapsed}s"
    
    # 断言有结果
    assert result.answer_blocks
    assert len(result.answer_blocks[0]) > 100

@pytest.mark.asyncio
async def test_cache_hit():
    """测试缓存命中"""
    # 第一次调用
    start1 = time.time()
    await fetch_fund_data("000042")
    time1 = time.time() - start1
    
    # 第二次调用（应该命中缓存）
    start2 = time.time()
    await fetch_fund_data("000042")
    time2 = time.time() - start2
    
    # 缓存命中应该快很多
    assert time2 < time1 * 0.1, "缓存未生效"
```

### 压力测试

```bash
# 使用 locust 进行压力测试
locust -f tests/locustfile.py --host=http://localhost:8000
```

---

## 📝 相关文件

- `backend/agents/skills/product_compare/runtime.py` - 数据获取
- `backend/agents/fund_agent_framework.py` - 任务规划
- `backend/agents/fund_agent/product_interpret/agent.py` - 产品解析
- `backend/orchestrator/run.py` - 编排器
- `backend/pkg/cache.py` - 缓存工具（新增）
- `tests/test_performance.py` - 性能测试（新增）

## 更新日期

2026-04-10
