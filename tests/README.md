# 测试目录

本目录包含所有测试文件，包括单元测试、集成测试、性能测试和功能验证脚本。

## 目录结构

```
tests/
├── conftest.py                      # pytest 配置和 fixtures
├── test_*.py                        # 单元测试和集成测试
├── test_perf_*.py                   # 性能测试
└── README.md                        # 本文件
```

## 测试分类

### 单元测试和集成测试

使用 pytest 框架，文件命名为 `test_*.py`：

- `test_api_envelope.py` - API 响应封装测试
- `test_chat_api.py` - 对话 API 测试
- `test_compliance.py` - 合规检查测试
- `test_model_gateway.py` - 模型网关测试
- `test_retrieval_service.py` - 检索服务测试
- 等等...

**运行方式**：
```bash
# 运行所有测试
pytest tests/

# 运行单个测试文件
pytest tests/test_chat_api.py

# 运行特定测试函数
pytest tests/test_chat_api.py::test_chat_endpoint

# 显示详细输出
pytest tests/ -v

# 显示打印输出
pytest tests/ -s
```

### 性能测试

性能测试脚本，文件命名为 `test_perf_*.py`：

- `test_perf_monitoring.py` - 性能监控测试，验证各阶段耗时

**运行方式**：
```bash
# 直接运行
python tests/test_perf_monitoring.py

# 或使用 pytest
pytest tests/test_perf_monitoring.py -s
```

### 功能验证脚本

功能验证和手动测试脚本：

- `test_streaming.py` - 流式输出测试，验证 SSE 事件和 token 级流式
- `test_akshare.py` - AKShare 数据源测试

**运行方式**：
```bash
# 设置环境变量
export API_TOKEN='your_token_here'

# 运行测试
python tests/test_streaming.py
```

## 编写测试规范

### 1. 文件命名

- 单元测试/集成测试：`test_<module_name>.py`
- 性能测试：`test_perf_<feature>.py`
- 功能验证：`test_<feature>.py`

### 2. 测试函数命名

- 使用 `test_` 前缀
- 描述性命名：`test_chat_endpoint_returns_valid_response`

### 3. 测试结构

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块测试

测试 XXX 模块的功能
"""
import pytest


def test_feature_basic():
    """测试基本功能"""
    # Arrange
    input_data = "test"
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result == expected_output


def test_feature_edge_case():
    """测试边界情况"""
    with pytest.raises(ValueError):
        function_under_test(invalid_input)
```

### 4. 功能验证脚本结构

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能验证脚本

用法：
    python tests/test_feature.py

说明：
    验证某个功能的具体行为
"""
import os
import sys


def main():
    """主函数"""
    print("=" * 80)
    print("🚀 功能测试")
    print("=" * 80)
    
    # 测试逻辑
    try:
        # 执行测试
        print("✅ 测试通过")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## 测试覆盖率

查看测试覆盖率：

```bash
# 安装 pytest-cov
pip install pytest-cov

# 运行测试并生成覆盖率报告
pytest tests/ --cov=backend --cov-report=html

# 查看报告
open htmlcov/index.html
```

## 持续集成

测试应该在 CI/CD 流程中自动运行：

```yaml
# .github/workflows/test.yml 示例
- name: Run tests
  run: |
    pytest tests/ -v --cov=backend
```

## 注意事项

1. **不要在 scripts/ 目录放置测试脚本** - 所有测试统一放在 tests/
2. **使用 fixtures** - 在 conftest.py 中定义可复用的 fixtures
3. **模拟外部依赖** - 使用 mock 避免依赖外部服务
4. **清理测试数据** - 测试后清理创建的数据
5. **独立性** - 每个测试应该独立运行，不依赖其他测试的状态

## 相关文档

- [pytest 文档](https://docs.pytest.org/)
- [编码规范](.kiro/steering/coding-standards.md)
- [项目上下文](.kiro/steering/project-context.md)
