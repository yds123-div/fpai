# AkShareClient 使用指南

## 概述

`AkShareClient` 是一个封装了 AkShare API 的客户端，提供了 6 个核心方法来获取基金数据。

## 核心特性

- **重试机制**：失败时自动重试 3 次，使用指数退避策略
- **限流控制**：请求间隔 0.5 秒，避免被限流
- **参数验证**：自动验证基金代码格式（6 位数字）
- **统一返回格式**：`{"ok": bool, "data": [...], "message": str}`
- **异步 API**：使用 asyncio 提升性能

## 安装依赖

```bash
pip install akshare>=1.18.54
```

## 快速开始

### 1. 初始化客户端

```python
from pkg.akshare_client import AkShareClient

# 使用默认配置
client = AkShareClient()

# 自定义配置
client = AkShareClient(
    max_retries=5,          # 最大重试次数
    retry_delay=2.0,        # 初始重试延迟（秒）
    request_interval=1.0,   # 请求间隔（秒）
)
```

### 2. 获取基金基本信息

```python
result = await client.get_basic_info("000001")

if result["ok"]:
    for item in result["data"]:
        print(f"{item['item']}: {item['value']}")
else:
    print(f"获取失败: {result['message']}")
```

**返回数据示例**：
```python
[
    {"item": "基金代码", "value": "000001"},
    {"item": "基金名称", "value": "华夏成长"},
    {"item": "基金类型", "value": "混合型"},
    {"item": "基金规模", "value": "100.5亿"},
    {"item": "基金经理", "value": "张三"},
]
```

### 3. 获取业绩表现数据

```python
result = await client.get_achievement("000001")

if result["ok"]:
    for record in result["data"]:
        print(f"{record['时间段']}: {record['收益率']}")
```

**返回数据示例**：
```python
[
    {"时间段": "近1月", "收益率": "5.2%", "同类排名": "10/100"},
    {"时间段": "近3月", "收益率": "12.5%", "同类排名": "8/100"},
    {"时间段": "近1年", "收益率": "35.8%", "同类排名": "5/100"},
]
```

### 4. 获取风险指标数据

```python
result = await client.get_analysis("000001")

if result["ok"]:
    for record in result["data"]:
        print(f"{record['指标']}: {record['值']}")
```

**返回数据示例**：
```python
[
    {"指标": "波动率", "值": "15.2%"},
    {"指标": "夏普比率", "值": "1.8"},
    {"指标": "最大回撤", "值": "-12.5%"},
]
```

### 5. 获取资产配置数据

```python
result = await client.get_detail_hold("000001")

if result["ok"]:
    for record in result["data"]:
        print(f"{record['资产类型']}: {record['仓位占比']}%")
```

**返回数据示例**：
```python
[
    {"资产类型": "股票", "仓位占比": 65.5},
    {"资产类型": "债券", "仓位占比": 25.3},
    {"资产类型": "现金", "仓位占比": 9.2},
]
```

### 6. 获取费率信息数据

```python
result = await client.get_detail_info("000001")

if result["ok"]:
    for record in result["data"]:
        print(f"{record['费用类型']}: {record['费率']}")
```

**返回数据示例**：
```python
[
    {"费用类型": "管理费率", "费率": "1.5%"},
    {"费用类型": "托管费率", "费率": "0.25%"},
    {"费用类型": "申购费率", "费率": "1.2%"},
    {"费用类型": "赎回费率", "费率": "0.5%"},
]
```

### 7. 获取净值走势数据

```python
# 默认获取近 1 年数据
result = await client.get_nav_data("000001")

# 指定时间周期
result = await client.get_nav_data("000001", period="3年")

if result["ok"]:
    for record in result["data"]:
        print(f"{record['净值日期']}: {record['单位净值']}")
```

**支持的周期**：
- `"1月"` - 近 1 个月
- `"3月"` - 近 3 个月
- `"6月"` - 近 6 个月
- `"1年"` - 近 1 年（默认）
- `"3年"` - 近 3 年
- `"成立来"` - 自成立以来

**返回数据示例**：
```python
[
    {"净值日期": "2024-01-01", "单位净值": 1.5000, "日增长率": 0.5},
    {"净值日期": "2024-01-02", "单位净值": 1.5100, "日增长率": 0.67},
    {"净值日期": "2024-01-03", "单位净值": 1.5050, "日增长率": -0.33},
]
```

