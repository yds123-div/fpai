# 执行流程详细分析

## 完整请求流程（000042的信息）

### 总览

```
总耗时：61.077s
├── 任务规划：13.526s (22%)
├── 输入合规检查：0.003s (0%)
├── Agent 执行：47.465s (78%) ⚠️
├── 输出合规检查：0.020s (0%)
└── 审计落库：0.061s (0%)
```

---

## 1. 任务规划（13.526s）

### 流程

```python
# backend/orchestrator/run.py
plan = await fund_router.coordinator.plan(message, ctx_obj)
```

### 详细步骤

#### 1.1 调用 CoordinatorAgent（13.5s）

**位置**：`backend/agents/fund_agent_framework.py` - `CoordinatorAgent.plan()`

```python
async def plan(self, question: str, ctx: AgentRunContext) -> dict[str, Any]:
    # 1. 短路检查（闲聊等）- 0.001s
    if _is_chitchat(question):
        return {"multi": False, "tasks": [{"type": "other", "question": q}]}
    
    # 2. 获取 skill 数据（fund_name_to_code）- 0.1s
    planner_skill_payload = await run_configured_skills(
        skill_keys=["fund_name_to_code"],
        question=q,
        ctx=planner_ctx,
    )
    
    # 3. 调用 LLM 规划任务 - 13.4s ⚠️ 最耗时
    from model_gateway.llm import llm_chat
    raw = await asyncio.to_thread(
        llm_chat,
        [
            {"role": "system", "content": COORDINATOR_DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        model="MiniMax-M2.5-highspeed",
    )
    
    # 4. 解析 JSON 结果 - 0.001s
    json_text = _extract_json_object(raw_text)
    plan = _parse_plan_output(json_text)
    
    # 5. 代码映射和验证 - 0.024s
    # 将基金名称转换为代码，验证代码有效性
```

### 耗时分解

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 短路检查 | 0.001s | 快速判断闲聊 |
| Skill 数据获取 | 0.1s | fund_name_to_code |
| **LLM 调用** | **13.4s** | **MiniMax API 调用** |
| JSON 解析 | 0.001s | 提取和验证 |
| 代码映射 | 0.024s | 基金代码处理 |

### LLM 调用详情

```
11:28:27.520 - 发送请求到 MiniMax API
11:28:40.880 - 收到响应（13.36s）
```

**Prompt 长度**：
- System: ~800 tokens
- User: ~100 tokens
- 总计: ~900 tokens

**响应**：
- Output tokens: 166
- Reasoning tokens: 94（思考过程）

---

## 2. Agent 执行（47.465s）

### 流程

```python
# backend/orchestrator/run.py
if len(tasks) == 1:
    agent = fund_router.route("product_interpret")
    reply_text = await agent.run(question, ctx_obj)
```

### 详细步骤

#### 2.1 ProductInterpretAgent.run()（47.5s）

**位置**：`backend/agents/fund_agent/product_interpret/agent.py`

```python
async def run(self, question: str, ctx: AgentRunContext) -> str:
    # 1. 解析基金代码 - 0.001s
    m = re.search(r"\b\d{6}\b", question)
    fund_code = m.group(0)  # "000042"
    
    # 2. 获取基金数据（Skill）- 20s ⚠️
    supplier_data = await run_configured_skills(
        skill_keys=["product_compare"],  # 复用对比 skill
        question=fund_code,
        ctx=ctx,
    )
    
    # 3. 构建 Prompt - 0.001s
    user_prompt = f"""
    当日日期：{today}
    用户问题：{question}
    基金供应商数据：{json.dumps(supplier_data)}
    """
    
    # 4. 调用 LLM 生成分析 - 27s ⚠️
    return await _llm_call_maybe_stream(
        ctx=ctx,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
```

### 耗时分解

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 代码解析 | 0.001s | 正则提取 |
| **数据获取（Skill）** | **20s** | **6个 API 调用** |
| Prompt 构建 | 0.001s | 字符串拼接 |
| **LLM 生成** | **27s** | **流式输出** |

---

## 3. 数据获取详细分析（20s）

### Skill 调用链

```python
# backend/agents/fund_agent/runtime.py
supplier_data = await run_configured_skills(
    skill_keys=["product_compare"],
    question="000042",
    ctx=ctx,
)
```

### product_compare Skill 实现

**位置**：`backend/agents/skills/product_compare/runtime.py`

```python
async def product_compare_skill(question: str, ctx: dict) -> str:
    codes = _extract_codes(question)  # ["000042"]
    
    # 并行获取多只基金数据
    tasks = [_fetch_single_fund(code) for code in codes]
    results = await asyncio.gather(*tasks)
    
    return json.dumps(results)

async def _fetch_single_fund(code: str) -> dict:
    # 串行调用 6 个 API ⚠️ 问题所在
    data = {}
    
    # 1. 基本信息 - 0.377s
    data["basic"] = await fetch_danjuan_basic(code)
    
    # 2. 业绩数据 - 19s ⚠️ 超时
    data["achievement"] = await fetch_danjuan_achievement(code)
    
    # 3. 风格分析 - 0.243s
    data["analysis"] = await fetch_danjuan_analysis(code)
    
    # 4. 盈亏比 - 0.231s
    data["profit_ratio"] = await fetch_danjuan_profit(code)
    
    # 5. 资产配置 - 0.222s
    data["asset"] = await fetch_danjuan_asset(code)
    
    # 6. 详细信息 - 0.297s
    data["detail"] = await fetch_danjuan_detail(code)
    
    return data
```

