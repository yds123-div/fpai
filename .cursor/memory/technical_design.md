# 技术设计

<!-- 由 generate-design 命令或 api-designer / database-designer / module-designer 等产出并维护 -->

**依据**：`.cursor/memory/prd.md`、`.cursor/memory/architecture.md`、`docs/技术架构图.md`

---

## 1. 概述

- **系统**：金融产品解析智能体（财富业务全场景智能问答与辅助决策）
- **一期形态**：模块化单体 + 异步 Worker；前端 H5（Vue3+Vite+Ant Design Vue），后端 Python/Go；检索链路 LLM + Milvus + Embedding + Reranker；合规统一大模型审查；审计冷热分层、保留 6 个月、支持导出。
- **本文范围**：对前端的 API 契约、技术架构与模块划分、核心数据模型与存储约定、内部服务接口及流式协议。

---

## 2. API 设计（面向 H5 / BFF）

### 2.1 通用约定

- **Base URL**：`/api/v1`（预留版本前缀）。
- **鉴权**：本系统维护用户表（users），用户采用**账号+密码**登录；登录成功后颁发 Token，请求头 `Authorization: Bearer <token>` 携带；业务层解析 Token 得到 `userId`（即 `users.id`）、`role`、`productPoolIds` 等权限上下文。可选后续对接企业 SSO/统一身份与现有 users 打通。
- **请求 ID**：请求头 `X-Request-Id` 可选，未传时由网关/BFF 生成，并贯穿日志与审计的 `traceId`。
- **统一响应 envelope（非流式）**：
  - 成功：`{ "code": 0, "message": "ok", "data": { ... } }`
  - 业务错误：`{ "code": <业务码>, "message": "<可展示文案>", "data": null }`
  - 合规拒答等：`{ "code": 合规码, "message": "...", "data": { "reason": "...", "suggestion": "建议转人工" } }`
- **错误码段**：`0` 成功；`4xx` 客户端（参数/鉴权/限流）；`5xx` 服务端；业务子码与合规子码在 `decisions.md` 或单独错误码表中维护。

### 2.2 核心端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 账号+密码登录，返回 token 与用户信息（id、姓名、工号、邮箱等） |
| GET  | `/api/v1/auth/me` | 当前登录用户信息（可选） |
| POST | `/api/v1/chat` | 多轮对话入口（可返回流式或非流式） |
| POST | `/api/v1/compare` | 多产品对比 |
| POST | `/api/v1/recommend` | 按需求与风险偏好推荐产品 |
| POST | `/api/v1/report/generate` | 周报/月报/市场解读稿生成 |
| GET  | `/api/v1/evidence/{answerId}` | 引用与证据链路查询 |
| POST | `/api/v1/feedback` | 答案反馈（有用/无用/纠错） |
| GET  | `/api/v1/products/search` | 产品列表/筛选（类型、关键词、可售权限等），对应产品列表查询智能体 |
| GET  | `/api/v1/sessions/{sessionId}` | 会话详情（可选） |
| POST | `/api/v1/sessions` | 创建会话（可选，部分实现可能由 chat 隐式创建） |

### 2.3 请求/响应契约（核心）

#### POST /api/v1/auth/login

- **请求体**：`account`（string，登录账号）、`password`（string，**密码经加密后传输**：如客户端使用服务端公钥 RSA 加密，或“服务端下发 nonce + 客户端对密码做哈希后与 nonce 一并上传”；不在信道中传明文密码）。
- **响应**：`data` 含 `token`（string，用于 Authorization 头）、`user`（object：`id`、`account`、`name`、`employee_no`、`email`，不含密码）。
- **错误**：账号不存在或密码错误返回 401 或业务码。

#### POST /api/v1/chat

- **请求体**：
  - `sessionId`（可选，无则新建会话）
  - `message`：string，用户本轮输入
  - `productIds`：string[]，可选，本会话已选产品
  - `customerProfile`：object，可选，客户画像（风险偏好、期限、流动性等）
  - `stream`：boolean，是否流式返回，默认 true（SSE）
- **响应（非流式）**：`data` 含 `answerId`、`answerBlocks[]`、`citations[]`、`compliance`、`trace`（见 architecture 契约）；可选 `suggestedQuestions[]`（猜你想问/洞察智能体输出，字符串数组）。
- **响应（流式）**：通过 SSE 推送；事件类型建议 `message`（文本块）、`citation`（引用块）、`done`（结束，含 answerId、trace、可选 suggestedQuestions[]）、`error`（错误）。

