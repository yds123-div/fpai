---
inclusion: auto
---

# 中文输出规则

## 语言要求

- 所有输出内容必须使用中文
- 代码注释使用中文
- 文档和说明使用中文
- 错误提示使用中文
- 日志信息使用中文

## 例外情况

以下情况可以使用英文：
- 代码中的变量名、函数名、类名（遵循编程规范）
- 技术术语的英文缩写（如 API、HTTP、JSON 等）
- 第三方库的名称和方法名
- Git commit 信息（如果项目规范要求）
- 配置文件中的键名

## 示例

✅ 正确：
```python
def 获取基金数据(symbol: str) -> dict:
    """获取基金的基本信息。
    
    Args:
        symbol: 基金代码
        
    Returns:
        包含基金信息的字典
    """
    logger.info(f"开始获取基金 {symbol} 的数据")
    return {"代码": symbol, "名称": "华夏成长"}
```

❌ 错误：
```python
def get_fund_data(symbol: str) -> dict:
    """Get fund basic information."""
    logger.info(f"Fetching data for fund {symbol}")
    return {"code": symbol, "name": "Huaxia Growth"}
```

## 适用范围

- 与用户的所有对话
- 生成的文档和注释
- 错误提示和日志
- 代码审查意见
- 设计文档和需求文档
