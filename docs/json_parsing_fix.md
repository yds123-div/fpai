# JSON 解析修复文档

## 问题描述

在处理用户请求 `000010和000013的对比` 时，任务规划器（Coordinator）返回的 JSON 解析失败，导致系统回退到启发式规则。

### 错误日志

```
[WARNING] agents.fund_agent_framework trace_id=ca6e1136-44cb-4496-bd59-961c04017443 
Coordinator plan failed, fallback to heuristic: plan json parse failed
```

### 根本原因

LLM 返回的 JSON 包含语法错误：

```json
{
  "multi": false,
  "tasks": [
    {"type": "product_compare", "question": "对比基金000010和000013"}
  ],
  "final_instruction": "将两只基金的多维度指标进行对比分析，形成清晰的对比报告"}
}
```

注意 `final_instruction` 字段后有多余的 `}`，导致 JSON 格式错误。

## 解决方案

### 1. 增强 JSON 提取逻辑

在 `backend/agents/fund_agent_framework.py` 中增强了 `_extract_json_object` 函数：

- 提取 JSON 后立即尝试验证和修复
- 调用新增的 `_try_fix_json` 函数处理常见语法错误

### 2. 新增 JSON 修复函数

新增 `_try_fix_json` 函数，实现以下修复策略：

1. **验证 JSON 有效性**：先尝试直接解析
2. **修复多余的右花括号**：
   - 统计 `{` 和 `}` 的数量
   - 如果 `}` 多于 `{`，从末尾移除多余的 `}`
3. **提取第一个完整对象**：
   - 使用括号深度计数
   - 找到第一个完整的 JSON 对象（depth 回到 0）

### 3. 代码变更

```python
def _try_fix_json(json_str: str) -> str | None:
    """
    尝试修复常见的 JSON 语法错误：
    1. 验证 JSON 是否有效
    2. 如果无效，尝试修复常见问题（如多余的右花括号）
    """
    if not json_str:
        return None
    
    # 先尝试直接解析
    try:
        json.loads(json_str)
        return json_str
    except Exception:
        pass
    
    # 尝试修复：移除末尾多余的 }
    try:
        open_count = json_str.count("{")
        close_count = json_str.count("}")
        
        if close_count > open_count:
            excess = close_count - open_count
            temp = json_str
            for _ in range(excess):
                last_brace = temp.rfind("}")
                if last_brace != -1:
                    temp = temp[:last_brace] + temp[last_brace + 1:]
            
            json.loads(temp)
            return temp
    except Exception:
        pass
    
    # 尝试修复：提取第一个完整的 JSON 对象
    try:
        depth = 0
        for i, ch in enumerate(json_str):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[:i + 1]
                    json.loads(candidate)
                    return candidate
    except Exception:
        pass
    
    return None
```

## 测试验证

### 测试用例

创建了两个测试文件：

1. `tests/test_json_fix.py` - 测试 JSON 修复基础功能
2. `tests/test_coordinator_fix.py` - 测试真实场景

### 测试结果

```bash
$ python tests/test_json_fix.py
✓ test_valid_json
✓ test_json_with_extra_closing_brace
✓ test_extract_from_think_tags
✓ test_extract_from_code_block
✓ test_extract_from_code_block_with_extra_brace
✓ test_real_world_case

所有测试通过！

$ python tests/test_coordinator_fix.py
✓ 成功解析带有语法错误的 LLM 输出
✓ 成功解析正确的 LLM 输出

所有测试通过！修复生效。
```

## 影响范围

### 修复的问题

- ✅ LLM 返回多余右花括号的 JSON
- ✅ 代码块中的 JSON 语法错误
- ✅ 带 `<think>` 标签的复杂输出

### 不影响的功能

- ✅ 正常的 JSON 解析（直接通过验证）
- ✅ 启发式规则回退机制（作为最后保障）
- ✅ 其他 Agent 的正常运行

## 后续优化建议

### 1. Prompt 优化

在 Coordinator 的 system prompt 中强调：

```
输出 JSON 结构如下（不得输出除 JSON 外的任何文字，确保 JSON 语法正确）：
{
  "multi": true|false,
  "tasks": [...],
  "final_instruction": "..."
}

注意：
- 不要在 JSON 中添加多余的花括号
- 确保每个字段的值都正确闭合
```

### 2. 监控告警

添加日志监控，当 JSON 修复被触发时记录：

```python
if fixed != json_str:
    logger.warning("JSON auto-fixed: original=%s, fixed=%s", json_str[:100], fixed[:100])
```

### 3. LLM 参数调优

考虑调整 temperature 参数（当前 0.3），可能降低到 0.1 以提高输出稳定性。

## 相关文件

- `backend/agents/fund_agent_framework.py` - 核心修复逻辑
- `tests/test_json_fix.py` - 基础测试
- `tests/test_coordinator_fix.py` - 集成测试
- `docs/json_parsing_fix.md` - 本文档

## 更新日期

2026-04-10
