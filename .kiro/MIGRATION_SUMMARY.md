# Cursor 到 Kiro 迁移总结

## 已完成的工作

### ✅ Steering Files 转换完成

已将 Cursor 的 rules 和 memory 文件转换为 Kiro steering files：

| 类型 | 文件名 | 包含模式 | 说明 |
|------|--------|----------|------|
| 核心规范 | `coding-standards.md` | auto | 编码规范与代码质量标准 |
| 核心规范 | `architecture.md` | auto | 架构规则与设计约束 |
| 核心规范 | `project-context.md` | auto | 项目上下文（技术栈、目录、命令） |
| 核心规范 | `workflow.md` | auto | AI 软件开发流程与规划原则 |
| 语言特定 | `python-backend.md` | fileMatch: `backend/**/*.py` | Python 后端开发规范 |
| 语言特定 | `vue-frontend.md` | fileMatch: `frontend/**/*.{vue,js,ts}` | Vue3 前端开发规范 |
| 按需引用 | `review-standards.md` | manual | 代码与设计评审标准 |
| 按需引用 | `decisions.md` | manual | 架构决策记录（ADRs） |

### 转换策略

1. **Always Included（auto）**：核心规范，每次对话都生效
   - 编码规范、架构规则、项目上下文、工作流程

2. **File Match（fileMatch）**：语言/框架特定规范，只在编辑对应文件时生效
   - Python 后端规范（编辑 .py 文件时）
   - Vue 前端规范（编辑 .vue/.js/.ts 文件时）
   - 这样可以避免上下文过长，更精准

3. **Manual（manual）**：按需引用，需要时用 # 手动引入
   - 评审标准（做代码审查时引入）
   - 架构决策记录（需要查看历史决策时引入）

## 与 Cursor 的主要区别

### 优势

1. **更智能的上下文管理**
   - Cursor：所有 rules 一股脑加载
   - Kiro：根据文件类型自动选择相关规范

2. **更灵活的规则组织**
   - 可以按语言、框架、场景分别定义规则
   - 避免 Python 规范干扰 Vue 开发，反之亦然

3. **更好的可维护性**
   - 规则分类清晰
   - 易于扩展和更新

### 使用建议

#### 1. 精准指定范围（最重要！）

```
❌ 不好："帮我优化基金推荐功能"
✅ 好："帮我优化基金推荐功能 #backend/agents/fund_agent/product_recommend/agent.py"
```

#### 2. 控制对话范围

- 一个聊天窗口 = 一个模块
- 模块完成后，新开窗口
- 避免上下文混乱

#### 3. 任务拆分

```
复杂功能这样问：
"这个功能分成 3 个任务：
1. 先实现数据访问层
2. 再实现业务逻辑
3. 最后实现 API 接口
我们先完成第 1 个"
```

#### 4. 利用 File Match 特性

当你编辑 Python 文件时，`python-backend.md` 会自动生效：
- AgentScope 集成规范
- 类型提示要求
- 错误处理规范

当你编辑 Vue 文件时，`vue-frontend.md` 会自动生效：
- Composition API 规范
- SSE 流式处理
- API 调用规范

#### 5. 手动引入决策记录

需要查看架构决策时：
```
"参考 #decisions.md，我们为什么选择 Milvus 而不是 ES？"
```

## 下一步建议

### 1. 创建 Hooks（自动化工作流）

可以创建以下 Hooks：

```json
{
  "name": "Python 代码保存时检查",
  "when": {
    "type": "fileEdited",
    "patterns": ["backend/**/*.py"]
  },
  "then": {
    "type": "askAgent",
    "prompt": "检查这段代码是否符合规范：类型提示、docstring、错误处理"
  }
}
```

### 2. 持续优化 Steering Files

发现 AI 经常犯的错误：
- 添加到对应的 steering file
- 例如："方法参数不超过 3 个"

### 3. 团队协作

- 团队成员可以共享这些 steering files
- 保证代码风格一致
- 新人快速上手

## 验证转换效果

你可以测试以下场景：

### 测试 1：编辑 Python 文件
```
打开任意 backend/**/*.py 文件
问："这个文件的代码规范有什么问题？"
应该会引用 python-backend.md 的规范
```

### 测试 2：编辑 Vue 文件
```
打开任意 frontend/**/*.vue 文件
问："这个组件的写法符合规范吗？"
应该会引用 vue-frontend.md 的规范
```

### 测试 3：架构决策
```
问："为什么我们选择 Milvus 而不是 ES？"
手动引入 #decisions.md
应该会引用 Decision 001
```

## 文件清单

```
.kiro/steering/
├── README.md                    # 使用说明
├── coding-standards.md          # ✅ 编码规范（auto）
├── architecture.md              # ✅ 架构规则（auto）
├── project-context.md           # ✅ 项目上下文（auto）
├── workflow.md                  # ✅ 开发流程（auto）
├── python-backend.md            # ✅ Python 规范（fileMatch）
├── vue-frontend.md              # ✅ Vue 规范（fileMatch）
├── review-standards.md          # ✅ 评审标准（manual）
└── decisions.md                 # ✅ 架构决策（manual）
```

## 总结

转换已完成！现在你可以：

1. ✅ 享受更智能的上下文管理
2. ✅ 根据文件类型自动应用相关规范
3. ✅ 按需引用架构决策和评审标准
4. ✅ 保持与 Cursor 相同的开发规范

记住核心原则：
- **精准指定范围**（用 #File）
- **一个窗口一个模块**
- **复杂任务要拆分**
- **持续优化规则**

祝开发愉快！🚀
