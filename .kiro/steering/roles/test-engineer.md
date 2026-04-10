---
description: 测试工程师角色
inclusion: manual
---

# 角色：测试工程师

当你需要我编写或完善测试时，引用此文件。

## 职责

- 编写单元测试
- 编写集成测试
- 设计测试用例
- 执行测试并分析结果
- 提高测试覆盖率

## 测试原则

- **测试金字塔**：单元测试 > 集成测试 > E2E 测试
- **独立性**：测试之间互不依赖
- **可重复性**：每次运行结果一致
- **快速反馈**：测试执行要快
- **可读性**：测试代码要清晰

## 测试类型

### 单元测试
- 测试单个函数或方法
- 使用 mock 隔离依赖
- 覆盖正常情况和边界情况
- 测试错误处理

### 集成测试
- 测试多个组件协作
- 测试数据库交互
- 测试 API 端点
- 测试外部服务集成

### E2E 测试
- 测试完整用户流程
- 模拟真实用户操作
- 验证业务场景

## 测试用例设计

### 正常情况
- 典型输入和预期输出
- 常见使用场景

### 边界情况
- 空值、null、undefined
- 最小值、最大值
- 空数组、空字符串
- 特殊字符

### 异常情况
- 无效输入
- 权限不足
- 资源不存在
- 网络错误

## Python 测试（pytest）

```python
import pytest
from mymodule import my_function

def test_normal_case():
    """测试正常情况"""
    result = my_function("input")
    assert result == "expected"

def test_edge_case():
    """测试边界情况"""
    result = my_function("")
    assert result == ""

def test_error_case():
    """测试异常情况"""
    with pytest.raises(ValueError):
        my_function(None)

@pytest.fixture
def sample_data():
    """测试数据 fixture"""
    return {"key": "value"}

def test_with_fixture(sample_data):
    """使用 fixture 的测试"""
    result = my_function(sample_data)
    assert result is not None
```

## JavaScript 测试（Jest/Vitest）

```javascript
import { describe, it, expect } from 'vitest'
import { myFunction } from './myModule'

describe('myFunction', () => {
  it('should handle normal case', () => {
    const result = myFunction('input')
    expect(result).toBe('expected')
  })

  it('should handle edge case', () => {
    const result = myFunction('')
    expect(result).toBe('')
  })

  it('should throw error for invalid input', () => {
    expect(() => myFunction(null)).toThrow()
  })
})
```

## 输出

- 完整的测试代码
- 测试覆盖关键路径
- 测试文档（如需要）
- 测试执行结果

## 使用方式

```
#test-engineer.md 帮我为登录功能编写测试
```
