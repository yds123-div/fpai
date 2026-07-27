# Kiro Steering Files

这个目录包含了从 Cursor 配置转换而来的 Kiro steering files，用于指导 AI 助手的行为。

## 文件说明

### 自动包含的规则（Always Included）

这些文件会在所有对话中自动加载：

- **coding-standards.md** - 编码规范与代码质量标准
- **execution-discipline.md** - 编码执行纪律（思考、简化、外科修改、目标驱动）
- **architecture.md** - 架构规则与设计约束
- **project-context.md** - 项目上下文（技术栈、目录结构、命令）
- **workflow.md** - AI 软件开发流程

### 文件匹配规则（File Match）

这些文件只在编辑特定文件时触发：

- **python-backend.md** - Python 后端开发规范（匹配 `backend/**/*.py`）
- **vue-frontend.md** - Vue3 前端开发规范（匹配 `frontend/**/*.{vue,js,ts}`）

### 手动引入规则（Manual）

这些文件需要时手动引入（使用 # 引用）：

- **review-standards.md** - 代码与设计评审标准
- **decisions.md** - 架构决策记录（ADRs）

## 与 Cursor 的对应关系

| Cursor 文件 | Kiro Steering File | 说明 |
|-------------|-------------------|------|
| `.cursor/rules/coding-standards.mdc` | `coding-standards.md` | 编码规范 |
| `.cursor/rules/execution-discipline.mdc` | `execution-discipline.md` | 编码执行纪律 |
| `.cursor/rules/architecture.mdc` | `architecture.md` | 架构规则 |
| `.cursor/rules/workflow.mdc` | `workflow.md` | 开发流程 |
| `.cursor/rules/plan.mdc` | `workflow.md` | 规划原则（合并到 workflow） |
| `.cursor/rules/review.mdc` | `review-standards.md` | 评审标准 |
| `.cursor/memory/project_context.md` | `project-context.md` | 项目上下文 |
| `.cursor/memory/decisions.md` | `decisions.md` | 架构决策 |
| - | `python-backend.md` | Python 特定规范（新增） |
| - | `vue-frontend.md` | Vue 特定规范（新增） |

## 使用建议

### 1. 控制上下文长度

- 一个聊天窗口专注一个模块
- 模块很大时继续拆小
- 一个模块做完，新开聊天窗口
- 新模块不要接着旧窗口聊

### 2. 精准指定范围

使用 #File 或 #Folder 精准指定范围，避免全局搜索：

```
❌ "帮我改供应商注册"（太模糊）
✅ "帮我改供应商注册 #backend/services/supplier.py"（精准）
```

### 3. 任务拆分

复杂功能一定要拆分任务：

```
✅ "这个功能分成 3 个任务，先只完成第 1 个"
```

### 4. 利用 Steering 的动态特性

- **Always included** 的规则会一直生效
- **File match** 的规则只在编辑对应文件时生效（更精准）
- **Manual** 的规则需要时再引入（避免上下文过长）

### 5. 持续优化

发现 AI 经常犯同一种错误时：

- 如果是长期规范 → 写进对应的 steering file
- 如果是特定场景 → 在对话中纠正，让 AI 记住

## 下一步

1. ✅ 已完成：转换 Cursor rules/memory 为 Kiro steering files
2. ✅ 已完成：创建 6 个角色 steering files（backend-engineer、frontend-engineer 等）
3. ✅ 已完成：创建 6 个 Specs（implement-feature、review-code 等）
4. ✅ 已完成：创建 5 个实用 Hooks（代码检查、测试等）
5. ✅ 已完成：完整的开发规范体系

## 新增内容

### 角色 Steering Files（.kiro/steering/roles/）
- `backend-engineer.md` - 高级后端工程师角色
- `frontend-engineer.md` - 高级前端工程师角色
- `product-manager.md` - 高级产品经理角色
- `system-architect.md` - 高级系统架构师角色
- `test-engineer.md` - 测试工程师角色
- `qa-reviewer.md` - QA 评审专家角色

### Specs（.kiro/specs/）
- `generate-prd` - 生成产品需求文档
- `design-architecture` - 设计系统架构
- `implement-feature` - 实现功能
- `review-code` - 代码评审
- `run-tests` - 运行测试
- `debug-issue` - 调试问题

### Hooks（自动化工作流）
- `task-start-reminder` - 任务开始前提醒查看文档
- `write-safety-check` - 写入操作前安全检查
- `python-code-check` - Python 代码规范自动检查
- `vue-component-check` - Vue 组件规范自动检查
- `task-complete-test` - 任务完成后自动运行测试

## 参考

- Kiro Steering 文档：查看 Kiro 帮助文档了解更多 steering 功能
- Cursor 经验：参考原始 Cursor 配置了解设计意图
