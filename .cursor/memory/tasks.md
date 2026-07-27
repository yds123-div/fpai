# Tasks

<!-- 由 generate-tasks 命令根据 PRD/架构/设计拆解；实现后更新状态。依据：`.cursor/memory/prd.md`、`architecture.md`、`technical_design.md`、`project_context.md` -->

## 状态与优先级说明

- **状态**：`pending` 未开始 → `in_progress` 进行中 → `done` 已完成 / `cancelled` 取消
- **优先级**：P0 必须 / P1 重要 / P2 可选
- **依赖**：前置任务 ID，无则填 `-`

实现时请遵循 `.cursor/commands/implement-feature.md`，完成后将对应任务状态改为 `done`。

---

## 一、基础设施与工程骨架

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T001 | 搭建后端工程骨架：backend/ 目录、pyproject.toml 或 requirements.txt、FastAPI 入口占位、.env.example（DB/Redis/Milvus/MinIO/模型地址等键） | P0 | - | done | 与 project_context 目录一致 |
| T002 | 搭建前端工程骨架：frontend/ 目录、Vue3+Vite+Ant Design Vue、package.json、环境变量示例 | P0 | - | done | 与 project_context 一致 |
| T003 | 实现 pkg 公共模块：结构化日志（含 traceId）、错误码枚举、Redis 客户端封装、MySQL 连接/会话封装 | P0 | T001 | done | 供各模块复用 |

---

## 二、数据与存储

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T004 | MySQL 建表与迁移：会话、消息、配置与策略、FAQ、反馈、审计索引（热）；冷热分层与 6 个月保留策略在 audit 实现时落地 | P0 | T001 | done | 见 technical_design §4.1；领域模型与数据源表由 T004b 补充 |
| T005 | Redis 键约定与封装：会话上下文 session:{id}、产品热点缓存 product:summary:{id}、检索结果缓存、限流 ratelimit:{userId}:chat、幂等 idempotent:{requestId} | P0 | T003 | done | 见 technical_design §4.2 |
| T006 | MinIO 客户端与 Bucket 约定：原始文档、解析中间产物、审计冷数据归档；路径规范 tenant/type/year-month/doc_id | P1 | T001 | done | 见 technical_design §4.4 |
| T007 | Milvus Collection 与封装：向量与标量字段（doc_id、source、permission_tag、created_at、chunk_text 等）、按权限过滤的查询接口 | P0 | T001 | done | 见 technical_design §4.3，S1 检索依赖 |
| T004b | MySQL 领域模型与数据源表：domain_models（模型编码、名称、描述）、domain_model_fields（字段名、类型、必填、source_path）、data_sources（model_code、org_id、类型、base_url、认证、请求/响应/映射 JSON 或关联表）、mapping_rules（可选独立表）；支持 docs/领域模型与API适配器设计.md §8 配置存储 | P0 | T004 | done | 迁移 003_domain_models_and_data_sources.sql 已新增；MySQL 未配置时 run_migrations 会跳过执行 |

---

## 三、模型与检索

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T008 | Model Gateway：统一调用 ReAgent（Qwen3/DeepSeekV3）、Embedding（BGE-M3/BGE-LARGE-ZH）、Reranker（BGE-RERANKER-LARGE）；配置化模型路由、超时与熔断 | P0 | T003 | done | 内网地址/API 配置，可先 mock 或占位 |
| T009 | 检索服务 retrieval：Embedding 向量化 query → Milvus 召回 → Reranker 精排 → ReAgent 生成回答；权限上下文过滤、citations 输出；接口 retrieve(…) 与可选 generateAnswer(…) | P0 | T006, T007, T008 | done | S1；generate_answer 已改为 ReAgent，不可用时回退 llm_chat |

---