## 完整示例

### 获取单只基金的所有数据（推荐方式）

使用 `get_all_data()` 方法一次性获取所有数据，内置并发控制和异常处理：

```python
import asyncio
from pkg.akshare_client import AkShareClient

async def main():
    """获取单只基金的所有数据。"""
    client = AkShareClient()
    
    # 使用 get_all_data() 方法（推荐）
    result = await client.get_all_data("000001")
    
    if result["ok"]:
        fund_data = result["data"]
        print(f"基金代码: {fund_data['symbol']}")
        
        # 检查各个数据源
        if fund_data["basic_info"]["ok"]:
            print("✓ 基本信息获取成功")
        else:
            print(f"✗ 基本信息获取失败: {fund_data['basic_info']['message']}")
        
        if fund_data["achievement"]["ok"]:
            print("✓ 业绩数据获取成功")
        
        if fund_data["analysis"]["ok"]:
            print("✓ 风险指标获取成功")
        
        if fund_data["detail_hold"]["ok"]:
            print("✓ 资产配置获取成功")
        
        if fund_data["detail_info"]["ok"]:
            print("✓ 费率信息获取成功")
        
        if fund_data["nav_data"]["ok"]:
            print("✓ 净值数据获取成功")
    else:
        print(f"获取失败: {result['message']}")

# 运行示例
asyncio.run(main())
```

**返回数据结构**：
```python
{
    "ok": True,
    "data": {
        "symbol": "000001",
        "basic_info": {"ok": True, "data": [...]},
        "achievement": {"ok": True, "data": [...]},
        "analysis": {"ok": True, "data": [...]},
        "detail_hold": {"ok": True, "data": [...]},
        "detail_info": {"ok": True, "data": [...]},
        "nav_data": {"ok": True, "data": [...]}
    }
}
```

**特性**：
- ✅ 自动并发获取 6 个数据源
- ✅ 使用 Semaphore 限制并发数为 3（避免请求过于频繁）
- ✅ 使用 `return_exceptions=True` 确保部分失败不影响其他数据
- ✅ 自动处理异常，将异常转换为错误响应
- ✅ 记录详细日志，便于排查问题

### 手动并发获取（高级用法）

如果需要更灵活的控制，可以手动使用 `asyncio.gather()`：

```python
async def get_fund_data_manual(symbol: str):
    """手动并发获取单只基金的所有数据。"""
    client = AkShareClient()
    
    # 手动并发获取所有数据
    basic_info, achievement, analysis, detail_hold, detail_info, nav_data = await asyncio.gather(
        client.get_basic_info(symbol),
        client.get_achievement(symbol),
        client.get_analysis(symbol),
        client.get_detail_hold(symbol),
        client.get_detail_info(symbol),
        client.get_nav_data(symbol, period="1年"),
    )
    
    return {
        "symbol": symbol,
        "basic_info": basic_info,
        "achievement": achievement,
        "analysis": analysis,
        "detail_hold": detail_hold,
        "detail_info": detail_info,
        "nav_data": nav_data,
    }
```

### 获取多只基金数据

```python
async def get_multiple_funds(symbols: list[str]):
    """获取多只基金的数据。"""
    client = AkShareClient()
    
    # 使用 get_all_data() 并发获取多只基金
    tasks = [client.get_all_data(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results

# 使用示例
symbols = ["000001", "000002", "000003"]
funds_data = await get_multiple_funds(symbols)

for result in funds_data:
    if isinstance(result, Exception):
        print(f"获取失败: {result}")
    elif result["ok"]:
        fund_data = result["data"]
        print(f"基金 {fund_data['symbol']} 数据获取完成")
    else:
        print(f"获取失败: {result['message']}")
```

## 并发控制说明

`get_all_data()` 方法内置了并发控制机制：

1. **Semaphore 限制**：最多 3 个并发请求
   - 6 个数据源分两批执行：前 3 个并发，后 3 个并发
   - 避免请求过于频繁导致被限流

2. **异常隔离**：使用 `return_exceptions=True`
   - 单个数据源失败不影响其他数据源
   - 异常自动转换为错误响应 `{"ok": False, "message": "..."}`

