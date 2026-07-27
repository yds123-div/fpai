# 架构决策记录（ADRs）

<!-- 重要技术决策及原因，便于后续上下文与评审 -->

---

## Decision 001：检索服务采用 LLM + Milvus + Embedding + Reranker（S1）

**标题：** 用户检索内容的回答链路采用 Milvus 向量库 + Embedding + Reranker + LLM，而非 ES/OpenSearch 一体。

**原因：**
- 语义检索与生成链路职责清晰；Milvus 专为向量场景设计，扩展性与检索性能更好。
- 与现有技术架构图（Milvus、BGE、Reranker、Qwen3/DeepSeekV3）一致，便于落地与运维统一。
- RAG 回答质量与引用可控性更优。

**日期：** 2025-03（按实际评审日期修正）

---

## Decision 002：合规审查采用统一大模型审查（S2）

**标题：** 输入与输出均经同一套 LLM 合规流程审查，规则与黑白名单作前置/兜底。

**原因：**
- 满足金融领域对输出合规的强约束；敏感主题、承诺收益、夸大宣传等由大模型统一判断，可配置/可灰度/可回滚。
- 与 PRD 中“合规校验”“可追溯”一致；审查依据与模型版本可写入审计。

**日期：** 2025-03

---

## Decision 003：证据与审计冷热分层、保留 6 个月、支持审计导出（S3）

**标题：** 审计与证据数据采用冷热分层存储，保留周期 6 个月，支持按条件导出审计报告。

**原因：**
- 近期热数据可查，超期归档至冷存储，兼顾查询性能与成本。
- 满足内外部审计与合规检查；保留期满前可审批延长或销毁。

**日期：** 2025-03

---

## Decision 004：关系型数据库选用 MySQL

**标题：** 结构化数据（会话、配置、FAQ、反馈、审计索引）使用 MySQL。

**原因：**
- 与 `docs/技术架构图.md` 数据存储层一致；行内已有 MySQL 运维与备份体系，内网私有化部署友好。
- 会话/消息/审计索引等模型适合关系型；复杂 JSON 需求可通过 JSON 列或适度反范式满足。

**日期：** 2025-03

---

## Decision 005：对象存储选用 MinIO

**标题：** 原始文档、解析中间产物、冷数据归档使用 MinIO（S3 兼容）。

**原因：**
- 技术架构图明确 MinIO；内网可自建，无公网依赖，与全内网私有化部署一致。
- S3 兼容便于后续迁移或混合云策略。

**日期：** 2025-03

---

## Decision 006：前端技术栈 Vue3 + Vite + Ant Design Vue + SSE/WebSocket

**标题：** H5 工作台采用 Vue3、Vite、Ant Design Vue；流式输出采用 SSE，可选 WebSocket。

**原因：**
- 与 `docs/技术架构图.md` 前端交互层一致；SSE 满足对话/报告流式推送，实现简单、易与现有 HTTP 鉴权结合。
- WebSocket 保留用于双向实时场景（如后续需服务端主动推送通知）。

**日期：** 2025-03

---

## Decision 007：多智能体框架采用 Agent Scope

**标题：** 编排与多智能体协作采用 Agent Scope 框架。

**原因：**
- 技术架构图指定；与架构中 Orchestrator + Agent Runtime 的职责对应，支持智能体注册、路由与任务编排。
- 便于智能体可插拔与扩展。

**日期：** 2025-03

**状态：** 历史决策（已被 Decision 012 部分替代，保留为演进背景）

---

## Decision 008：API 统一响应结构与流式事件类型

**标题：** 非流式 API 使用 envelope（code/message/data）；流式 SSE 事件类型为 message、citation、done、error。

**原因：**
- 前端统一处理成功/业务错误/合规拒答；审计与证据通过 answerId、trace 关联。
- 流式事件与 architecture 中 answerBlocks、citations、trace 契约一致，便于前端分块渲染与引用展示。

**日期：** 2025-03

**状态：** 历史决策（流式事件定义已由 Decision 013 升级）

---

## Decision 009：多智能体编排由 AgentScope 推理驱动

**标题：** 采用阿里 AgentScope 作为多智能体框架；意图识别结果作为上下文或候选工具集注入，**由 AgentScope（ReAct/工具调用或 MsgHub）在运行时推理决定**调用哪些能力、以何种顺序协作，而非仅靠“意图→主智能体”查表路由。

