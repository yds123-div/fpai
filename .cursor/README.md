# Cursor AI 软件工程操作系统 · 使用指南

本目录是项目的 **AI 研发协作配置**，用于实现**需求到上线的完整软件项目开发**：需求 → PRD → 架构 → 设计 → 任务拆解 → 编码 → 测试 → 部署。

---

## 一、目录结构说明

```
.cursor
├── skills/          # AI 角色（按阶段选用，@ 引用）
├── rules/           # AI 行为规则（自动或按条件生效）
├── commands/        # 操作指令（按步骤执行的提示模板）
├── memory/          # 项目长期记忆（PRD、架构、设计、任务、决策、项目上下文）
└── README.md        # 本说明
```

| 目录       | 作用 |
|------------|------|
| **skills** | 不同阶段的“AI 角色”，对话时 @ 引用即可按该角色输出 |
| **rules**  | 工作流、编码规范、架构约束等，Cursor 会据此约束回答 |
| **commands** | 可复用的操作步骤（生成 PRD/架构/设计/任务、实现、测试、部署、调试），按文档执行 |
| **memory** | 项目上下文与产出物，AI 读取以保持与现有 PRD/架构/设计一致 |

---

## 二、如何调用：`/` 与 `@`

在 Cursor 对话框中用以下方式触发命令或引用 Skills，无需每次手打长路径。

### 用 `/` 调用命令（Commands）

- 在输入框输入 **`/`**，会列出本项目 `.cursor/commands/` 下的可用命令。
- 选择对应命令（如 `generate-prd`、`review-code`）后，会带入该命令的说明，AI 将按该命令的步骤执行。
- **示例**：输入 `/generate-prd` 后补一句「需求是：做一个 xxx 系统」，即可按「生成 PRD」流程执行并写入 `.cursor/memory/prd.md`。
- 常用命令对应文件名：`generate-prd`、`generate-architecture`、`generate-design`、`generate-tasks`、`implement-feature`、`run-tests`、`deploy`、`debug`、`review-code`。

### 用 `@` 引用文件或 Skill

- 在输入框输入 **`@`**，可搜索并引用项目中的文件。
- **引用 Command**：输入 `@` 后选 `.cursor/commands/xxx.md`，等同于让 AI 按该命令执行（适合命令未出现在 `/` 列表时）。
- **引用 Skill**：输入 `@` 后选 `.cursor/skills/product/xxx.md`、`architecture/xxx.md`、`engineering/xxx.md` 等，AI 会以该角色与输出格式回答。
- **示例**：`@.cursor/skills/engineering/backend-engineer.md 实现用户登录接口` → AI 以后端工程师角色、按规范实现登录接口。
- **引用 Memory**：`@.cursor/memory/prd.md` 或 `@.cursor/memory/architecture.md`，让 AI 先读取再回答，保持与现有 PRD/架构一致。

### 组合使用

- 先 `@.cursor/memory/prd.md` 再输入「按 generate-architecture 生成架构」→ 带上下文生成架构。
- 输入 `/review-code` 并 @ 待评审的文件 → 按评审标准做代码评审。

---

## 三、完整流程（从零到上线）

按顺序执行以下步骤，即可完成整体软件项目开发：

| 步骤 | 说明 | 使用的 Command | 产出写入 Memory |
|------|------|----------------|-----------------|
| 1 | 需求输入 | 用户提供业务需求、用户故事 | - |
| 2 | PRD 生成 | `.cursor/commands/generate-prd.md` | `.cursor/memory/prd.md` |
| 3 | 系统架构 | `.cursor/commands/generate-architecture.md` | `.cursor/memory/architecture.md` |
| 4 | 技术设计 | `.cursor/commands/generate-design.md` | `.cursor/memory/technical_design.md`、`.cursor/memory/decisions.md` |
| 5 | 项目上下文 | 手动或让 AI 协助填写 | `.cursor/memory/project_context.md` |
| 6 | 任务拆解 | `.cursor/commands/generate-tasks.md` | `.cursor/memory/tasks.md` |
| 7 | 编码实现 | `.cursor/commands/implement-feature.md` | 代码库 + 更新 `.cursor/memory/tasks.md` 状态 |
| 8 | 测试 | `.cursor/commands/run-tests.md` | 测试结果 / 补充用例 |
| 9 | 部署 | `.cursor/commands/deploy.md` | 部署步骤或 CI/CD 配置 |

