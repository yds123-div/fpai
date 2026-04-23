# Project Context（项目上下文）

<!-- 项目启动或技术选型确定后填写，便于 AI 与人类在实现、测试、部署时保持一致。依据：`.cursor/memory/architecture.md`、`.cursor/memory/technical_design.md`、`docs/技术架构图.md` -->

## 项目概要

- **系统名称**：金融产品解析智能体（财富业务全场景智能问答与辅助决策）
- **一期形态**：模块化单体 + 异步 Worker；全内网私有化部署。
- **核心能力**：合规约束下的实时问答、产品要素解读、产品匹配推荐、多产品对比、研报/政策/内部投研摘要、周报/月报/解读稿生成，证据引用与审计追溯。

---

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| **前端** | Vue3、Vite、Ant Design Vue、ECharts | H5 工作台；SSE/WebSocket 流式与实时通信 |
| **编排与智能体运行** | FundAgentRouter + Coordinator（当前） / AgentScope（历史） | 当前主链路为 Coordinator 任务规划 + 业务 Agent 路由执行；AgentScope 作为历史演进背景保留 |
| **后端** | **全 Python** | API 层（FastAPI/Starlette 等异步框架）、orchestrator、agents、retrieval、compliance、ingestion、model_gateway；一期不引入 Go，详见 technical_design §3.4 |
| **关系型数据库** | MySQL | 会话/消息、配置与策略、FAQ、反馈、审计索引 |
| **缓存与限流** | Redis | 会话上下文、热点缓存、限流、幂等 |
| **向量库** | Milvus | 检索服务（S1）：Embedding 向量 + chunk 元数据，权限过滤与引用 |
| **对象存储** | MinIO | S3 兼容；原始文档、解析中间产物、审计冷数据归档 |
| **模型** | Qwen3 / DeepSeekV3、BGE-M3 / BGE-LARGE-ZH、BGE-RERANKER-LARGE、MinerU / PaddleOCR | LLM、Embedding、Reranker、OCR；经 Model Gateway 统一调用 |
| **部署** | Docker、K8S、Ascend 推理框架 | 容器化、编排、内网 NPU 算力 |

---

## 目录结构

```
fpai/
├── .cursor/                 # AI 研发协作配置（rules、commands、memory、skills）
│   └── memory/              # PRD、architecture、technical_design、decisions、project_context、tasks
├── docs/                    # 项目文档（功能架构图、技术架构图、设计说明等）
├── frontend/                # H5 前端（Vue3 + Vite + Ant Design Vue + ECharts）
│   ├── src/
│   │   ├── api/             # 对 /api/v1 的封装（chat、compare、recommend、report、evidence、feedback、products）
│   │   ├── views/           # 页面（对话、对比、推荐、报告、引用展示）
│   │   └── ...
│   └── package.json
├── backend/                 # 后端（一期全 Python 模块化单体；API 层 + 编排 + 智能体 + 检索 + 合规等）
│   ├── api/                 # 对外 HTTP/SSE/WS 入口，鉴权、限流、请求解析
│   ├── orchestrator/        # Coordinator 任务规划、路由、并行执行、结果融合
│   ├── agents/              # 各业务能力智能体，由编排器按任务类型路由调用
│   │   ├── faq/
│   │   ├── rag/
│   │   ├── product_list/
│   │   ├── product_interpret/
│   │   ├── product_compare/
│   │   ├── product_recommend/
│   │   ├── report_generate/
│   │   ├── insight/
│   │   ├── product_element/
│   │   └── registry.py
│   ├── retrieval/           # Milvus + Embedding + Reranker + LLM 封装
│   ├── data_access/         # 产品主数据、可售权限、行情
│   ├── compliance/           # 输入/输出大模型审查
│   ├── audit/                # 审计与证据落库、查询、导出
│   ├── feedback/
│   ├── ingestion/            # 文档接入、解析、分块、向量化任务
│   ├── model_gateway/       # 统一调用 LLM/Embedding/Reranker/OCR
│   ├── config/               # 策略/模板/路由配置与版本
│   └── pkg/                  # 公共：日志、追踪、错误码、Redis/MySQL 客户端
├── tests/                   # 测试（单元、集成、E2E 按需）
├── scripts/                 # 脚本（迁移、运维、离线任务）
└── deploy/                  # Docker、K8S、配置清单（可选）
```

- 一期后端**全 Python**（不引入 Go）；若后续网关/会话层成为瓶颈，再考虑单独 Go 网关服务，见 `technical_design.md` §3.4。
- 实现与部署时优先参照本目录与 `technical_design.md` §3.2 的依赖方向，禁止反向依赖与循环依赖。

