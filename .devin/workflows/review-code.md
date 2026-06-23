---
description: 按评审标准做代码/设计评审
---

# 代码评审

**输入：**
- 待评审的代码或改动（可指定文件、目录，或粘贴 diff/说明）
- 可选：本次改动对应的任务（如 memory/tasks.md 中的 Txxx）或需求范围

**输出：**
- 按评审维度给出结论：**通过** 或 **不通过**
- 通过：简要确认符合需求、架构、规范与测试要求
- 不通过：列出问题项（文件/行号或位置）、严重程度、修改建议

**步骤：**
1. 按评审维度执行：
   - **需求对齐**：实现是否覆盖 PRD/User Story
   - **架构一致**：是否违反 architecture.md、technical_design.md、decisions.md
   - **代码质量**：符合编码规范（Clean Architecture、SOLID、命名、错误处理）
   - **测试**：关键逻辑有测试，无不该有的依赖或 mock
   - **安全与运维**：无敏感信息泄露，错误与日志可观测
2. 若有 memory：对照 prd.md、architecture.md、technical_design.md、decisions.md 检查一致性
3. 汇总结论与问题列表，给出明确通过/不通过及后续建议

**建议使用场景：** 提交前自检、PR 前评审、或完成某任务后做一次小范围评审。