**话术示例：**

- 步骤 2：「按 `.cursor/commands/generate-prd.md` 生成 PRD，需求是：……」
- 步骤 3：「根据 `.cursor/memory/prd.md`，按 `.cursor/commands/generate-architecture.md` 生成架构」
- 步骤 4：「根据 `.cursor/memory/architecture.md`，按 `.cursor/commands/generate-design.md` 做 API 与数据设计」
- 步骤 5：「根据 `.cursor/memory/architecture.md` 和 `.cursor/memory/technical_design.md`，帮我填写 `.cursor/memory/project_context.md`（技术栈、目录、命令）」
- 步骤 6：「根据 `.cursor/memory/` 里的 prd、architecture、technical_design，按 `.cursor/commands/generate-tasks.md` 拆解任务」
- 步骤 7：「按 `.cursor/memory/tasks.md` 和 `.cursor/commands/implement-feature.md` 实现任务 T001」（可 @ 对应 engineering skill）
- 步骤 8：「按 `.cursor/commands/run-tests.md` 跑测试」
- 步骤 9：「按 `.cursor/commands/deploy.md` 准备部署到 xx 环境」

---

## 四、Commands 一览

| 命令文件 | 用途 |
|----------|------|
| `generate-prd.md` | 根据业务需求生成 PRD → `.cursor/memory/prd.md` |
| `generate-architecture.md` | 根据 PRD 生成系统/技术架构 → `.cursor/memory/architecture.md` |
| `generate-design.md` | 根据 PRD+架构 做 API/数据/模块设计 → `.cursor/memory/technical_design.md`、`.cursor/memory/decisions.md` |
| `generate-tasks.md` | 根据 PRD+架构+设计 拆解可执行任务 → `.cursor/memory/tasks.md` |
| `implement-feature.md` | 按 `.cursor/memory/` 与规范实现指定任务（含测试、更新 tasks 状态） |
| `run-tests.md` | 执行测试、修复失败、补充用例 |
| `deploy.md` | 部署/发布或产出部署方案（含回滚建议） |
| `debug.md` | 问题根因分析、修复与防复现建议 |
| `review-code.md` | 按评审标准做代码/设计评审（需求、架构、质量、测试、安全） |

---

## 五、Skills 速查（何时用谁）

| 阶段       | 可用的 Skill |
|------------|--------------|
| 需求/PRD   | `skills/product/prd-generator.md`、`product-manager.md`、`business-analyst.md` |
| 任务拆解   | `skills/product/task-planner.md` |
| 架构       | `skills/architecture/system-architect.md`、`tech-architect.md`、`microservice-architect.md`、`ai-system-architect.md` |
| 设计       | `skills/design/api-designer.md`、`database-designer.md`、`data-model-designer.md`、`module-designer.md` |
| 开发       | `skills/engineering/backend-engineer.md`、`frontend-engineer.md`、`ai-engineer.md`、`integration-engineer.md`、`refactor-engineer.md` |
| 质量       | `skills/quality/test-engineer.md`、`qa-reviewer.md`、`security-reviewer.md` |
| 运维       | `skills/devops/devops-engineer.md`、`ci-cd-engineer.md`、`sre-engineer.md` |

**用法**：在输入框用 `@` 引用对应文件，例如：  
`@.cursor/skills/engineering/backend-engineer.md 实现用户登录接口`

---

## 六、Rules 说明