---

## API 与契约要点

- **Base URL**：`/api/v1`
- **鉴权**：本系统维护用户表，用户账号+密码登录后获得 Token；请求头 `Authorization: Bearer <token>`，业务层解析得到 `userId`（users.id）、`role`、`productPoolIds`。
- **核心端点**：`POST /auth/login`（账号密码登录）、`GET /auth/me`（当前用户，可选）、`POST /chat`、`POST /compare`、`POST /recommend`、`POST /report/generate`、`GET /evidence/{answerId}`、`POST /feedback`、`GET /products/search`、`GET /sessions/{sessionId}`、`POST /sessions`。
- **统一响应**：`code`、`message`、`data`；`data` 内含 `answerBlocks[]`、`citations[]`、`compliance`、`trace`、可选 `suggestedQuestions[]`、`structuredOutputs[]`。
- **流式**：SSE 事件类型 `message_start`、`message_delta`、`status`、`structured_update`、`citation`、`done`、`error`；详见 `technical_design.md` §2。

---

## 环境与命令

| 用途 | 说明 |
|------|------|
| **Python 包管理** | `pip` 或 `uv`；建议 Python 3.10+，`pip install -r requirements.txt` 或 `uv pip install -r requirements.txt` |
| **前端包管理** | `npm` / `pnpm` / `yarn`；`npm install` 或 `pnpm install` |
| **安装依赖（后端）** | `cd backend && pip install -e .` 或 `pip install -r requirements.txt`（含 agentscope、fastapi、uvicorn 等） |
| **安装依赖（前端）** | `cd frontend && npm install` |
| **开发启动（后端）** | `cd backend && uvicorn api.main:app --reload` 或 `python -m api.main`（按实际入口定） |
| **开发启动（前端）** | `cd frontend && npm run dev` 或 `pnpm dev` |
| **运行测试（后端）** | `cd backend && pytest` 或 `python -m pytest` |
| **运行测试（前端）** | `cd frontend && npm run test` 或 `pnpm test` |
| **构建（前端）** | `cd frontend && npm run build` |
| **代码检查** | 后端：`ruff check` / `black` / `mypy`（若配置）；前端：`npm run lint` / `eslint`（若配置） |
| **依赖与基础设施** | 本地开发需 MySQL、Redis、Milvus、MinIO（或 Docker Compose 启动）；模型服务经 Model Gateway 配置（内网地址）。 |

- 具体入口模块名、命令行参数以仓库内现有或后续实现的为准；上述为与 architecture/technical_design 一致的推荐命令形态。

---

## 约定

- **编排约定（当前）**：聊天主链路使用 `FundAgentRouter + Coordinator`。Coordinator 负责任务规划（单任务/多任务），并按任务类型路由到业务 Agent；多任务可并行执行并融合结果。
- **大模型调用**：业务 Agent 内优先通过统一运行时封装调用模型（支持流式 token 回调与进度回调）；`model_gateway` 仍用于非 Agent 场景（如合规审查）与基础模型能力封装。
- **分支策略**：`main` 保护；功能开发使用 `feature/*` 或 `feat/xxx`，修复使用 `fix/xxx`；发布标签 `v*`。
- **提交规范**：建议 Conventional Commits（`feat:`、`fix:`、`docs:`、`refactor:` 等），便于生成变更日志。
- **环境变量**：敏感配置（DB 连接串、Redis、Milvus、MinIO、模型 API 地址/密钥、SSO 配置）使用环境变量，不提交 `.env`；提供 `.env.example` 列出键名与说明。
- **可观测性**：日志带 `traceId`、`answerId`、`userId`；指标与链路追踪按 `architecture.md` 可观测性章节落地；敏感字段脱敏。

---

## 相关 Memory 文件

| 文件 | 用途 |
|------|------|
| `prd.md` | 产品需求、用户故事、功能/非功能需求、成功指标 |
| `architecture.md` | 系统架构、组件、数据存储、部署、意图与能力映射、自检清单 |
| `technical_design.md` | API 契约、模块结构、数据模型与存储约定、内部接口、核心应用场景与能力映射 |
| `decisions.md` | 技术决策（S1/S2/S3、MySQL、MinIO、编排内核演进、SSE 契约、API 约定等） |
| `tasks.md` | 任务拆解与执行状态（由 generate-tasks 产出并维护） |

---

填写后，实现功能、编写测试、部署时请优先参照本文件与上述 Memory 文件，保证与项目一致。