**原因：**
- AgentScope 理念为“释放模型的推理与工具调用潜能，而不是用僵化的提示工程和预设流程束缚”（[README_zh](https://github.com/agentscope-ai/agentscope/blob/main/README_zh.md)）；ReAct 通过 thought→action→observation 自选工具，MsgHub 提供多智能体消息编排。
- 意图与能力映射表仍保留，作为**可用工具/能力清单与典型意图对应**，用于注册到 Toolkit、设计系统提示或约束候选工具集，以及合规/审计时解释“本次调用了哪些能力”；可选混合策略为按意图缩小候选工具集后再由框架推理。

**日期：** 2025-03

**状态：** 历史决策（当前主链路以 Decision 012 为准）

---

## Decision 010：一期后端全 Python，不引入 Go

**标题：** 一期后端采用全 Python 实现（API 层用 FastAPI/Starlette 等异步框架），不引入 Golang 网关或会话层。

**原因：**
- 一期目标为 200 并发、P95≤5s，Python 异步 I/O（asyncio）可满足；瓶颈主要在 LLM/检索/外部数据源，不在网关。
- 单语言降低实现、调试与运维成本；编排、检索、合规等同进程，无跨语言 RPC 与契约维护。
- 若后续网关/会话层压测成为明确瓶颈（如数千 QPS），再单独引入 Go 网关层；详见 `technical_design.md` §3.4。

**日期：** 2025-03

---

## Decision 011：本系统维护用户表，支持账号+密码登录

**标题：** 系统维护用户主数据（users 表），支持用户采用账号和密码登录；用户表记录用户姓名、工号、邮箱等信息。

**原因：**
- 业务需求变更：需要本系统自管用户与登录，不依赖外部 SSO 即可使用。
- 用户表字段：账号（唯一）、密码哈希、姓名、工号、邮箱；会话/消息/反馈/审计中的 user_id 关联 users.id。
- 登录流程：POST /api/v1/auth/login（account + password）→ 校验后颁发 Token，返回用户信息（不含密码）；后续请求携带 Token 解析出 userId。
- 可选后续与企业 SSO/统一身份打通（同步或联邦）。

**日期：** 2025-03

---

## Decision 012：对话编排内核演进为 FundAgentRouter + Coordinator

**标题：** 聊天主链路从“意图槽位 + AgentScope 推理驱动”演进为“FundAgentRouter + Coordinator 任务规划与路由驱动”。

**原因：**
- 当前基金业务场景下，需要更强的任务可控性（单任务直达、多任务并行、结果融合），Coordinator 规划更易满足业务可解释性与稳定性要求。
- 便于把“阶段进度、子任务执行、结构化结果”统一纳入 API 流式协议和审计链路，降低前后端联调复杂度。
- 该变更为**现状实现（as-is）**；历史 Decision 007/009 作为演进背景保留，不再作为当前主链路约束。

**日期：** 2026-04

---

## Decision 013：SSE 事件契约升级并引入 structuredOutputs

**标题：** SSE 事件从 `message/citation/done/error` 升级为 `message_start/message_delta/status/structured_update/citation/done/error`，并在 done 事件兜底回传 `structuredOutputs[]`。

**原因：**
- 支持“首包可见、增量可见、进度可见、结构化可见”的前端体验，减少“后端在跑但前端无反馈”的体感问题。
- `structured_update` 可提前渲染结构化结果，`done.structuredOutputs[]` 作为最终兜底，增强链路容错性。
- 与当前 chat 路由实现和前端事件消费逻辑一致，避免文档与实现偏差。

**日期：** 2026-04

---

## Decision 014：产品检索采用本地库优先 + data_access 回退

**标题：** 产品搜索路径采用“双通道”策略：本地产品库优先，未命中时回退 `data_access` 统一接口。

**原因：**
- 本地产品库可承接同步数据后的高频查询，降低外部依赖波动对交互时延的影响。
- `data_access` 回退保留多机构多数据源扩展能力，兼顾近期效率与长期架构一致性。
- 该策略与 API 层 `/products/search` 的当前实现一致，避免设计文档误导后续开发。

**日期：** 2026-04

---

## Decision 015：会话恢复以 content_summary 为主，结构化结果持久化后补

**标题：** 当前会话恢复先以消息摘要 `content_summary` 为主，`structuredOutputs` 完整持久化列为后续演进项。

**原因：**
- 现阶段 chat/SSE 已可透传结构化结果，优先保证链路可用与交互体验。
- 结构化结果未完全持久化会影响刷新后一致性，需要后续补齐“存储模型 + 读取恢复”设计（如 MySQL JSON 列或对象存储索引化）。
- 先明确“现状 vs 目标”，避免架构文档把未完成能力误写成已落地。

**日期：** 2026-04

---

## 错误码约定（与 API envelope 一致）

- **0**：成功。
- **4xx 段**：客户端错误（参数、鉴权、限流等）；**4xx01–4xx99** 为业务/合规子码，与前端约定。
- **5xx 段**：服务端错误。
- 当前子码见 `backend/pkg/codes.py`（如 VALIDATION_ERROR=40001、COMPLIANCE_REJECT=40301、SESSION_NOT_FOUND=40401 等）；新增子码在该枚举与 DEFAULT_MESSAGES 中扩展，必要时在本节或 api_contract 中说明。

---

## 后续决策

按相同格式追加：
- **标题**
- **原因/背景**
- **日期**