#### POST /api/v1/compare

- **请求体**：`productIds`：string[]（≥2）；`dimensionTemplateId`：可选，对比维度模板。
- **响应**：`data` 含 `comparisonTable`（结构化对比表）、`summary`、`citations[]`、`compliance`、`trace`。

#### POST /api/v1/recommend

- **请求体**：`customerProfile`（期限、流动性、风险偏好、目标收益、偏好行业等）；`topN`：可选，默认 5。
- **响应**：`data` 含 `products[]`（产品摘要 + 推荐理由）、`disclaimers`、`citations[]`、`compliance`、`trace`。

#### POST /api/v1/report/generate

- **请求体**：`templateId`（周报/月报/市场解读等）；`timeRange`；`topic`：可选。
- **响应**：`data` 含 `reportBlocks[]`（标题/摘要/要点/风险提示/参考来源）、`citations[]`、`trace`；大报告可支持流式返回或异步任务+轮询。

#### GET /api/v1/evidence/{answerId}

- **响应**：`data` 含请求摘要、意图、数据源、检索证据片段、模型/策略版本、操作人、时间戳（与审计共用证据对象，脱敏按权限）。

#### GET /api/v1/products/search

- **查询参数**：`productType`（可选）、`keyword`（可选）、`page`、`pageSize`；权限由 BFF 注入，仅返回当前用户可售且符合 productPoolIds 的产品。
- **响应**：`data` 含 `products[]`（产品摘要列表：id、名称、类型、风险等级、期限等）、`total`；用于产品列表查询智能体能力的前端直连入口；若一期全部通过 chat 内意图路由也可不暴露，但编排器需在 intent=product_list 时调用产品列表查询智能体并返回结构化列表。

#### POST /api/v1/feedback

- **请求体**：`answerId`；`rating`：enum（useful / not_useful / inaccurate）；`comment`：可选。
- **响应**：`data` 为 `{ "ack": true }`。

### 2.4 流式协议（SSE / WebSocket）

- **SSE（推荐用于 chat/report 流式）**
  - Content-Type: `text/event-stream`；事件格式：`event: <type>\ndata: <JSON>\n\n`。
  - 类型：`message`（内容块）、`citation`（引用）、`done`（含 answerId、trace）、`error`（含 code、message）。
  - 前端需支持断线重连与 `X-Request-Id` 幂等（可选）。
- **WebSocket（可选，用于双向实时）**
  - 连接后鉴权（如 query 携带 token 或首帧 auth）；消息格式 JSON：`{ "type": "chat"|"ping"|..., "payload": { ... } }`；服务端推送类型与 SSE 对齐，便于前端统一处理。
- 详细帧格式与错误码在实现时可在本段下追加或单独 `api_contract.md`。

### 2.5 核心应用场景与智能体/能力映射（与 architecture、AgentScope 对齐）

以下确保「Agent Runtime 及内置智能体」每一类应用场景在 API 与能力注册中有明确落地。**采用 AgentScope 时**：意图识别结果作为**上下文或候选工具集**注入，**由 AgentScope 的 ReAct/工具推理或 MsgHub 在运行时决定**调用哪些能力、以何种顺序协作；下表为**可用能力与典型意图的对应**，用于向 AgentScope 注册工具、设计提示或约束候选集，而非强制查表路由。审计记录“实际被调用的工具/能力”（由框架推理产生）。

