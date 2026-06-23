---
description: 根据 PRD/架构/设计拆解可执行任务
---

# 生成任务（任务拆解）

**输入：**
- `.cursor/memory/prd.md`（产品需求）
- `.cursor/memory/architecture.md`（架构）
- `.cursor/memory/technical_design.md`（技术设计）
- 可选：迭代范围、优先级偏好

**输出：**
- 可执行任务列表，写入 `.cursor/memory/tasks.md`
- 每项任务：ID、描述、优先级、依赖、状态、备注
- 任务粒度：单次实现可在一个会话内完成

**步骤：**
1. 读取 `memory/prd.md`、`architecture.md`、`technical_design.md`
2. 按功能/模块拆解为具体开发任务（后端 API、前端页面、数据迁移、配置等）
3. 为每项任务分配 ID（T001, T002…）、优先级（P0/P1/P2）、依赖（如 T002 依赖 T001）
4. 写入 `.cursor/memory/tasks.md`，覆盖或合并到现有任务表
5. 若项目有 `memory/project_context.md`，技术栈与目录结构需与任务描述一致

**验收标准：**
- 任务列表可直接指导「按 implement-feature 实现 Txxx」
- 无模糊项（如「完成用户模块」需拆成具体接口/页面/表）
