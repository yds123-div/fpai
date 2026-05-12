# Graph Report - d:\hjjk\fpai  (2026-05-11)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1290 nodes · 2486 edges · 62 communities (58 shown, 4 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 413 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a7efaf84`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]

## God Nodes (most connected - your core abstractions)
1. `envelope()` - 64 edges
2. `get_connection()` - 62 edges
3. `run()` - 52 edges
4. `message_for()` - 43 edges
5. `service` - 35 edges
6. `_ensure_tables()` - 32 edges
7. `ErrorCode` - 27 edges
8. `_forbidden()` - 26 edges
9. `_is_admin()` - 24 edges
10. `build_single_output()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `get_connection()`  [INFERRED]
  standalone_fetch_test.py → backend/pkg/mysql_client.py
- `获取外部知识库配置。          返回格式：     {       "base_url": "http://localhost:8080",` --rationale_for--> `updateExternalKBConfig()`  [EXTRACTED]
  backend/api/routes/config.py → frontend/src/api/config.ts
- `ExternalKBConfig` --uses--> `ErrorCode`  [INFERRED]
  frontend/src/api/config.ts → backend/pkg/codes.py
- `main()` --calls--> `load_dotenv()`  [EXTRACTED]
  standalone_fetch_test.py → tools/run_graphify_extract_and_viewer.py
- `products` --rationale_for--> `_has_strong_product_intent()`  [EXTRACTED]
  frontend/src/views/fpai/ProductsView.vue → backend/agents/fund_agent_framework.py

## Communities (62 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (57): onDone(), [], ex, lines, m, showDebug, fundCode, signature (+49 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (29): AgentMetrics, AkShareMetrics, Counter, get_agent_metrics(), get_akshare_metrics(), Histogram, monitor_agent_execution(), monitor_akshare_api() (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (54): 从 model_gateway.config 读取 LLM 配置，按 base_url / api_key 创建 AgentScope ChatModel。, CompliancePolicy, 合规策略与黑白名单配置。  一期为内存配置，支持从环境变量或代码中注入；T014 config 模块可后续从 MySQL/配置文件加载。, 合规策略：黑白名单与审查开关。      - blacklist_keywords: 命中即触发拒答或复核（按策略可配置为 reject/review）, 返回命中的黑名单词（已转小写），空列表表示未命中。, 若文本包含白名单短语则视为放行（用于减少误拦）。, Exception, _answer_via_agentscope() (+46 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (58): _llm_call_maybe_stream(), 从 agent_profiles 读取 skill_keys（JSON 数组字符串或空）。     返回：     - None：未配置/不可用, 统一的 LLM 调用：     - 若 API 层提供了 stream_callback 且当前轮模型配置有 base_url：走 OpenAI 兼容流式，边, 从 agent_profiles 读取配置覆盖：     - system_prompt：覆盖默认 system prompt（仅当非空）     - mo, resolve_agent_overrides(), resolve_agent_skill_keys(), _build_query_candidates(), _extract_name_keywords() (+50 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (58): next, _achievement_val_pct(), _build_basic_card(), build_compare_output(), _build_fee_card(), _build_fetch_failure_sections(), _build_performance_card(), build_single_output() (+50 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (55): 将文本切分为若干 chunk，尽量在段落边界切分，超长段落按 chunk_size 滑动窗口。      Args:         text: 全文。, 移除模型可能输出的 <think>...</think> 等思考过程，避免前端展示。     注意：仅做展示层清洗，不改变业务事实。, append_message(), _default_context(), delete_user_session(), _ensure_session_in_mysql(), get_recent_messages(), get_session_context_for_orchestration() (+47 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (41): ChatStreamCallbacks, DeleteSessionData, getAuthHeader(), postChatStream(), SessionListData, SessionListItem, SessionMessageItem, SessionMessagesData (+33 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (40): payload, deleteKnowledgeBaseSyncRecord(), ExternalKnowledgeItem, ExternalKnowledgeRequest, externalKnowledgeSearch(), KnowledgeBaseOption, postKnowledgeChatStream(), syncKnowledgeBases() (+32 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (35): build_http_fetcher(), DataSourceConfig, load_from_mysql(), load_from_mysql_and_register(), _parse_json(), T010a：从 MySQL 加载领域模型与数据源配置，构建 HTTP Fetcher 并注册，供 get_data 使用。 见 docs/领域模型与API适配, 从 MySQL domain_models、domain_model_fields、data_sources 表加载配置。     org_id 为 None, 从 MySQL 加载领域模型与数据源并注册到 model_registry；返回注册数量。 (+27 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (40): add_auth_middleware(), add_trace_id_middleware(), _get_bearer_token(), _is_public_path(), API 中间件：请求 ID 与 traceId 绑定、响应头回传；鉴权（Bearer Token → userId/role/productPoolIds）。, 判断当前请求是否能匹配到任一路由（用于避免“未登录访问不存在路径”被误判为 401）。, 从请求头读取 X-Request-Id 作为 traceId，未传则生成 UUID；     绑定到当前请求上下文，并在响应头回传同一值。, 鉴权中间件：对 /api/v1 下除 /api/v1/auth/login、/api/v1 外的请求校验 Bearer Token，     解析后注入 re (+32 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (24): get_akshare_config(), load_akshare_config(), AkShare 配置类。          使用 Pydantic 进行配置验证和类型检查。, 获取全局 AkShare 配置实例（单例模式）。          Returns:         AkShareConfig 实例, _filter_nav_records_by_period(), AkShare 数据获取客户端。  封装 AkShare API 调用，提供统一的数据访问接口。 特性： - 重试机制：失败时重试 3 次，指数退避 - 限流机, 获取缓存统计信息。                  Returns:             包含缓存统计信息的字典：             {, 清空缓存。                  清空所有缓存数据，但保留缓存统计信息。                  Example: (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (42): AgentUpsertBody, ModelUpsertBody, SkillUpsertBody, get_user_by_id(), 按 users.id 查询用户信息（不含密码）；不存在返回 None。, BaseModel, IntEnum, ErrorCode (+34 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (33): append_event(), export_report(), list_answer_ids_for_retention(), 审计存储：热数据 MySQL（audit_index + audit_events），冷数据 MinIO；保留 6 个月、按条件导出。, 返回 created_at 早于 older_than_days 天的 answer_id 列表，供归档或清理。, 按条件导出审计报告：时间范围、用户、会话、answer_id；返回证据列表（含 events）。, 追加审计事件；若该 answer_id 在 audit_index 尚无记录则插入索引行（用传入的 session_id/user_id 等）。, clear_config_cache() (+25 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (28): _build_faq_context(), faq_query(), query_faq(), 在 FAQ 知识库中检索并回答（检索 TopK → AgentScope 返回答案），包装为 ToolResponse。     供 toolkit.regi, 将 TopK FAQ 拼成给 AgentScope 的上下文。, 1）检索层 TopK 相似 FAQ；2）初始化 AgentScope 调用返回答案。     无 AgentScope/模型配置时回退 model_gatew, FAQ 检索层：query → Embedding → Milvus TopK 相似 → 回表 MySQL 取 answer → 返回 FAQHit 列表。, 向量检索 TopK 相似 FAQ：query 向量化 → Milvus fpai_faq 检索 → 按 doc_id 回表 MySQL 取完整 FAQ。 (+20 more)

### Community 14 - "Community 14"
Cohesion: 0.23
Nodes (27): createAgent(), deleteAgent(), updateAgent(), deleteSession(), updateExternalKBConfig(), getRoleMenus(), getUserRoles(), listMenus() (+19 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (26): _cache_get(), _cache_invalidate(), 新增/更新 agent_profile（按 agent_key upsert）。, 将当前代码内置的业务 agent 预置到 agent_profiles，便于“Agent 管理”页面直接编辑。     - 若记录不存在则创建     - 若记, _seed_builtin_agents(), soft_delete_agent(), upsert_agent(), 预置当前代码内置 skills。     - 不存在则插入     - 已存在但 module_path 为空时补齐（不覆盖管理员修改） (+18 more)

### Community 16 - "Community 16"
Cohesion: 0.13
Nodes (26): _extract_codes_from_planner_skill_payload(), _extract_codes_from_text(), _extract_json_object(), _extract_name_code_pairs_from_planner_skill_payload(), _has_strong_product_intent(), _heuristic_classify(), _is_simple_planning_fast_path_candidate(), _looks_like_kb_explainer_query() (+18 more)

### Community 17 - "Community 17"
Cohesion: 0.1
Nodes (13): build_toolkit_from_registry(), get_all_entries(), get_entries_by_intent(), _load_entries_from_config(), 从 config（T014）读取扩展注册项；config_key=agent_registry，结构为 list of {id, name, intent_ke, 按意图关键词过滤注册项（用于缩小候选工具集）。, 根据注册表构建 AgentScope Toolkit，逐条注册入口函数。      Args:         entries: 若为 None 则使用, 解析 entry_loader 得到实际可注册的入口（异步工具函数）。 (+5 more)

### Community 18 - "Community 18"
Cohesion: 0.11
Nodes (14): changePassword(), getUserInfo(), login(), LoginParams, LoginResponse, logout(), updateCurrentUser(), UserInfo (+6 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (22): issue_token(), 签发 JWT；payload 含 sub=user_id、exp、iat。     未配置 JWT_SECRET 或未安装 pyjwt 时返回空字符串。, check_input(), check_output(), _llm_input_check(), _llm_output_check(), _parse_llm_decision(), 合规服务：输入审查 checkInput、输出审查 checkOutput（统一大模型审查）。  策略与黑白名单前置；LLM 审查作为统一流程，返回通过/拒答/ (+14 more)

### Community 20 - "Community 20"
Cohesion: 0.23
Nodes (17): CoordinatorAgent, FundAgentRouter, IntentClassifierAgent, 意图识别 Agent（框架版）。      当前策略：     - 先启发式分类（确保稳定）     - 若后续你提供提示词/工具调用，可改为强制走 LLM 分, 总控/规划 Agent（方式1）：负责识别多子任务并输出结构化 plan。     - 使用 llm_chat（优先走 AgentScope ChatModel, 基金业务 Agent 路由器：先分类，再路由到四个业务 Agent。, BaseBusinessAgent, AgentRunContext (+9 more)

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (19): ChatTurnResult, _ensure_compliance_and_audit(), _format_multi_task_response(), _infer_model_provider(), 写入审计事件（意图、合规输入/输出、回复摘要）；返回 compliance 字段用 dict。, 执行一轮对话编排：意图与槽位抽取 → 注入 AgentScope → ReAct+Toolkit 执行 → 合规审查 → 审计落库。      Args:, 直接格式化拼接多任务结果，不调用LLM合并。          格式：【子问题：xxx】\n回答内容\n\n【子问题：yyy】\n回答内容      Args:, 同步封装：asyncio.run(run_chat_turn_async(...))。 (+11 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (16): getUserMenus(), MenuItem, route, commonIcons, fetchUserMenus(), menuCode, pathSegments, router (+8 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (18): 输入审查：防提示注入、越权、敏感请求等。      - 先做黑名单规则匹配，命中且未白名单则拒答。     - 若策略启用且 LLM 可用，再经大模型审查；否则, FAQ 问答智能体：检索层 TopK 相似 FAQ → 初始化 AgentScope 调用返回答案。  逻辑：1）检索层 search_faq(questi, _is_chitchat(), 轻量闲聊识别：命中问候/客套词就认为是闲聊。     仅当输入不包含 6 位基金代码时才短路，避免误伤产品问题。, _compact_supplier_data_for_prompt(), _parse_filters(), product_list_query(), query_product_list() (+10 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (18): getSessionMessages(), postFeedback(), 提交反馈并落库；rating 须为 useful / not_useful / inaccurate。     返回是否落库成功。, submit_feedback(), create_session(), 创建会话：写入 MySQL sessions 表，并初始化 Redis session:{id} 上下文（user_id、product_ids、custome, _permission_context(), get_session_detail() (+10 more)

### Community 25 - "Community 25"
Cohesion: 0.18
Nodes (17): RmCustomer, RmCustomerLevel, RmRiskPreference, RmTodo, RmTodoPriority, RmTodoSource, RmTodoStatus, addRmTodo() (+9 more)

### Community 26 - "Community 26"
Cohesion: 0.12
Nodes (17): ExternalKBConfig, delete_knowledge_base(), 删除本地 knowledge_bases 表中的单条映射记录。      注意：这里只删除本地同步结果（uuid/name 映射），不会触碰外部知识库源数据。, 获取外部知识库配置。          返回格式：     {       "base_url": "http://localhost:8080",, delete_base(), _external_kb_search(), external_search(), knowledge_chat_stream() (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.16
Nodes (13): postReportGenerate(), parseAndValidateCodes(), productIdsText, streamText, comment, successMsg, errorMsg, onSubmit() (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.15
Nodes (17): 是否已配置 Milvus（有 MILVUS_HOST 或默认 localhost）。, 返回单例 MilvusClient；未安装 pymilvus 或连接失败时返回 None。, _uri(), _client_params(), get_client(), get_object(), is_configured(), put_object() (+9 more)

### Community 29 - "Community 29"
Cohesion: 0.13
Nodes (14): AuditEvent, Evidence, 审计证据与事件类型，与 technical_design §3.3、GET /api/v1/evidence/{answerId} 契约一致。, 按 answerId 查询得到的证据：请求摘要、意图、数据源、检索证据片段、模型/策略版本、操作人、时间戳。     与 GET /api/v1/eviden, 合规审查结果类型：通过/拒答/改写/补充提示。  与 technical_design §3.3 Orchestrator → Compliance 及 a, 转为可序列化 dict，供 API 的 compliance 字段使用。, FeedbackRecord, 反馈类型：与 technical_design §2.3 POST /api/v1/feedback 及 MySQL feedback 表一致。 (+6 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (15): getProductsSearch(), ProductsSearchResult, ProductsSyncResult, syncFundProducts(), columns, keyword, loadProducts(), onSearch() (+7 more)

### Community 31 - "Community 31"
Cohesion: 0.2
Nodes (11): extract_ip_hint(), looks_html(), main(), 完全独立的抓取测试脚本（不依赖本项目任何模块）。  用途：   验证关键数据源是否被拒绝/重定向/notfound/返回 HTML 或返回不完整 JSON, Req, snip(), build_vis_payload(), _js_safe() (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.17
Nodes (12): _envelope_response(), http_exception_handler(), _http_status_to_error_code(), FastAPI 应用入口（占位）。  从 backend 目录启动：   uvicorn api.main:app --reload --port 800, 开发时可直接 python -m api.main，端口由环境变量 PORT 指定（默认 8000）。, 将 HTTP 状态码映射为业务错误码（用于 envelope）。, 将 HTTPException 转为统一 envelope 响应（HTTP 200 + body.code）。, 将请求体验证错误转为 40001 + 校验详情。 (+4 more)

### Community 33 - "Community 33"
Cohesion: 0.22
Nodes (13): 将 MySQL 中生效期内的 FAQ 同步到 Milvus：对 question 做 Embedding，写入 fpai_faq。     先删除该 coll, sync_faq_to_milvus(), process_one_task(), 从队列取一条任务并处理：解析 → 分块 → 向量化 → 写 Milvus。      Returns:         True 表示处理了一条任务；Fa, delete_by_filter(), ensure_collection(), get_collection_name(), insert_chunks() (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (8): AgentProfile, AgentType, testExternalKBConnection(), SkillProfile, 测试外部知识库连接。          使用当前保存的配置（或环境变量）尝试调用外部知识库的健康检查接口。, Config, ApiResponse, requestWrapper

### Community 35 - "Community 35"
Cohesion: 0.15
Nodes (10): pop_task(), push_task(), 将一条文档任务投递到队列。content 以 base64 存入 JSON 负载。      Returns:         是否投递成功（Redis, 从队列取出一条任务（BRPOP，阻塞等待）。      Returns:         解析后的任务 dict（含 doc_id, source, pe, 从任务负载中解码 content bytes。, task_content_from_payload(), 将文档投递到 ingestion 队列，异步由 Worker 解析并写入 Milvus。      Args:         content: 文件二进, submit_document() (+2 more)

### Community 36 - "Community 36"
Cohesion: 0.18
Nodes (8): AiModelItem, listModels(), ModelSource, upsertModel(), delete_model(), 新增/更新模型。若 payload 含 id 则更新，否则新增。     返回 id，失败返回 None。, 连接测试：     - Ollama：GET {base_url}/api/tags     - Remote(OpenAI兼容)：POST {base_u, test_connection()

### Community 37 - "Community 37"
Cohesion: 0.17
Nodes (12): get_password_hash_by_user_id(), hash_password_from_digest(), 按 users.id 查询 password_hash；不存在或未配置返回 None。用于修改密码时校验旧密码。, 更新指定用户的 password_hash。成功返回 True。, 将已是 SHA256(明文).hex 的字符串用 bcrypt 哈希后存储。     用于当前用户修改密码时，前端传入 new_password 为 SHA25, 校验「待校验值」与存储哈希是否匹配。     plain: 前端登录时发送的 SHA256(明文).hex；     hashed: 经 hash_passwo, 按账号与密码校验用户；成功返回用户记录，失败返回 None。, update_user_password_hash() (+4 more)

### Community 38 - "Community 38"
Cohesion: 0.33
Nodes (7): _connection_impl(), _connection_params(), _ConnectionPool, _get_pool(), _pool_size(), MySQL 连接/会话封装，供会话、消息、配置、FAQ、反馈、审计等模块复用。  从环境变量读取：MYSQL_HOST、MYSQL_PORT、MYSQL_U, 简单线程安全连接池：空闲队列 + 在用集合，不超过 max_size。

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (10): checkEnvelope(), createUser(), deleteUser(), getUserDetail(), getUsersList(), updateUser(), _find_unique_conflict(), 新增用户；account、name、email、employee_no 均须唯一（非空时校验）。 (+2 more)

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (6): ComplianceAction, Enum, Rating, 反馈评级：useful / not_useful / inaccurate。, 统一错误码枚举，与 API 契约一致。  约定：0 成功；4xx 客户端（参数/鉴权/限流）；5xx 服务端； 业务子码与合规子码可在本模块扩展或由 de, str

### Community 41 - "Community 41"
Cohesion: 0.33
Nodes (5): FundNavByPeriodResponse, FundNavChartData, FundNavPeriod, getFundNavByPeriod(), _lock_for_symbol()

### Community 42 - "Community 42"
Cohesion: 0.33
Nodes (6): close_client(), 释放 MinIO 客户端，用于测试或进程退出。, is_available(), Redis 客户端封装，供会话上下文、缓存、限流、幂等等模块复用。  支持从 REDIS_URL 解析或从 REDIS_HOST/PORT/PASSWORD/D, 关闭全局 Redis 客户端与连接池，用于进程退出或测试清理。, _redis_url()

### Community 43 - "Community 43"
Cohesion: 0.33
Nodes (7): archive_to_cold(), _ensure_audit_bucket(), 将某 answer_id 的热事件归档到 MinIO，更新 audit_index.cold_ref，并删除 audit_events 对应行。, build_object_name(), ensure_bucket(), get_bucket_audit(), 按 technical_design §4.4 路径规范生成对象名：tenant/type/year-month/doc_id。     便于按租户、类型、时

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (7): resetUserPassword(), hash_password(), 将明文密码哈希为存储格式；用于注册或种子数据。     与前端约定：前端登录时发送 SHA256(明文).hex，此处存储 bcrypt(SHA256(明文)., 重置用户密码（明文）；经 hash_password 后更新。成功返回 True。, _sha256_hex(), 重置用户密码（明文传入，后端 bcrypt(SHA256) 后更新）。, users_reset_password()

### Community 45 - "Community 45"
Cohesion: 0.47
Nodes (5): AuthContext, get_auth_context(), get_current_user_id(), 从 request.state 读取当前用户 ID（鉴权中间件已注入）。     仅用于已受鉴权保护的路径；未认证时由中间件直接返回，不会执行到依赖。, 返回当前请求的鉴权上下文（user_id、role、product_pool_ids）。

### Community 46 - "Community 46"
Cohesion: 0.53
Nodes (4): get_evidence(), 按 answerId 查询证据：热数据从 MySQL 读索引 + 事件；若存在 cold_ref 则从 MinIO 拉取冷数据合并。, answerId, onQuery()

### Community 47 - "Community 47"
Cohesion: 0.4
Nodes (4): _get_embedding_dimension(), 循环消费队列；once=True 时只处理一条后退出。, 通过 embed 单条短文本获取向量维度；未配置时返回 None。, run_worker()

### Community 48 - "Community 48"
Cohesion: 0.5
Nodes (4): _emit_progress(), 按顺序尝试执行 skills，返回第一个成功的 payload（dict）。     约定：     - 每个 skill 模块需提供 async run(, run_configured_skills(), _safe_json_loads()

### Community 49 - "Community 49"
Cohesion: 0.5
Nodes (4): list_users_paginated(), 将 users 表一行转为不含 password_hash 的 user 字典。, 分页查询用户列表（不含 password_hash）。     返回 (items, total)。, _row_to_user()

## Knowledge Gaps
- **443 isolated node(s):** `完全独立的抓取测试脚本（不依赖本项目任何模块）。  用途：   验证关键数据源是否被拒绝/重定向/notfound/返回 HTML 或返回不完整 JSON`, `将当前代码内置的业务 agent 预置到 agent_profiles，便于“Agent 管理”页面直接编辑。     - 若记录不存在则创建     - 若记`, `新增/更新 agent_profile（按 agent_key upsert）。`, `解析 Coordinator 输出（预期 JSON）。     期望：     {       "multi": true/false,       "task`, `从模型输出中尽量提取 JSON object 字符串：     - 先去掉 <think>...</think>     - 支持 ```json ... ``` (+438 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run()` connect `Community 3` to `Community 4`, `Community 13`, `Community 48`, `Community 20`, `Community 21`, `Community 23`, `Community 26`?**
  _High betweenness centrality (0.196) - this node is a cross-community bridge._
- **Why does `get_connection()` connect `Community 15` to `Community 36`, `Community 37`, `Community 5`, `Community 38`, `Community 8`, `Community 39`, `Community 43`, `Community 12`, `Community 11`, `Community 46`, `Community 14`, `Community 44`, `Community 49`, `Community 24`, `Community 26`, `Community 31`?**
  _High betweenness centrality (0.187) - this node is a cross-community bridge._
- **Why does `envelope()` connect `Community 14` to `Community 32`, `Community 34`, `Community 35`, `Community 36`, `Community 37`, `Community 6`, `Community 5`, `Community 39`, `Community 9`, `Community 40`, `Community 11`, `Community 44`, `Community 41`, `Community 46`, `Community 15`, `Community 50`, `Community 24`, `Community 26`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Are the 62 inferred relationships involving `envelope()` (e.g. with `report_generate_query()` and `_envelope_response()`) actually correct?**
  _`envelope()` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 59 inferred relationships involving `get_connection()` (e.g. with `main()` and `_seed_builtin_agents()`) actually correct?**
  _`get_connection()` has 59 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `run()` (e.g. with `resolve_agent_overrides()` and `resolve_agent_skill_keys()`) actually correct?**
  _`run()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `message_for()` (e.g. with `report_generate_query()` and `http_exception_handler()`) actually correct?**
  _`message_for()` has 41 INFERRED edges - model-reasoned connections that need verification._