| 应用场景（能力/智能体） | 意图标识建议 | 依赖能力 | 前端入口 | 说明 |
|-------------------|--------------|----------|----------|------|
| FAQ 问答 | faq / standard_reply | FAQ 库（MySQL） | POST /chat | 命中 FAQ 时直接返回标准答，可带引用 |
| RAG（研报/政策/观点） | rag_summary / policy / research | Retrieval（Milvus+Embedding+Reranker+LLM） | POST /chat | 检索 + 重排 + 生成，带 citations |
| 产品列表查询 | product_list / product_search | Data Access（可售/权限/筛选） | POST /chat 或 GET /products/search | 返回结构化产品列表，供选择或继续解读/对比 |
| 产品解读 | product_interpretation | Data Access + 产品要素抽取（内部）+ 可选 Retrieval + LLM | POST /chat | 会话中若有 productIds 且问“这只是啥”等，路由到此 |
| 产品对比 | product_compare | Data Access + 产品要素抽取（内部）+ LLM | POST /compare | 多产品多维对比表 + 差异总结 |
| 产品推荐 | product_recommend | Data Access + LLM | POST /recommend | 按客户画像/需求 TopN 推荐 |
| 报告生成 | report_generate | Retrieval + Data Access + 模板 + LLM | POST /report/generate | 周报/月报/市场解读稿 |
| 猜你想问/洞察 | insight / guess_question | 会话上下文 + 行为 + LLM | POST /chat 响应 suggestedQuestions[] | 作为兜底或增强，在 done 时返回推荐问题列表 |
| 产品要素/条款抽取 | （内部子能力） | 文档解析 + LLM/规则 | 被解读/对比/报告智能体或 Ingestion 调用 | 不单独对前端暴露 API |
| 智能图谱构建 | （二期） | — | — | 一期保留扩展点，不实现 |
| 扩展智能体 | 配置化 intent_id | 按注册表与路由配置 | 通过 /chat 或专用路径由编排器路由 | 插件注册表 + 配置驱动路由 |

- **Chat 与 AgentScope 编排**：`POST /chat` 请求进入后，Intent & Slot Service 产出意图与槽位；**将意图与槽位作为上下文或候选工具集传入 AgentScope**，由 ReAct 主智能体或 MsgHub 参与者在运行时**推理**调用上表能力（工具）；会话内的 `productIds`、`customerProfile` 参与槽位填充与权限过滤。可选：仅将“与当前意图相关的工具子集”暴露给 AgentScope 以兼顾合规与延迟。所有输出经 Compliance 审查后返回，并写入 Audit（记录实际调用的工具/能力）。
- **产品要素抽取**：作为内部能力/工具，由产品解读、产品对比、报告生成在需要时调用（如从说明书/条款中抽期限、费率、风险等）；Ingestion 侧文档入库时也可调用同一套抽取能力做结构化落库。

---

## 3. 技术架构与模块结构

### 3.1 与 docs/技术架构图.md 的对应

| 技术架构图层 | 实现职责 | 建议代码归属 |
|--------------|----------|--------------|
| 前端交互层 | Vue3+Vite+Ant Design Vue，ECharts，SSE/WebSocket 客户端 | 独立前端仓库或 `frontend/` |
| 多智能体框架 | AgentScope（ReAct、Toolkit、MsgHub）编排；意图/槽位作为上下文或候选工具集，**由框架推理决定**调用哪些能力与协作顺序 | 后端 `orchestrator/`、`agents/` |
| 数据适配层 | **全 Python**：业务逻辑、API 层、RAG、解析、模型调用（推荐一期）；或 Python + Go 混合（Go 仅做网关/高并发层，见下文对比） | 后端 `backend/`（单仓 Python） |
| 数据存储层 | MySQL、Redis、Milvus、MinIO 的接入与封装 | `storage/`、`retrieval/`、`ingestion/` |
| 模型与文档解析 | LLM/Embedding/Reranker 经 Model Gateway 统一调用；**文档解析与版面识别采用 MinerU 组件**（PDF/图片等版面分析、表格/公式识别、文本抽取），输出结构化文本供分块与向量化 | `model_gateway/`、`parsing/`（MinerU） |
| 部署层 | Docker、K8S、Ascend 推理 | 运维/CI/CD 与部署清单 |

### 3.2 后端模块划分（一期模块化单体）

建议按“包/模块”划分，便于后续拆服务；同一进程内通过接口/依赖注入调用。

