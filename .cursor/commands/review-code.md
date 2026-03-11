# 代码评审

使用 **qa-reviewer** / **security-reviewer** skill，并遵循 `rules/review.mdc` 的评审标准。

**输入：**
- 待评审的代码或改动（可 @ 具体文件、目录，或粘贴 diff/说明）
- 可选：本次改动对应的任务（如 memory/tasks.md 中的 Txxx）或需求范围

**输出：**
- 按评审维度给出结论：**通过** 或 **不通过**
- 通过：简要确认符合需求、架构、规范与测试要求
- 不通过：列出问题项（文件/行号或位置）、严重程度、修改建议；必要时引用 `rules/review.mdc` 与对应 quality skill

**步骤：**
1. 读取 `.cursor/rules/review.mdc`，按「需求对齐、架构一致、代码质量、测试、安全与运维」维度执行
2. 若有 memory：对照 `memory/prd.md`、`memory/architecture.md`、`memory/technical_design.md`、`memory/decisions.md` 检查一致性
3. 需要时引用 `.cursor/skills/quality/qa-reviewer.md`（质量与测试）、`.cursor/skills/quality/security-reviewer.md`（安全）做专项检查
4. 汇总结论与问题列表，给出明确通过/不通过及后续建议

**建议使用场景：** 提交前自检、PR 前评审、或完成某任务后做一次小范围评审。