- **rules.mdc**：必须始终遵守的通用指令（例如分多次回复、给出改进建议）。
- **workflow.mdc**：完整 9 步流程及与 `.cursor/memory/`、`.cursor/commands/` 的对应关系。
- **coding-standards.mdc**：编码原则与质量要求（Clean Architecture、SOLID、命名、测试等）。
- **architecture.mdc**：架构约束、产出物位置、与 project_context 的关系。
- **architecture-understanding.mdc**：架构理解与校验规则（从 `.cursor/memory/architecture.md` 解析 Mermaid、提取边界/依赖/数据流；用于改动前对照架构约束自检）。  
- **plan.mdc**：规划/架构类任务的工作方式（先读 `.cursor/memory/`，再输出可执行 plan，并回写到 `.cursor/memory/`）。
- **review.mdc**：评审标准（需求对齐、架构、代码、测试、安全）。

Rules 可能是自动生效（`alwaysApply: true`），也可能是按需启用（`alwaysApply: false`）。需要「按评审标准检查」时，可用 `/review-code` 或显式引用 `@.cursor/rules/review.mdc`；需要强制按架构理解/校验流程时，可显式引用 `@.cursor/rules/architecture-understanding.mdc`。

---

## 七、Memory 维护建议

| 文件 | 维护时机 |
|------|----------|
| **prd.md** | 生成 PRD 或大需求变更时更新 |
| **architecture.md** | 生成架构或架构演进时更新 |
| **technical_design.md** | 生成设计或设计变更时更新 |
| **decisions.md** | 重要技术选型与决策时追加（标题 + 原因 + 日期） |
| **project_context.md** | 技术栈与目录确定后填写；实现、测试、部署时优先参照 |
| **tasks.md** | 任务拆解时生成；每完成一项将状态改为 `done` |

对话中可说：「先读取 `.cursor/memory` 下的 prd、architecture、technical_design、project_context、tasks 再回答」。

---

## 八、阶段检查清单（完成整体项目时自检）

- [ ] **需求与 PRD**：prd.md 已生成，包含用户故事与功能/非功能需求
- [ ] **架构与设计**：architecture.md、technical_design.md、decisions.md 已就绪，重要决策有记录
- [ ] **项目上下文**：project_context.md 已填写技术栈、目录、命令，与架构一致
- [ ] **任务列表**：tasks.md 已拆解为可执行任务，有优先级与依赖，无模糊项
- [ ] **实现**：按 tasks 逐项实现，代码符合 coding-standards，关键路径有测试
- [ ] **测试**：run-tests 通过，无遗留不该 skip 的用例
- [ ] **部署**：deploy 步骤或 CI/CD 已就绪，环境与密钥通过配置管理

---

## 九、一句话小结

- **生成 PRD** → 引用 `.cursor/commands/generate-prd.md` + 需求。
- **生成架构** → 读 `.cursor/memory/prd.md`，再引用 `.cursor/commands/generate-architecture.md`。
- **生成设计** → 读 `.cursor/memory/architecture.md`，再引用 `.cursor/commands/generate-design.md`。
- **填写项目上下文** → 完善 `.cursor/memory/project_context.md`（技术栈、目录、命令）。
- **拆解任务** → 引用 `.cursor/commands/generate-tasks.md`，产出写入 `.cursor/memory/tasks.md`。
- **实现功能** → 引用 `.cursor/commands/implement-feature.md` 或对应 `skills/engineering/xxx`，并让 AI 读 `.cursor/memory/`。
- **测试** → 引用 `.cursor/commands/run-tests.md`。
- **部署** → 引用 `.cursor/commands/deploy.md`。
- **调试** → 引用 `.cursor/commands/debug.md`。
- **代码评审** → `/review-code` 或引用 `.cursor/commands/review-code.md`。

按上述流程与命令使用，即可在本指导下完成从需求到上线的整体软件项目开发。