```
backend/
├── api/                    # 对外 HTTP/SSE/WS 入口，鉴权、限流、请求解析
├── orchestrator/           # 意图识别、槽位抽取、任务编排、智能体选择与执行
├── agents/                 # 各能力/智能体实现（见下表）；向 AgentScope 注册为 Toolkit 工具或子智能体，**由 AgentScope 推理决定调用组合与顺序**
│   ├── faq/                 # FAQ 问答智能体
│   ├── rag/                 # RAG 智能体（内部调 retrieval）
│   ├── product_list/       # 产品列表查询智能体
│   ├── product_interpret/  # 产品解读智能体（可调 product_element 子能力）
│   ├── product_compare/     # 产品对比智能体
│   ├── product_recommend/   # 产品检索推荐智能体
│   ├── report_generate/    # 智能报告生成智能体
│   ├── insight/             # 猜你想问/风险点洞察智能体
│   ├── product_element/     # 产品要素/条款抽取（内部子能力，被解读/对比/报告或 ingestion 调用）
│   └── registry.py         # 智能体注册表：id、名称、意图映射、入口函数、超时/成本约束；支持配置化扩展
├── retrieval/              # 检索服务：Milvus + Embedding + Reranker + LLM 封装
├── data_access/            # 业务数据访问层：产品主数据、可售权限、行情
├── compliance/             # 合规服务：输入/输出大模型审查、策略与黑白名单
├── audit/                  # 审计与证据：落库、查询、导出
├── feedback/               # 反馈闭环
├── ingestion/              # 文档接入、解析（MinerU）、分块、向量化任务投递
├── parsing/                # 可选：MinerU 文档解析与版面识别封装，供 ingestion 调用
├── model_gateway/          # 统一调用 LLM/Embedding/Reranker/OCR
├── config/                 # 策略/模板/路由配置与版本
└── pkg/                    # 公共：日志、追踪、错误码、Redis/MySQL 客户端
```

- **依赖方向**：`api` → `orchestrator` → `agents`、`retrieval`、`data_access`、`compliance`、`audit`；`agents` 依赖 `retrieval`、`data_access`、`model_gateway`；`ingestion` 依赖 **MinerU 解析**（`parsing/` 或内置）、`model_gateway`、队列、Milvus、MinIO。禁止反向依赖与循环依赖。
- **一期后端全 Python**：`api` 层使用 FastAPI/Starlette 等异步框架提供 HTTP/SSE/WS，鉴权与限流在同一进程内完成；与编排、智能体、检索、合规等无跨进程调用，延迟更小。若后续引入 Go 网关见 §3.4。

### 3.3 内部服务接口（应用层内）

- **Orchestrator → Data Access**：按产品 ID/类型、可售权限查询产品要素、行情；接口需带 `userId`、`productPoolIds`。Data Access 对上游暴露**统一领域模型与接口**；内部按机构/数据源通过**适配器**对接各家不同请求体/响应体，见下文「业务数据访问层与多机构适配」。
- **Orchestrator → Retrieval**：`retrieve(query, filters, topK, permissionContext) → (chunks, scores, citations)`；可选 `generateAnswer(query, chunks) → (answerBlocks, citations)` 由检索服务内调 LLM。
- **Orchestrator → Compliance**：`checkInput(text, userId) → decision`；`checkOutput(text, structuredOutput, citations) → decision`；返回通过/拒答/改写/补充提示等。
- **Orchestrator / Agents → Audit**：`appendEvent(answerId, event)` 追加审计事件；查询由 `evidence/{answerId}` 对前端暴露，后端调用 `audit.getEvidence(answerId)`。
- **Ingestion → Queue**：文档解析/向量化任务投递；Worker 消费后写 Milvus + 元数据，必要时更新 MySQL 文档状态。

**智能体与下游依赖（支撑核心应用场景）**：

| 智能体 | Data Access | Retrieval | Model Gateway（LLM/Embedding/Reranker） | 产品要素抽取（内部） | Compliance |
|--------|-------------|-----------|----------------------------------------|----------------------|------------|
| FAQ 问答 | — | 可选（FAQ 也可向量化） | 可选（匹配后生成话术） | — | 输出审查 |
| RAG | — | 是 | 是（生成） | — | 输出审查 |
| 产品列表查询 | 是 | — | — | — | 输出审查 |
| 产品解读 | 是 | 可选（条款/说明书） | 是 | 是 | 输出审查 |
| 产品对比 | 是 | 可选 | 是 | 是 | 输出审查 |
| 产品推荐 | 是 | — | 是 | — | 输出审查 |
| 报告生成 | 是 | 是 | 是 | 可选 | 输出审查 |
| 猜你想问/洞察 | — | 可选 | 是 | — | 输出审查 |
| 产品要素抽取 | — | 可选 | 是（或规则） | — | 内部不直接对用户，由调用方负责合规 |

### 3.4 全 Python 与 Python+Go 对比（一期推荐全 Python）

