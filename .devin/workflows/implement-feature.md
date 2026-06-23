---
description: 按任务和规范实现功能
---

# 实现功能

**输入：**
- 要实现的功能描述或任务（可从 `.cursor/memory/tasks.md` 取）
- 约束：`.cursor/memory/technical_design.md`、编码规范

**输出：**
- 可运行、符合规范的代码
- 相关单元/集成测试
- 必要文档或注释

**步骤：**
1. 读取 `.cursor/memory/` 中 prd、architecture、technical_design、tasks；若有 `project_context.md` 则优先按其中技术栈与目录实现
2. 按功能类型选择实现方式（后端 API / 前端页面 / 数据模型等）
3. 遵循编码规范实现：
   - Clean Architecture 分层
   - SOLID 原则
   - 命名见名知意
   - 关键路径有测试
   - 错误处理明确
4. 编写测试，更新 `tasks.md` 中该任务状态