### API 调用时间线（从日志）

```
11:28:41.042 - 开始第1个 API（基本信息）
11:28:41.419 - 完成（0.377s）

11:28:41.430 - 开始第2个 API（业绩数据）
[19秒超时/重试]
11:29:00.524 - 超时，开始第3个 API

11:29:00.762 - 完成第3个 API（0.238s）
11:29:00.989 - 完成第4个 API（0.227s）
11:29:01.392 - 完成第5个 API（0.403s）
11:29:01.695 - 完成第6个 API（0.303s）

总计：~20s（其中19s是超时）
```

### 问题分析

1. **串行执行**：6个 API 依次调用，无法并行
2. **超时处理不当**：某个 API 超时19秒才失败
3. **无降级策略**：超时后仍等待，没有跳过或使用缓存

---

## 4. LLM 生成详细分析（27s）

### 流程

```python
# backend/agents/fund_agent/runtime.py
async def _llm_call_maybe_stream(ctx, messages):
    # 1. 构建请求 - 0.001s
    # 2. 发送到 MiniMax API - 6s
    # 3. 流式接收响应 - 21s
    # 4. 返回完整文本 - 0.001s
```

### 时间线

```
11:29:01.720 - 发送 LLM 请求
11:29:07.786 - 收到响应头（6s）
11:29:28.350 - 流式输出完成（21s）
```

### Prompt 分析

**System Prompt**：~3000 tokens
- 包含详细的分析规则
- 输出格式要求
- 风险提示模板

**User Prompt**：~2000 tokens
- 当日日期
- 用户问题
- 基金数据（JSON，约1500 tokens）

**总输入**：~5000 tokens

**输出**：~1800 tokens（约1815字）

---

## 优化建议总结

### 高优先级（预计节省 35-40s）

#### 1. 并行化数据获取（节省 15-18s）

**当前**：串行调用 6 个 API
```python
data1 = await api1()  # 0.4s
data2 = await api2()  # 19s
data3 = await api3()  # 0.2s
# 总计：19.6s
```

**优化后**：并行调用
```python
results = await asyncio.gather(
    api1(),  # 0.4s
    api2(),  # 19s
    api3(),  # 0.2s
)
# 总计：19s（节省0.6s，但如果修复超时可节省更多）
```

#### 2. API 超时策略（节省 15-18s）

**当前**：默认超时或无超时
```python
async def fetch_api(url):
    response = await httpx.get(url)  # 可能超时19s
```

**优化后**：设置合理超时
```python
async def fetch_api(url, timeout=3.0):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.json()
    except httpx.TimeoutException:
        logger.warning(f"API timeout: {url}")
        return None  # 降级处理
```

#### 3. 数据缓存（节省 5-10s）

```python
@lru_cache(maxsize=1000)
async def get_fund_data_cached(fund_code: str):
    # 缓存5分钟
    return await fetch_fund_data(fund_code)
```

### 中优先级（预计节省 5-8s）

#### 4. 优化任务规划（节省 3-5s）

**快速分类**：简单问题跳过 LLM
```python
def quick_classify(question: str) -> str | None:
    if re.match(r'^\d{6}的信息$', question):
        return 'product_interpret'
    if re.match(r'^\d{6}和\d{6}(的)?对比$', question):
        return 'product_compare'
    return None  # 需要 LLM
```

#### 5. 精简 Prompt（节省 2-3s）

- 减少 System Prompt 长度（3000 → 2000 tokens）
- 优化输出格式要求
- 移除冗余说明

---

## 性能监控建议

### 关键指标

```python
# 在各阶段添加详细监控
logger.info(f"[PERF] 任务规划 - LLM调用: {llm_time}s")
logger.info(f"[PERF] 数据获取 - API1: {api1_time}s")
logger.info(f"[PERF] 数据获取 - API2: {api2_time}s")
logger.info(f"[PERF] LLM生成 - 输入tokens: {input_tokens}")
logger.info(f"[PERF] LLM生成 - 输出tokens: {output_tokens}")
logger.info(f"[PERF] LLM生成 - 耗时: {generation_time}s")
```

### 告警阈值

- 任务规划 > 15s：警告
- 数据获取 > 10s：警告
- 单个 API > 5s：警告
- LLM 生成 > 30s：警告
- 总耗时 > 60s：严重

---

## 相关文件

- `backend/orchestrator/run.py` - 主编排流程
- `backend/agents/fund_agent_framework.py` - 任务规划
- `backend/agents/fund_agent/product_interpret/agent.py` - 产品解析 Agent
- `backend/agents/skills/product_compare/runtime.py` - 数据获取 Skill
- `backend/agents/fund_agent/runtime.py` - Agent 运行时

## 更新日期

2026-04-10