| 维度 | 全 Python | Python + Go（Go 做网关/会话层） |
|------|-----------|----------------------------------|
| **技术栈** | 单语言，API 层用 FastAPI/Starlette 等异步框架，与 AgentScope、retrieval、compliance 同进程或同仓 | 双语言，Go 负责 BFF/网关、高并发会话与缓存，Python 负责编排与智能体；需 gRPC 或 HTTP 内网约定 |
| **部署与运维** | 单进程或单镜像即可，调试、链路追踪、日志统一 | 至少两个服务/镜像，跨语言 RPC、契约与排障更复杂 |
| **性能** | 一期目标（200 并发、P95≤5s）下，Python 异步 I/O（asyncio）足够；瓶颈多在 LLM/检索/外部数据源，不在网关 | 网关层可承受更高 QPS、更低延迟；适合网关与业务解耦、独立扩缩 |
| **团队与生态** | 只需 Python；AgentScope、RAG、模型调用均为 Python 生态，无跨进程序列化与接口维护 | 需兼顾 Go 与 Python 两套依赖、构建与发布 |
| **何时考虑 Go** | — | 当网关/会话层成为明确瓶颈（如数千 QPS、或需极低延迟的协议解析）时，再引入 Go 网关层；二期按需拆分 |

**结论**：**一期更优为全 Python**。理由：需求明确为 200 并发、P95≤5s；模块化单体已足够；单语言降低实现与运维成本；AgentScope 与全部能力同进程可减少跨调用延迟。若后续网关或会话层压测不达标，再单独引入 Go 网关层不迟。

---

## 4. 数据模型与存储约定

### 4.1 MySQL（核心表用途）

| 逻辑表/用途 | 说明 |
|-------------|------|
| **用户（users）** | 账号（account，唯一）、密码哈希（password_hash）、姓名（name）、工号（employee_no）、邮箱（email）；支持账号+密码登录，业务层以 users.id 作为 userId |
| 会话 / 消息 | 会话 id、用户 id（关联 users.id）、创建/更新时间；消息表：会话 id、角色、内容摘要、answer_id、引用块数等（正文过大可放冷存储或对象存储） |
| 配置与策略 | 合规策略版本、路由策略、报告模板、对比维度模板、智能体注册信息 |
| FAQ 库 | 标准问、标准答、标签、生效时间（可扩展为多表） |
| 反馈 | answer_id、用户 id（关联 users.id）、rating、comment、时间 |
| 审计索引（热） | answer_id、session_id、user_id（关联 users.id）、intent、model_version、policy_version、created_at；审计正文或大字段冷分层后存 MinIO 或归档表 |

- **user_id 来源**：本系统维护用户表 `users`（见迁移 002）；用户通过账号+密码登录，登录后会话/请求上下文中的 `userId` 即 `users.id`。各表中 `user_id` 关联 `users.id`，用于归属、审计与权限过滤。可选后续与 SSO/统一身份打通（如同步或联邦）。
- 具体建表、索引、冷热分层字段与迁移策略在实现阶段按 DBA 规范补充；此处仅约定用途与边界。

### 4.2 Redis

- **会话上下文**：`session:{sessionId}`，TTL 按会话超时配置（如 30 分钟续期）。
- **热点缓存**：产品要素 `product:summary:{productId}`；检索结果缓存 key 含 `query_hash`、`filters_hash`、`user_context_hash`，TTL 适中（如 5–10 分钟）。
- **限流/幂等**：`ratelimit:{userId}:chat`；`idempotent:{requestId}`（可选）。

### 4.3 Milvus

- **Collection**：存储 chunk 向量与标量字段；标量字段至少包含：`doc_id`、`source`、`permission_tag`、`created_at`、`chunk_text`（或仅存 id，正文在 MySQL/MinIO）。
- **检索**：按 `permission_tag`/`product_pool` 等做过滤，与架构中“检索前过滤”一致；检索服务封装“检索后强过滤”与引用输出。

### 4.4 MinIO

- **Bucket**：原始文档、解析后文本/分块结果、审计冷数据归档；路径建议按 `tenant/type/year-month/doc_id` 等规范，便于保留周期与导出。

---

## 5. 其他技术设计

### 5.0 业务数据访问层与多机构适配（满足不同银行 API 差异）

