---
description: Python 后端开发规范
inclusion: fileMatch
fileMatchPattern: 'backend/**/*.py'
---

# Python 后端开发规范

## 代码风格

- 使用 snake_case 命名变量和函数
- 使用 PascalCase 命名类
- 使用类型提示（Type Hints）
- 方法必须有 docstring
- 异常处理要具体，不要使用 bare except

## 项目结构

遵循以下目录结构：

```
backend/
├── api/                    # HTTP/SSE/WS 入口
├── orchestrator/           # 意图识别、任务编排
├── agents/                 # 各能力智能体
├── retrieval/              # 检索服务
├── data_access/            # 业务数据访问层
├── compliance/             # 合规服务
├── audit/                  # 审计与证据
├── feedback/               # 反馈闭环
├── ingestion/              # 文档接入与解析
├── model_gateway/          # 模型网关
├── config/                 # 配置管理
└── pkg/                    # 公共模块
```

## 依赖方向

- `api` → `orchestrator` → `agents`、`retrieval`、`data_access`、`compliance`、`audit`
- `agents` 依赖 `retrieval`、`data_access`、`model_gateway`
- 禁止反向依赖与循环依赖

## AgentScope 集成

- 智能体内需调用大模型时，统一通过 **AgentScope 的 ReActAgent（ReAgent）** 模式
- 实例化 `ReActAgent`，`model` 由 `model_gateway.config` 选用
- 无工具时使用空 `Toolkit()`
- 通过 `agent(Msg(...))` 获取回复
- 不在智能体内部直接调用 `model_gateway.llm_chat`

## 错误处理

- 使用统一错误码（见 `backend/pkg/codes.py`）
- 日志带 `traceId`、`answerId`、`userId`
- 敏感字段脱敏

## 测试

- 关键路径必须有单元测试或集成测试
- 使用 pytest 框架
- 测试文件命名：`test_*.py`