## 四、业务数据访问与合规、审计

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T010 | 业务数据访问层 data_access 统一层（按 docs/领域模型与API适配器设计.md）：支持可配置的领域模型与元数据（Schema）；统一取数接口 get_data(model_code, request_params) → (records, total?)；按数据源配置按租户/机构路由、组装请求、解析响应、按映射规则得到符合领域模型的数据集；统一层内权限过滤（userId、productPoolIds）、缓存、熔断与观测 | P0 | T003, T004, T005, T004b（可选，若用 MySQL 存模型） | done | 已实现 get_data/list_models/get_model_metadata、模型/Fetcher 注册表、权限过滤、缓存、熔断；原 get_products/get_quotes 保留为便捷 API |
| T010a | 基于配置的 API 适配器运行时：从配置（MySQL）加载领域模型与数据源定义；支持 HTTP REST 请求定义（method、path、query/body/path 参数）、响应定义（list_path、total_path、single_path）、映射规则（response_path → model_field）；执行 get_data 时组装请求、调用机构 API、解析响应并映射为领域模型数据集；可先实现MYSQL获取配置了的数据源，调用HTTP请求API（如 0731H016 等） | P0 | T010 | done | 已实现 load_from_mysql、load_from_mysql_and_register、build_http_fetcher；从 T004b 表加载并注册后 get_data 可调机构 API |
| T011 | 合规服务 compliance：输入审查 checkInput、输出审查 checkOutput（统一大模型审查）；策略与黑白名单配置；返回通过/拒答/改写/补充提示 | P0 | T008, T003 | done | S2 统一大模型审查 |
| T012 | 审计服务 audit：appendEvent 追加审计事件、getEvidence 按 answerId 查询；冷热分层（热表+冷存 MinIO）、保留 6 个月、支持按条件导出审计报告 | P0 | T004, T005, T006 | done | S3 证据与审计 |
| T013 | 反馈闭环 feedback：反馈落库（answerId、userId、rating、comment）、查询与统计接口 | P1 | T004 | done | 见 technical_design §4.1 |

**重新完成 T004 / T010 / T010a 说明**：T004 现有表（会话、消息、配置、FAQ、反馈、审计）保持不变；**需新增表结构**由 **T004b** 承接（domain_models、domain_model_fields、data_sources、响应/映射配置）。T010 按「可配置领域模型 + get_data(model_code, request_params)」重做；T010a 按「配置化 API 适配器（请求/响应/映射）」重做，可与 T004b 并行（先 YAML 则 T004b 可延后）。

---

## 五、配置与智能体能力

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T014 | config 模块：策略/模板/路由配置与版本管理（合规策略、报告模板、对比维度模板、智能体注册信息）；可从 MySQL加载 | P1 | T004 | done | 见 architecture Policy & Template Service；合规策略与版本须从 MySQL config_strategy 加载，见 .cursor/memory/compliance_improvements_plan.md |
| T015 | 产品要素/条款抽取 product_element：内部子能力，从文档/条款中抽取期限、费率、风险、赎回规则等；供解读/对比/报告或 ingestion 调用 | P0 | T008 | done | agents/product_element/ |
| T016 | FAQ 智能体 agents/faq：FAQ 入库(MySQL)→同步→Embedding→向量库(Milvus)→TopK 检索→LLM 回答；由 Coordinator 按任务路由调用 | P0 | T004, T008, T009 | done | 方案见 .cursor/memory/faq_design.md；实现：store/sync/retrieval/agent；通过编排链路调用 |
| T017 | RAG 智能体 agents/rag：调用 retrieval 检索+生成，输出 answerBlocks 与 citations | P0 | T009, T011 | done | 由 Coordinator 路由调用 |
| T018 | 产品列表查询智能体 agents/product_list：调用 data_access 统一接口返回可售产品列表（筛选、分页） | P0 | T010a, T011 | done | 由 Coordinator 路由调用 |
| T019 | 产品解读智能体 agents/product_interpret：Data Access + 产品要素抽取 + 可选 Retrieval + LLM；输出结构化要点与风险提示 | P0 | T010a, T009, T015, T008, T011 | done | 由 Coordinator 路由调用 |
| T020 | 产品对比智能体 agents/product_compare：多产品多维对比表、差异总结；Data Access + product_element + LLM | P0 | T010a, T015, T008, T011 | done | 由 Coordinator 路由调用 |
| T021 | 产品推荐智能体 agents/product_recommend：按客户画像/需求 TopN 推荐；Data Access + LLM | P0 | T010a, T008, T011 | done | 由 Coordinator 路由调用 |
| T022 | 报告生成智能体 agents/report_generate：周报/月报/市场解读稿；Retrieval + Data Access + 模板 + LLM | P0 | T009, T010a, T008, T014, T011 | done | 由 Coordinator 路由调用 |
| T023 | 猜你想问/洞察智能体 agents/insight：会话上下文 + LLM 生成 suggestedQuestions[] | P1 | T008, T011 | done | 由 Coordinator 路由调用 |
| T024 | 智能体注册/路由配置：统一维护能力清单、任务类型映射、入口函数、超时约束；支持配置化扩展 | P0 | T016,T017,T018,T019,T020,T021,T022 | done | 与 Coordinator 任务规划和路由策略保持一致 |