- **目标**：上游（编排、智能体）只依赖**统一领域模型与统一取数接口**；各机构 API 的请求/响应差异由本层通过**可配置的领域模型、元数据与 API 适配器**吸收，不向上暴露。详见 `docs/领域模型与API适配器设计.md`。
- **统一领域模型（可定义）**：一个接口对应一个领域模型（如基金相关接口 0731H016～A0731H046 各对应一个模型）。每个模型有：**模型编码**、**名称**、**元数据（Schema）**（字段名、类型、必填、source_path 等）。支持在系统内定义与扩展，而非写死少数类。
- **元数据（Metadata）**：描述领域模型的数据形状（字段列表、类型、是否必填、默认值）；并支持 **source_path** 等映射信息，用于将 API 响应解析后映射到该模型，得到符合元数据的数据集。
- **数据获取方式与 API 适配器**：为每个领域模型配置**通过何种方式**获取数据（先支持 **HTTP REST**）。对 HTTP 方式需配置：**请求定义**（method、path、query/body/path 参数）、**响应定义**（数据列表/总数/单条的路径，如 list_path、total_path）、**映射规则**（响应路径 → 模型字段）。请求体参数与响应结构均通过配置描述，解析结果按映射规则写入领域模型元数据，得到真实数据集。
- **统一接口**：`get_data(model_code, request_params, options?) → (records, total?)`，按领域模型编码与请求参数取数；可选保留 `get_products` / `get_quotes` / `check_sale_permission` 等便捷 API，内部可封装为对上述模型的调用或与预置模型并存。
- **路由与多机构**：根据请求上下文（租户 id、机构 id 或 productPoolIds）选择该模型对应的数据源实例（如不同 base_url、认证）；配置可含 base_url、认证方式、超时等。新增接口时以**配置领域模型 + 数据源 + 请求/响应/映射**为主，无需为每个接口写死适配器类。
- **在统一层完成**：权限过滤（按 permission_context）、缓存（如按 model_code + params）、熔断与观测（按机构/接口打点），保证统一口径。

### 5.1 安全与鉴权

- 本系统维护用户表，用户以账号+密码登录，登录成功后颁发 Token；对前端的业务 API 需校验 Token 并解析出 `userId`（users.id）、`role`、`productPoolIds`、`dataSourceTags` 等注入下游。可选由 BFF/网关统一鉴权后注入。
- 检索与数据访问层必须使用上述权限上下文做过滤；审计记录操作人与时间戳。
- 敏感字段（密码、Token 明文）不写入日志与监控；审计导出按角色做脱敏与范围控制。

### 5.2 性能与降级

- P95 ≤ 5s：并行调用（数据访问 + 检索）、热点缓存、检索结果缓存、生成超时与熔断；外部研报源不可用时降级为内部知识库或缓存摘要。
- 流式优先：chat/report 优先 SSE 流式返回，首字延迟优于整段生成再返回。

### 5.3 可观测性

- 日志、指标、链路追踪与 `architecture.md` 一致；`traceId`、`answerId`、`intent`、`modelVersion`、`policyVersion`、`latencyMs`、`cacheHit`、`complianceDecision` 等结构化输出。
- 检索、重排、生成、合规审查、数据源调用各自打 span，便于定位 P95。

### 5.4 配置与版本

- 合规策略、路由策略、报告模板等支持版本管理与灰度；回滚时切换版本号或配置快照，无需改代码。

---

## 6. 与架构/PRD 的对照

- **API**：满足 PRD 中对话、对比、推荐、报告、证据、反馈等用户故事；响应结构满足 architecture 的 `answerBlocks`、`citations`、`compliance`、`trace`、`suggestedQuestions[]` 契约；产品列表查询可通过 GET /products/search 或 chat 内路由覆盖。
- **技术架构**：与 `docs/技术架构图.md` 六层对应；检索链路为 LLM + Milvus + Embedding + Reranker；合规为统一大模型审查；审计为冷热分层、6 个月保留、支持导出。
- **模块边界**：Orchestrator、Retrieval、Compliance、Doc Processing、Model Gateway 等均可独立拆分为服务，满足架构自检清单中的“模块边界是否支持演进”。
- **核心应用场景（Agent Runtime 及内置智能体）**：architecture 中列出的 FAQ、RAG、产品列表查询、产品解读、产品对比、产品要素抽取、洞察、报告生成、扩展智能体，在本文中均有对应——见 §2.5 场景与智能体映射、§3.2 agents 子模块与注册表、§3.3 智能体与下游依赖表；产品要素抽取作为内部子能力被解读/对比/报告或 Ingestion 调用；智能图谱构建一期保留扩展点不实现。
