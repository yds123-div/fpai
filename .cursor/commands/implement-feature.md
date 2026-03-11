# 实现功能

按需使用 **backend-engineer** / **frontend-engineer** / **ai-engineer** 等 engineering skill。

**输入：**
- 要实现的功能描述或任务（可从 `.cursor/memory/tasks.md` 取）
- 约束：`.cursor/memory/technical_design.md`、`.cursor/rules/coding-standards.mdc`

**输出：**
- 可运行、符合规范的代码
- 相关单元/集成测试
- 必要文档或注释

**步骤：**
1. 读取 `.cursor/memory/` 中 prd、architecture、technical_design、tasks；若有 `project_context.md` 则优先按其中技术栈与目录实现
2. 按功能类型选择对应 engineering skill（如 backend-engineer、frontend-engineer）
3. 遵循 `.cursor/rules/coding-standards.mdc` 实现
4. 编写测试，更新 `tasks.md` 中该任务状态（如需要）
