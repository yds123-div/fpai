---
description: 已有功能导航文档 - 快速定位模块、类、接口、方法
inclusion: auto
---

# 功能导航文档

> 本文档是项目的"功能地图"，帮助 AI 快速定位已有功能的位置，避免全项目搜索。
> 
> **使用场景**：
> - 需要修改某个功能时，先查本文档找到对应文件
> - 需要调用某个服务时，查找对应的类和方法
> - 需要了解某个模块的职责时，查看模块说明

---

## 📋 目录

- [后端模块](#后端模块)
  - [API 路由层](#api-路由层)
  - [智能体层](#智能体层)
  - [核心服务层](#核心服务层)
  - [数据访问层](#数据访问层)
  - [基础设施层](#基础设施层)
- [前端模块](#前端模块)

---

## 后端模块

### API 路由层

**位置**：`backend/api/routes/`

所有 HTTP/SSE 端点的入口，负责请求解析、鉴权、参数验证、响应封装。

| 路由文件 | 端点 | 主要方法 | 说明 |
|---------|------|---------|------|
| `auth.py` | `/api/v1/auth/*` | `auth_login()`, `auth_me()`, `change_password()`, `update_me()` | 用户登录、获取当前用户、修改密码、更新用户信息 |
| `chat.py` | `/api/v1/chat` | `chat()` | 多轮对话入口（支持流式 SSE 和非流式），路由到各智能体 |
| `compare_recommend_report.py` | `/api/v1/compare`, `/api/v1/recommend`, `/api/v1/report/generate` | `compare()`, `recommend()`, `generate_report()` | 产品对比、推荐、报告生成 |
| `evidence_feedback_products_sessions.py` | `/api/v1/evidence/{answerId}`, `/api/v1/feedback`, `/api/v1/products/search`, `/api/v1/sessions/*` | `get_evidence()`, `post_feedback()`, `products_search()`, `list_sessions()`, `get_session()` | 引用证据查询、反馈提交、产品搜索、会话管理 |
| `knowledge.py` | `/api/v1/knowledge/*` | `external_knowledge_query()`, `knowledge_chat()` | 外部知识库查询、知识库对话 |
| `rbac.py` | `/api/v1/rbac/*` | `list_roles()`, `upsert_role()`, `list_menus()`, `upsert_menu()`, `set_user_roles()`, `set_role_menus()`, `list_user_menus()` | 角色、菜单、用户角色、角色菜单管理（RBAC） |
| `models.py` | `/api/v1/models/*` | `list_models()`, `upsert_model()`, `delete_model()`, `test_model()` | 模型配置管理（LLM/Embedding/Reranker） |
| `agents.py` | `/api/v1/agents/*` | `list_agents()`, `get_agent()`, `upsert_agent()`, `delete_agent()` | Agent 配置管理 |
| `skills.py` | `/api/v1/skills/*` | `list_skills()`, `get_skill()`, `upsert_skill()`, `delete_skill()` | Skill 配置管理 |
| `config.py` | `/api/v1/config/*` | `get_external_kb_config()`, `update_external_kb_config()` | 外部知识库配置管理 |
| `documents.py` | `/api/v1/documents/upload` | `upload_document()` | 文档上传 |
| `users.py` | `/api/v1/users/*` | `list_users()`, `create_user()`, `update_user()`, `delete_user()` | 用户管理（管理员功能） |

**关键依赖**：
- `api/deps.py` - 依赖注入（鉴权、权限上下文）
- `api/middleware.py` - 中间件（traceId、CORS、异常处理）
- `api/main.py` - FastAPI 应用入口

---

### 智能体层

**位置**：`backend/agents/`

各业务能力智能体，向 AgentScope 注册为 Toolkit 或子智能体。

#### 核心智能体

| 智能体 | 文件路径 | 主要类/方法 | 适用场景 |
|-------|---------|-----------|---------|
| **FAQ 问答** | `agents/faq/agent.py` | `query_faq()`, `faq_query()` | 标准问答、话术库检索 |
| **RAG 检索** | `agents/rag/agent.py` | `RAGAgent.run()` | 研报/政策/观点摘要 |
| **产品列表查询** | `agents/product_list/agent.py` | `ProductListAgent.run()` | 产品列表/筛选 |
| **产品解读** | `agents/fund_agent/product_interpret/agent.py` | `ProductInterpretAgent.run()` | 产品要素解读 |
| **产品对比** | `agents/fund_agent/product_compare/agent.py` | `ProductCompareAgent.run()` | 多产品对比 |
| **产品推荐** | `agents/fund_agent/product_recommend/agent.py` | `ProductRecommendAgent.run()` | 按需求推荐产品 |
| **产品查询** | `agents/fund_agent/product_query/agent.py` | `ProductQueryAgent.run()` | 产品信息查询 |
| **其它问题** | `agents/fund_agent/other/agent.py` | `OtherAgent.run()` | 兜底智能体（外部知识库/自由回答） |
| **报告生成** | `agents/report_generate/agent.py` | `ReportGenerateAgent.run()` | 周报/月报/解读稿生成 |

#### 智能体管理

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **Agent 配置存储** | `agents/agent_store.py` | `list_agents()`, `get_agent()`, `upsert_agent()`, `delete_agent()` | Agent 配置的 CRUD（MySQL） |
| **Skill 配置存储** | `agents/skills_store.py` | `list_skills()`, `get_skill()`, `upsert_skill()`, `delete_skill()` | Skill 配置的 CRUD（MySQL） |
| **Agent 运行时** | `agents/fund_agent/runtime.py` | `AgentRunContext`, `BaseBusinessAgent`, `resolve_agent_overrides()`, `run_configured_skills()` | Agent 上下文、基类、配置覆盖、Skill 执行 |
| **模型配置** | `agents/model_config.py` | 模型配置辅助函数 | Agent 使用的模型配置 |

#### Skills（可复用能力）

| Skill | 文件路径 | 主要方法 | 说明 |
|-------|---------|---------|------|
| **基金名称转代码** | `agents/skills/fund_name_to_code/runtime.py` | `run()` | 将基金名称转换为代码 |
| **产品对比** | `agents/skills/product_compare/runtime.py` | `run()` | 产品对比逻辑 |
| **产品解读** | `agents/skills/product_interpret/runtime.py` | `run()` | 产品解读逻辑 |
| **产品查询** | `agents/skills/product_query/runtime.py` | `run()` | 产品查询逻辑 |
| **产品推荐** | `agents/skills/product_recommend/runtime.py` | `run()` | 产品推荐逻辑 |

---

### 核心服务层

#### 编排器（Orchestrator）

**位置**：`backend/orchestrator/`

意图识别、任务编排、AgentScope 调度。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **任务编排** | `orchestrator/run.py` | `run_chat_turn_async()` | 多轮对话编排入口，路由到各智能体 |
| **会话管理** | `orchestrator/session.py` | `create_session()`, `get_session()`, `update_session_context()`, `append_message()`, `get_recent_messages()` | 会话创建、上下文管理、消息历史 |

#### 检索服务（Retrieval）

**位置**：`backend/retrieval/`

Milvus + Embedding + Reranker + LLM 封装。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **检索服务** | `retrieval/service.py` | `retrieve()`, `generate_answer()` | 向量检索、生成回答（基于检索结果） |
| **检索类型** | `retrieval/types.py` | `Citation`, `RetrieveResult`, `GenerateAnswerResult` | 引用、检索结果、生成结果数据类 |

#### 合规服务（Compliance）

**位置**：`backend/compliance/`

输入/输出大模型审查。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **合规审查** | `compliance/service.py` | `check_input()`, `check_output()` | 输入/输出合规审查（LLM + 规则） |
| **合规策略** | `compliance/config.py` | `CompliancePolicy` | 合规策略配置（黑白名单、敏感主题） |
| **合规类型** | `compliance/types.py` | `ComplianceAction`, `ComplianceDecision` | 合规动作、决策数据类 |

#### 审计服务（Audit）

**位置**：`backend/audit/`

全链路审计与证据追溯。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **审计存储** | `audit/store.py` | `append_event()`, `get_evidence()`, `archive_to_cold()`, `list_answer_ids_for_retention()` | 审计事件落库、证据查询、冷归档、留存管理 |
| **审计类型** | `audit/types.py` | `AuditEvent`, `Evidence` | 审计事件、证据数据类 |

#### 反馈服务（Feedback）

**位置**：`backend/feedback/`

用户反馈闭环。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **反馈存储** | `feedback/store.py` | `save_feedback()`, `list_feedback()` | 反馈保存、查询 |
| **反馈类型** | `feedback/types.py` | `Feedback` | 反馈数据类 |

#### 文档接入（Ingestion）

**位置**：`backend/ingestion/`

文档接入、解析、分块、向量化任务。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **文档处理器** | `ingestion/processor.py` | `process_document()` | 文档解析、分块、向量化 |
| **分块策略** | `ingestion/chunking.py` | `chunk_text()` | 文本分块 |
| **任务队列** | `ingestion/queue.py` | `enqueue_task()`, `dequeue_task()` | 异步任务队列 |
| **提交入口** | `ingestion/submit.py` | `submit_document()` | 文档提交入口 |

#### 文档解析（Parsing）

**位置**：`backend/parsing/`

文档解析（MinerU/PaddleOCR）。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **解析服务** | `parsing/service.py` | `parse_document()` | 文档解析入口 |
| **MinerU 适配器** | `parsing/mineru_adapter.py` | `parse_with_mineru()` | MinerU 解析适配 |
| **解析类型** | `parsing/types.py` | `ParseResult` | 解析结果数据类 |
| **解析错误** | `parsing/errors.py` | `ParsingError` | 解析异常 |

---

### 数据访问层

**位置**：`backend/`

#### 产品数据（Products）

**位置**：`backend/products/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **产品存储** | `products/store.py` | `upsert_products()`, `search_products()` | 产品数据 CRUD（MySQL） |

#### 权限管理（RBAC）

**位置**：`backend/rbac/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **RBAC 存储** | `rbac/store.py` | `list_roles()`, `upsert_role()`, `list_menus()`, `upsert_menu()`, `get_user_roles()`, `set_user_roles()`, `set_role_menus()`, `list_user_menus()`, `ensure_seed_admin()` | 角色、菜单、用户角色、角色菜单管理 |

#### 用户认证（Auth）

**位置**：`backend/auth/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **认证服务** | `auth/service.py` | `verify_password()`, `hash_password()`, `create_token()`, `verify_token()` | 密码验证、Token 生成/验证 |

#### 模型配置（Models）

**位置**：`backend/models/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **模型存储** | `models/store.py` | `list_models()`, `get_model_by_id()`, `upsert_model()`, `delete_model()` | 模型配置 CRUD（MySQL） |

#### 知识库（Knowledge）

**位置**：`backend/knowledge/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **知识库存储** | `knowledge/store.py` | `list_knowledge_bases()`, `get_knowledge_base()`, `upsert_knowledge_base()` | 知识库配置 CRUD（MySQL） |
| **知识库同步** | `knowledge/sync.py` | `sync_knowledge_to_milvus()` | 知识库同步到 Milvus |

#### 配置管理（Config）

**位置**：`backend/config/`

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **配置存储** | `config/store.py` | `get_config()`, `set_config()` | 系统配置 CRUD（MySQL） |

#### 统一数据访问（Data Access）

**位置**：`backend/data_access/`

统一封装多机构/多数据源的产品主数据、可售权限、行情等。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **统一接口** | `data_access/unified.py` | `get_data()` | 统一数据访问入口（缓存、权限过滤、熔断） |
| **领域模型** | `data_access/domain_model.py` | `FieldDef`, `ModelMetadata`, `DomainModelInfo` | 标准产品模型定义 |
| **模型注册表** | `data_access/model_registry.py` | `register_model()`, `register_fetcher()`, `get_model_info()`, `get_fetcher()` | 模型与数据源注册 |
| **适配器加载** | `data_access/adapters/config_loader.py` | `DataSourceConfig`, `build_http_fetcher()` | 数据源配置加载、HTTP 适配器构建 |
| **熔断器** | `data_access/_circuit.py` | `record_failure()`, `record_success()`, `is_open()`, `reset()` | 熔断器（防雪崩） |

---

### 基础设施层

#### 模型网关（Model Gateway）

**位置**：`backend/model_gateway/`

统一调用 LLM/Embedding/Reranker/OCR。

| 模块 | 文件路径 | 主要方法 | 说明 |
|-----|---------|---------|------|
| **LLM 调用** | `model_gateway/llm.py` | `llm_chat()`, `llm_chat_stream()` | LLM 调用（同步/流式） |
| **Embedding 调用** | `model_gateway/embedding.py` | `embed()` | Embedding 向量化 |
| **Reranker 调用** | `model_gateway/reranker.py` | `rerank()` | Reranker 精排 |
| **网关配置** | `model_gateway/config.py` | `load_gateway_config()`, `LLMConfig`, `EmbeddingConfig`, `RerankerConfig` | 模型网关配置加载 |
| **熔断器** | `model_gateway/_circuit.py` | `record_failure()`, `record_success()`, `is_open()`, `reset()` | 熔断器（防雪崩） |

#### 公共模块（Pkg）

**位置**：`backend/pkg/`

日志、追踪、错误码、数据库客户端等。

| 模块 | 文件路径 | 主要方法/类 | 说明 |
|-----|---------|-----------|------|
| **错误码** | `pkg/codes.py` | `ErrorCode`, `envelope()`, `message_for()` | 统一错误码与响应封装 |
| **日志** | `pkg/logger.py` | `get_logger()`, `bind_trace_id()`, `get_trace_id()` | 结构化日志与 traceId |
| **MySQL 客户端** | `pkg/mysql_client.py` | `get_connection()`, `is_configured()` | MySQL 连接池 |
| **Redis 客户端** | `pkg/redis_client.py` | `get_client()`, `is_available()` | Redis 客户端 |
| **Redis 键** | `pkg/redis_keys.py` | `key_session()`, `key_product_summary()`, `key_retrieval_cache()`, `key_ratelimit()`, `key_idempotent()` | Redis 键命名规范 |
| **Milvus 客户端** | `pkg/milvus_client.py` | `get_client()`, `get_collection_name()`, `is_configured()` | Milvus 客户端 |
| **MinIO 客户端** | `pkg/minio_client.py` | `get_client()`, `get_bucket_docs()`, `get_bucket_audit()`, `build_object_name()` | MinIO 对象存储客户端 |

---

## 前端模块

**位置**：`frontend/src/`

### API 封装

**位置**：`frontend/src/api/`

对后端 `/api/v1` 的封装。

| 文件 | 主要方法 | 说明 |
|-----|---------|------|
| `auth.ts` | `login()`, `getMe()`, `changePassword()`, `updateMe()` | 用户认证 |
| `chat.ts` | `chat()`, `chatStream()` | 多轮对话（非流式/流式） |
| `compare.ts` | `compare()` | 产品对比 |
| `recommend.ts` | `recommend()` | 产品推荐 |
| `report.ts` | `generateReport()` | 报告生成 |
| `evidence.ts` | `getEvidence()` | 引用证据查询 |
| `feedback.ts` | `postFeedback()` | 反馈提交 |
| `products.ts` | `searchProducts()` | 产品搜索 |
| `rbac.ts` | `listRoles()`, `upsertRole()`, `listMenus()`, `upsertMenu()`, `setUserRoles()`, `setRoleMenus()`, `listUserMenus()` | RBAC 管理 |
| `models.ts` | `listModels()`, `upsertModel()`, `deleteModel()`, `testModel()` | 模型配置管理 |
| `agents.ts` | `listAgents()`, `getAgent()`, `upsertAgent()`, `deleteAgent()` | Agent 配置管理 |
| `skills.ts` | `listSkills()`, `getSkill()`, `upsertSkill()`, `deleteSkill()` | Skill 配置管理 |
| `config.ts` | `getExternalKBConfig()`, `updateExternalKBConfig()` | 外部知识库配置 |
| `knowledge.ts` | `externalKnowledgeQuery()`, `knowledgeChat()` | 知识库查询/对话 |
| `user.ts` | `listUsers()`, `createUser()`, `updateUser()`, `deleteUser()` | 用户管理 |

### 页面视图

**位置**：`frontend/src/views/`

| 目录 | 说明 |
|-----|------|
| `views/home/` | 首页 |
| `views/login/` | 登录页 |
| `views/fpai/` | 金融产品解析智能体主界面（对话、对比、推荐、报告） |
| `views/admin/` | 管理后台（用户、角色、菜单、模型、Agent、Skill、知识库） |

### 工具函数

**位置**：`frontend/src/utils/`

| 文件 | 说明 |
|-----|------|
| `request.ts` | HTTP 请求封装（axios） |
| `storage.ts` | 本地存储封装（localStorage/sessionStorage） |
| `crypto.ts` | 加密工具（密码加密） |
| `theme.ts` | 主题切换 |

### 状态管理

**位置**：`frontend/src/store/`

| 文件 | 说明 |
|-----|------|
| `user.ts` | 用户状态（登录信息、权限） |
| `theme.ts` | 主题状态 |

---

## 快速查找示例

### 场景 1：修改产品对比功能

1. **后端逻辑**：`backend/agents/fund_agent/product_compare/agent.py` → `ProductCompareAgent.run()`
2. **API 路由**：`backend/api/routes/compare_recommend_report.py` → `compare()`
3. **前端调用**：`frontend/src/api/compare.ts` → `compare()`
4. **前端页面**：`frontend/src/views/fpai/` 中的对比页面

### 场景 2：修改用户登录逻辑

1. **后端认证**：`backend/auth/service.py` → `verify_password()`, `create_token()`
2. **API 路由**：`backend/api/routes/auth.py` → `auth_login()`
3. **前端调用**：`frontend/src/api/auth.ts` → `login()`
4. **前端页面**：`frontend/src/views/login/`

### 场景 3：修改检索服务

1. **检索逻辑**：`backend/retrieval/service.py` → `retrieve()`, `generate_answer()`
2. **Milvus 客户端**：`backend/pkg/milvus_client.py` → `get_client()`
3. **Embedding 调用**：`backend/model_gateway/embedding.py` → `embed()`
4. **Reranker 调用**：`backend/model_gateway/reranker.py` → `rerank()`

### 场景 4：修改合规审查

1. **合规服务**：`backend/compliance/service.py` → `check_input()`, `check_output()`
2. **合规策略**：`backend/compliance/config.py` → `CompliancePolicy`
3. **调用位置**：`backend/orchestrator/run.py` → `_ensure_compliance_and_audit()`

### 场景 5：修改 RBAC 权限

1. **后端存储**：`backend/rbac/store.py` → `get_user_roles()`, `set_user_roles()`, `list_user_menus()`
2. **API 路由**：`backend/api/routes/rbac.py` → `list_roles()`, `set_user_roles()`, `list_user_menus()`
3. **前端调用**：`frontend/src/api/rbac.ts` → `listRoles()`, `setUserRoles()`, `listUserMenus()`
4. **前端页面**：`frontend/src/views/admin/` 中的角色/菜单管理页面

---

## 更新说明

本文档应在以下情况更新：

1. ✅ 新增模块/智能体/API 端点时
2. ✅ 重构导致文件路径变化时
3. ✅ 核心类/方法重命名时
4. ✅ 新增重要的工具函数/服务时

**维护原则**：保持文档简洁，只记录"在哪里"和"是什么"，不记录"怎么做"（详细实现看代码注释）。

---

**最后更新**：2025-01-XX（由 AI 自动生成）