3. **性能优化**：
   - 并发执行比串行快约 2-3 倍
   - 6 个数据源串行需要约 3-6 秒
   - 并发执行只需约 1-2 秒

**并发控制示意图**：
```
时间轴：
0s    ├─ get_basic_info()    ┐
      ├─ get_achievement()   ├─ 第一批（3 个并发）
      ├─ get_analysis()      ┘
      
0.5s  ├─ get_detail_hold()   ┐
      ├─ get_detail_info()   ├─ 第二批（3 个并发）
      ├─ get_nav_data()      ┘
      
1.0s  完成
```

## 错误处理

### 1. 参数验证错误

```python
result = await client.get_basic_info("invalid")

# 返回：
# {
#     "ok": False,
#     "message": "Invalid fund symbol: invalid. Expected 6-digit string."
# }
```

### 2. API 调用失败

```python
result = await client.get_basic_info("000001")

if not result["ok"]:
    # 所有重试都失败
    print(f"API 调用失败: {result['message']}")
    # 可以选择：
    # 1. 记录日志
    # 2. 返回默认值
    # 3. 抛出异常
```

### 3. 部分数据缺失

```python
fund_data = await get_fund_data("000001")

# 检查每个数据源
if not fund_data["achievement"]["ok"]:
    print("业绩数据不可用，使用默认值或隐藏该模块")
```

## 性能优化建议

### 1. 使用并发获取

```python
# ✓ 推荐：并发获取（快）
results = await asyncio.gather(
    client.get_basic_info("000001"),
    client.get_achievement("000001"),
    client.get_analysis("000001"),
)

# ✗ 不推荐：顺序获取（慢）
basic_info = await client.get_basic_info("000001")
achievement = await client.get_achievement("000001")
analysis = await client.get_analysis("000001")
```

### 2. 调整限流参数

```python
# 对于内部测试，可以减少请求间隔
client = AkShareClient(request_interval=0.2)

# 对于生产环境，建议使用默认值或更大的间隔
client = AkShareClient(request_interval=1.0)
```

### 3. 调整重试策略

```python
# 对于关键数据，增加重试次数
client = AkShareClient(max_retries=5, retry_delay=2.0)

# 对于非关键数据，减少重试次数
client = AkShareClient(max_retries=1, retry_delay=0.5)
```

## 日志记录

客户端会自动记录详细的日志，包括：

- 初始化参数
- 每次 API 调用的参数和结果
- 重试次数和延迟
- 错误信息

日志示例：
```
INFO: AkShareClient initialized (max_retries=3, retry_delay=1.0, request_interval=0.5)
DEBUG: Calling fund_individual_basic_info_xq (attempt 1/3)
INFO: fund_individual_basic_info_xq succeeded (attempt=1, data_size=10)
```

## 常见问题

### Q1: 为什么有时候获取数据很慢？

A: 可能的原因：
1. 网络延迟
2. AkShare 服务器响应慢
3. 触发了限流机制（请求间隔太短）
4. 正在重试（之前的请求失败）

解决方法：
- 检查网络连接
- 增加 `request_interval` 参数
- 查看日志了解具体原因

### Q2: 如何处理基金代码不存在的情况？

A: AkShare 会抛出异常，客户端会捕获并返回 `{"ok": False, "message": "..."}`。你需要在业务逻辑中检查 `ok` 字段。

### Q3: 可以缓存数据吗？

A: 可以。建议在业务层实现缓存（Redis 或内存缓存），TTL 设置为 1 小时。客户端本身不提供缓存功能。

### Q4: 支持同步调用吗？

A: 不支持。所有方法都是异步的，必须使用 `await` 调用。如果需要在同步代码中使用，可以使用 `asyncio.run()`：

```python
import asyncio

result = asyncio.run(client.get_basic_info("000001"))
```

## 相关文档

- [AkShare 官方文档](https://akshare.akfamily.xyz/)
- [设计文档](../.kiro/specs/akshare-data-integration/design.md)
- [需求文档](../.kiro/specs/akshare-data-integration/requirements.md)
- [任务列表](../.kiro/specs/akshare-data-integration/tasks.md)

## 更新记录

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2024-01-10 | 1.0 | 初始版本，实现 6 个核心方法 |
| 2024-01-11 | 1.1 | 新增 `get_all_data()` 方法，支持并发获取和并发控制 |

