# Kiro 快速参考

## 🎯 使用角色

```bash
# 单个角色
#backend-engineer.md 帮我实现登录 API

# 组合角色
#backend-engineer.md #test-engineer.md 实现并测试登录 API
```

**所有可用角色：**
- `#backend-engineer.md` - 后端工程师
- `#frontend-engineer.md` - 前端工程师
- `#product-manager.md` - 产品经理
- `#system-architect.md` - 系统架构师
- `#test-engineer.md` - 测试工程师
- `#qa-reviewer.md` - QA 评审专家

## 📋 使用 Specs

```bash
使用 spec: implement-feature
功能描述：[描述功能]
类型：后端/前端
```

**所有可用 Specs：**
- `generate-prd` - 生成产品需求文档
- `design-architecture` - 设计系统架构
- `implement-feature` - 实现功能
- `review-code` - 代码评审
- `run-tests` - 运行测试
- `debug-issue` - 调试问题

## 🔧 Hooks（自动触发）

| Hook | 触发时机 | 作用 |
|------|----------|------|
| `python-code-check` | 保存 .py 文件 | 检查代码规范 |
| `vue-component-check` | 保存 .vue 文件 | 检查组件规范 |
| `task-start-reminder` | 任务开始前 | 提醒查看文档 |
| `task-complete-test` | 任务完成后 | 自动运行测试 |
| `write-safety-check` | 写入文件前 | 安全检查 |

## 💡 常用组合

### 实现新功能
```
使用 spec: implement-feature
功能描述：用户登录功能
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

## 🎨 最佳实践

✅ **精准指定文件**：`#backend/api/routes/auth.py`  
✅ **组合使用角色**：`#backend-engineer.md #test-engineer.md`  
✅ **使用 Specs**：结构化流程更清晰  

❌ **避免模糊**："帮我优化登录功能"  
❌ **避免范围太大**："帮我优化整个后端"  

---

查看完整指南：`.kiro/COMPLETE_MIGRATION_GUIDE.md`