---

## 六、编排与会话

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T025 | Coordinator 任务规划：根据用户输入产出单任务/多任务计划（产品查询、解读、对比、其它），并支持多任务并行 | P0 | T008 | done | orchestrator/run.py + fund_agent_framework.coordinator；规划结果写入 trace.plan |
| T026 | 编排执行与合规审计集成：按计划路由业务 Agent，执行后统一做输入/输出合规审查与审计落库 | P0 | T024, T025, T011, T012 | done | orchestrator/run.py：run_chat_turn/run_chat_turn_async、ChatTurnResult；计划→路由执行→合规输入/输出→审计 append_event |
| T027 | 会话服务：会话创建、消息持久化、会话上下文（Redis session:{id}）；会话内 productIds、customerProfile 参与编排 | P0 | T004, T005 | done | orchestrator/session.py：create_session、get_session、get_session_context_for_orchestration、update_session_context、append_message、get_recent_messages；Redis 键 session:{id}，MySQL sessions/messages |

---

## 七、API 层

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T027a | **用户与认证模块**：users 表（已迁移 002）；POST /api/v1/auth/login（账号+加密密码传输）、Token 签发与校验、GET /api/v1/auth/me；供鉴权中间件校验 Token 并注入 userId（users.id） | P0 | T003, T004 | done | auth/service.py：verify_user、issue_token、verify_token、get_user_by_id；api/routes/auth.py：POST /login、GET /me；JWT+passlib bcrypt；.env.example 增加 JWT_SECRET |
| T028 | API 层基础：FastAPI 应用、/api/v1 前缀、鉴权中间件（Bearer Token → userId/role/productPoolIds）、统一响应 envelope（code/message/data）、X-Request-Id 与 traceId | P0 | T003, T027a | done | 鉴权中间件 api/middleware.add_auth_middleware；envelope 与 X-Request-Id/traceId 已具备；api/deps.get_current_user_id、get_auth_context 供路由注入 |
| T029 | POST /api/v1/chat：多轮对话入口，支持 stream（SSE）、非流式；请求体 sessionId、message、productIds、customerProfile；响应 answerBlocks、citations、compliance、trace、suggestedQuestions[]、structuredOutputs[]；SSE 事件 message_start/message_delta/status/structured_update/citation/done/error | P0 | T026, T027, T028 | done | api/routes/chat.py：POST /chat（SSE+非流式）；隐式 create_session、写回会话上下文、append_message；新增 structuredOutputs 透传与事件序测试（tests/test_chat_sse_events.py） |
| T030 | POST /api/v1/compare、POST /api/v1/recommend、POST /api/v1/report/generate：请求/响应契约与编排调用 | P0 | T026, T028 | done | api/routes/compare_recommend_report.py：/compare、/recommend、/report/generate；调用 agents product_compare/product_recommend/report_generate query_*，envelope 含 comparisonTable/summary、products/disclaimers、reportBlocks/citations 等 |
| T031 | GET /api/v1/evidence/{answerId}、POST /api/v1/feedback、GET /api/v1/products/search、GET|POST /api/v1/sessions：证据查询、反馈、产品列表、会话详情与创建 | P0 | T012, T013, T010a, T027, T028 | done | api/routes/evidence_feedback_products_sessions.py：evidence 调 audit.get_evidence 且仅当前用户可查；feedback 调 feedback.submit_feedback；products/search 本地产品库优先、data_access.get_data(products) 回退；sessions 调 orchestrator.session.get_session/create_session；tests/test_evidence_feedback_products_sessions_api.py |

---

