# 测试指南

## 测试文件组织规范

### 目录结构

```
fpai/
├── tests/                   # 所有测试文件
│   ├── conftest.py          # pytest 配置
│   ├── test_*.py            # 单元测试和集成测试
│   ├── test_perf_*.py       # 性能测试
│   └── README.md            # 测试目录说明
└── scripts/                 # 仅用于运维脚本
    ├── migrations/          # 数据库迁移
    └── run_migrations.py    # 迁移执行
```

### 规则

1. **所有测试文件必须放在 `tests/` 目录**
   - 单元测试：`tests/test_<module>.py`
   - 集成测试：`tests/test_<feature>.py`
   - 性能测试：`tests/test_perf_<feature>.py`
   - 功能验证：`tests/test_<feature>.py`

2. **`scripts/` 目录仅用于运维脚本**
   - 数据库迁移脚本
   - 部署脚本
   - 数据导入/导出脚本
   - 不要在此放置测试脚本

3. **测试脚本命名规范**
   - 使用 `test_` 前缀
   - 描述性命名
   - 使用 snake_case

## 测试类型

### 1. 单元测试（pytest）

```python
# tests/test_module.py
import pytest

def test_function():
    """测试某个函数"""
    result = my_function(input_data)
    assert result == expected_output
```

运行：
```bash
pytest tests/test_module.py
```

### 2. 集成测试（pytest）

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient

def test_api_endpoint(client):
    """测试 API 端点"""
    response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 200
```

运行：
```bash
pytest tests/test_api.py
```

### 3. 性能测试

```python
# tests/test_perf_monitoring.py
#!/usr/bin/env python3
"""性能监控测试"""

def test_performance():
    """测试性能指标"""
    print("🚀 性能测试开始...")
    # 测试逻辑
    print("✅ 性能测试完成")

if __name__ == "__main__":
    test_performance()
```

运行：
```bash
python tests/test_perf_monitoring.py
```

### 4. 功能验证脚本

```python
# tests/test_streaming.py
#!/usr/bin/env python3
"""流式输出测试"""

async def test_streaming():
    """测试流式输出"""
    print("🚀 流式测试开始...")
    # 测试逻辑
    print("✅ 流式测试完成")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_streaming())
```

运行：
```bash
export API_TOKEN='your_token'
python tests/test_streaming.py
```

## 快速参考

### 常用命令

```bash
# 运行所有测试
pytest tests/

# 运行单个测试文件
pytest tests/test_chat_api.py

# 运行性能测试
python tests/test_perf_monitoring.py

# 运行流式测试
python tests/test_streaming.py

# 显示详细输出
pytest tests/ -v -s

# 生成覆盖率报告
pytest tests/ --cov=backend --cov-report=html
```

### 测试脚本模板

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能测试脚本

用法：
    python tests/test_feature.py

说明：
    测试某个功能的具体行为
"""
import os
import sys


def main():
    """主函数"""
    print("=" * 80)
    print("🚀 功能测试")
    print("=" * 80)
    
    try:
        # 测试逻辑
        print("✅ 测试通过")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)
    
    print("=" * 80)


if __name__ == "__main__":
    main()
```

## 相关文档

- [tests/README.md](../tests/README.md) - 测试目录详细说明
- [coding-standards.md](steering/coding-standards.md) - 编码规范
- [project-context.md](steering/project-context.md) - 项目上下文
