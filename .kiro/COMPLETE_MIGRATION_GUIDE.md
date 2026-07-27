# Cursor 到 Kiro 完整迁移指南

## ✅ 迁移完成！

恭喜！你的 Cursor 配置已经完全迁移到 Kiro，并且增强了很多功能。

---

## 📦 已迁移的内容

### 1. Steering Files（规则和上下文）

#### 核心规范（自动生效）
- `coding-standards.md` - 编码规范
- `architecture.md` - 架构规则
- `project-context.md` - 项目上下文
- `workflow.md` - 开发流程

#### 语言特定规范（文件匹配）
- `python-backend.md` - Python 后端规范（匹配 `backend/**/*.py`）
- `vue-frontend.md` - Vue 前端规范（匹配 `frontend/**/*.{vue,js,ts}`）

#### 按需引用（手动）
- `review-standards.md` - 评审标准
- `decisions.md` - 架构决策记录

### 2. 角色 Steering Files（6 个角色）

- `roles/backend-engineer.md` - 后端工程师
- `roles/frontend-engineer.md` - 前端工程师
- `roles/product-manager.md` - 产品经理
- `roles/system-architect.md` - 系统架构师
- `roles/test-engineer.md` - 测试工程师
- `roles/qa-reviewer.md` - QA 评审专家

### 3. Specs（6 个工作流）

- `generate-prd` - 生成产品需求文档
- `design-architecture` - 设计系统架构
- `implement-feature` - 实现功能
- `review-code` - 代码评审
- `run-tests` - 运行测试
- `debug-issue` - 调试问题

### 4. Hooks（5 个自动化 - Kiro 独有！）

- `task-start-reminder` - 任务开始前提醒
- `write-safety-check` - 写入操作前安全检查
- `python-code-check` - Python 代码规范检查
- `vue-component-check` - Vue 组件规范检查
- `task-complete-test` - 任务完成后运行测试

---

## 🚀 快速开始

### 使用角色

```
#backend-engineer.md 帮我实现登录 API
```

### 使用 Specs

```
使用 spec: implement-feature

功能描述：用户登录功能
类型：后端
```

### Hooks 自动触发

- 保存 Python 文件 → 自动检查代码规范
- 保存 Vue 文件 → 自动检查组件规范
- 开始任务 → 自动提醒查看文档
- 完成任务 → 自动运行测试

---

## 📖 常见场景

### 实现新功能

```
使用 spec: implement-feature

功能描述：实现用户登录功能

#backend-engineer.md #test-engineer.md
```

### 代码评审

```
使用 spec: review-code

评审范围：#backend/api/routes/auth.py

#qa-reviewer.md
```

### 调试问题

```
使用 spec: debug-issue

问题描述：登录接口返回 500 错误
相关文件：#backend/api/routes/auth.py
```

---

## 🆚 Cursor vs Kiro

| 功能 | Cursor | Kiro |
|------|--------|------|
| 规则管理 | 全部加载 | 智能匹配 ✨ |
| 角色扮演 | 需要明确调用 | 灵活引用 ✨ |
| 工作流 | 简单指令 | 结构化流程 ✨ |
| 自动化 | ❌ 无 | ✅ Hooks ✨ |
| 文件匹配 | ❌ 无 | ✅ 支持 ✨ |

---

## 🎉 你现在拥有的能力

✅ 智能上下文管理 - 编辑什么文件就应用什么规范  
✅ 灵活的角色系统 - 可以组合使用多个角色  
✅ 结构化的工作流 - 6 个 Specs 覆盖主要场景  
✅ 自动化检查 - Hooks 自动检查和测试  
✅ 完整的文档体系 - 规范、决策、上下文

---

## 💡 最佳实践

1. **精准指定范围**：使用 #File 指定具体文件
2. **组合使用角色**：`#backend-engineer.md #test-engineer.md`
3. **利用 Specs**：使用结构化流程完成复杂任务
4. **信任 Hooks**：让自动化帮你检查和测试
5. **持续优化**：根据实际使用调整配置

---

查看更多详细信息：
- `.kiro/steering/README.md` - Steering 使用说明
- `.kiro/MIGRATION_SUMMARY.md` - 迁移总结
- 各个 Spec 的 `spec.md` - 具体用法

开始享受高效的 AI 辅助开发吧！🚀