## 八、文档接入与前端

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T031a | **MinerU 文档解析与版面识别**：集成 MinerU 组件，对上传文档（PDF/图片等）进行版面分析、表格与公式识别、文本抽取，输出结构化文本供 ingestion 分块与向量化；归属 `parsing/` 或 `ingestion/`，与 technical_design §3.1 模型与文档解析一致 | P1 | T001 | done | backend/parsing：types（ParsedDocument/ParsedBlock）、mineru_adapter（可选依赖）、service（parse_document_bytes/file）；tests/test_parsing_mineru_optional.py 覆盖未安装时行为 |
| T032 | 文档接入与解析 ingestion：文档上传、**经 MinerU 解析**、分块、向量化任务投递（队列）；Worker 消费后写 Milvus + 元数据 | P1 | T006, T007, T008, T031a | done | ingestion：chunking、queue（Redis）、processor（解析→分块→embed→Milvus）、submit_document；POST /api/v1/documents/upload；tests/test_ingestion.py、test_documents_upload_api.py |
| T032a | **前端：用户登录页**，实现登录功能（账号+密码、调用登录 API、Token 存储、登录后跳转） | P0 | T002, T027a | done | frontend：api/auth.js、composables/useAuth.js、views/LoginView.vue、router 守卫；localStorage fpai_token/fpai_user；axios 请求头 Bearer；登录后跳 redirect 或 / |
| T033 | 前端：对话页（多轮消息、引用展示、SSE 流式、suggestedQuestions 快捷追问）、API 封装（chat/compare/recommend/report/evidence/feedback/products） | P0 | T002, T029 | done | frontend：api/chat/compare/recommend/report/evidence/feedback/products.js；ChatView.vue 多轮消息+引用+SSE+suggestedQuestions；路由 /chat；首页入口卡片 |
| T034 | 前端：产品对比页、推荐页、报告生成页、证据查询与反馈入口；产品列表/筛选（GET /products/search） | P0 | T002, T030, T031 | done | frontend：CompareView/RecommendView/ReportView/EvidenceView/FeedbackView/ProductsView；路由 /compare、/recommend、/report、/evidence、/feedback、/products；首页工作台入口卡片（T033 已有 API 封装） |

---

## 九、部署与测试

| ID | 描述 | 优先级 | 依赖 | 状态 | 备注 |
|----|------|--------|------|------|------|
| T035 | Docker 与 docker-compose：backend 镜像、MySQL/Redis/Milvus/MinIO 开发环境；可选 frontend 构建与 nginx | P1 | T001, T002 | pending | 见 project_context、architecture 部署层 |
| T036 | 关键路径单元/集成测试：API 契约（chat/compare/recommend 至少一种）、retrieval、compliance、audit 落库与查询 | P1 | T029, T030, T009, T011, T012 | pending | 见 run-tests 命令 |

---

## 依赖关系简图（便于排期）

```
T001 ─┬─ T003 ─┬─ T005 ────────────────────────────────────────┐
      │        ├─ T004 ─┬─ T004b（领域模型与数据源表，可选）───┤
      │        │        ├─ T027a（用户与认证）─ T028 ──────────┤
      │        │        ├─ T010 ─ T010a（按领域模型设计）─────┤
      │        │        ├─ T011(T008) ─────────────────────────┤
      │        │        ├─ T012 ───────────────────────────────┤
      │        │        ├─ T013, T014 ──────────────────────────┤
      │        │        └─ T027 ───────────────────────────────┤
      │        ├─ T006, T007 ─ T009 ───────────────────────────┤
      │        ├─ T031a（MinerU 解析）──────────────────────────┤
      │        │   (T032 依赖 T031a) ───────────────────────────┤
      │        └─ T008 ─┬─ T015 ────────────────────────────────┤
      │                 └─ T016..T023 ─ T024 ─ T025 ─ T026 ─┬─ T029, T030, T031
      │                                                      └─ (T028 依赖 T027a)
T002 ─────────────────────────────────────────────────────────── T033, T034
```

建议实现顺序：T001 → T002 → T003 → T004,T005,T006,T007,T008 → **T004b**（若采用 MySQL 存领域模型与数据源）→ **T027a（用户与认证）** → T009 → **T010（按 docs/领域模型与API适配器设计.md）→ T010a（配置化 API 适配器运行时）** → T011,T012 → T014,T015 → T016..T023 → T024 → T025,T026,T027 → T028 → T029,T030,T031 → T033,T034；**T031a（MinerU 文档解析）** 在 T032 之前实现；T013,T032,T035,T036 可并行或按需插入。T027a 在 T004 之后、T028 之前实现。重新完成 T004/T010/T010a 时：T004 已含会话/消息/配置/FAQ/反馈/审计表，仅需通过 T004b 新增领域模型与数据源相关表；T010/T010a 按新设计实现 get_data 与配置化适配器。
