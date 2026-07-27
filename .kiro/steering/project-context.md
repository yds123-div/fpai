---
description: 项目上下文（技术栈、目录结构、命令）
inclusion: auto
---

# 项目上下文

## 项目概要

- **系统名称**：金融产品解析智能体（财富业务全场景智能问答与辅助决策）
- **一期形态**：模块化单体 + 异步 Worker；全内网私有化部署
- **核心能力**：合规约束下的实时问答、产品要素解读、产品匹配推荐、多产品对比、研报/政策/内部投研摘要、周报/月报/解读稿生成，证据引用与审计追溯

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | Vue3、Vite、Ant Design Vue、ECharts | H5 工作台；SSE/WebSocket 流式与实时通信 |
| **编排与智能体运行** | FundAgentRouter + Coordinator（当前）/ AgentScope（历史） | 当前主链路为 Coordinator 任务规划 + 业务 Agent 路由执行；AgentScope 作为历史演进背景保留 |
| **后端** | **全 Python** | FastAPI/Starlette 异步框架 |
| **关系型数据库** | MySQL | 会话/消息、配置与策略、FAQ、反馈、审计索引 |
| **缓存与限流** | Redis | 会话上下文、热点缓存、限流、幂等 |
| **向量库** | Milvus | Embedding 向量 + chunk 元数据 |
| **对象存储** | MinIO | S3 兼容；原始文档、解析中间产物、审计冷数据归档 |
| **模型** | Qwen3 / DeepSeekV3、BGE-M3、BGE-RERANKER-LARGE、MinerU | LLM、Embedding、Reranker、OCR |
| **部署** | Docker、K8S、Ascend 推理框架 | 容器化、编排、内网 NPU 算力 |

## 目录结构

```
fpai/
├── docs/                    # 项目文档
├── frontend/                # H5 前端（Vue3 + Vite）
│   ├── src/
│   │   ├── api/             # API 封装
│   │   ├── views/           # 页面
│   │   └── ...
│   └── package.json
├── backend/                 # 后端（全 Python）
│   ├── api/                 # HTTP/SSE/WS 入口
│   ├── orchestrator/        # 意图识别、任务编排
│   ├── agents/              # 各能力智能体
│   ├── retrieval/           # Milvus + Embedding + Reranker + LLM
│   ├── data_access/         # 产品主数据、可售权限、行情
│   ├── compliance/          # 输入/输出大模型审查
│   ├── audit/               # 审计与证据
│   ├── feedback/            # 反馈
│   ├── ingestion/           # 文档接入、解析、分块、向量化
│   ├── model_gateway/       # 统一调用 LLM/Embedding/Reranker/OCR
│   ├── config/              # 策略/模板/路由配置
│   └── pkg/                 # 公共模块
├── tests/                   # 所有测试文件（单元测试、集成测试、性能测试、功能验证）
│   ├── test_*.py            # 单元测试和集成测试
│   ├── test_perf_*.py       # 性能测试
│   └── conftest.py          # pytest 配置
└── scripts/                 # 运维脚本和数据迁移脚本
    ├── migrations/          # 数据库迁移脚本
    └── run_migrations.py    # 迁移执行脚本
```

## API 与契约要点

- **Base URL**：`/api/v1`
- **鉴权**：本系统维护用户表，账号+密码登录后获得 Token
- **核心端点**：
  - `POST /auth/login` - 账号密码登录
  - `POST /chat` - 多轮对话
  - `POST /compare` - 多产品对比
  - `POST /recommend` - 产品推荐
  - `POST /report/generate` - 报告生成
  - `GET /evidence/{answerId}` - 引用与证据
  - `POST /feedback` - 反馈
  - `GET /products/search` - 产品列表
- **统一响应**：`code`、`message`、`data`
- **流式**：SSE 事件类型 `message_start`、`message_delta`、`status`、`structured_update`、`citation`、`done`、`error`

## 环境与命令

| 用途 | 命令 |
|------|------|
| **后端安装依赖** | `cd backend && pip install -r requirements.txt` |
| **前端安装依赖** | `cd frontend && npm install` |
| **后端开发启动** | `cd backend && uvicorn api.main:app --reload` |
| **前端开发启动** | `cd frontend && npm run dev` |
| **运行所有测试** | `pytest tests/` |
| **运行单个测试** | `pytest tests/test_chat_api.py` |
| **运行性能测试** | `python tests/test_perf_monitoring.py` |
| **运行流式测试** | `python tests/test_streaming.py` |
| **构建（前端）** | `cd frontend && npm run build` |
| **代码检查** | 后端：`ruff check` / `black`；前端：`npm run lint` |

## 约定

- **编排约定（当前）**：聊天主链路使用 `FundAgentRouter + Coordinator`。Coordinator 负责任务规划（单任务/多任务），并按任务类型路由到业务 Agent；多任务可并行执行并融合结果。
- **大模型调用**：业务 Agent 内优先通过统一运行时封装调用模型（支持流式 token 回调与进度回调）
- **分支策略**：`main` 保护；功能开发使用 `feature/*`，修复使用 `fix/*`
- **提交规范**：Conventional Commits（`feat:`、`fix:`、`docs:`、`refactor:` 等）
- **环境变量**：敏感配置使用环境变量，不提交 `.env`；提供 `.env.example`
- **可观测性**：日志带 `traceId`、`answerId`、`userId`；敏感字段脱敏
