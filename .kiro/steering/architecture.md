---
description: 架构规则与设计约束
inclusion: auto
---

# 架构规则与设计约束

## 架构风格

一期采用**模块化单体 + 异步 Worker**，全内网私有化部署。

- 模块边界清晰，禁止反向依赖与循环依赖
- 依赖方向：`api` → `orchestrator` → `agents`、`retrieval`、`data_access`、`compliance`、`audit`
- `agents` 依赖 `retrieval`、`data_access`、`model_gateway`
- `ingestion` 依赖 `parsing`、`model_gateway`、队列、Milvus、MinIO

## 编排约定（当前主链路）

- 聊天主链路：`FundAgentRouter + Coordinator` 任务规划 → 按任务类型路由到业务 Agent
- 多任务场景支持并行执行与结果融合
- 历史 AgentScope 方案已被替代，不作为当前约束

## 核心设计约束

### 合规（强约束）
- 所有用户可见输出必须经过 Compliance 输入/输出审查
- 合规策略支持版本管理、灰度发布与快速回滚
- 审计记录每次调用的意图、实际被调用的能力、数据源与证据

### 权限贯穿检索链路
- 检索与数据访问调用必须携带权限上下文（userId、role、productPoolIds）
- 支持"检索前过滤（优先）"+ "检索后强过滤（兜底）"
- 过滤结果写入审计事件

### 可追溯
- 每次回答可回放：数据源、检索 chunk、策略与模型版本、操作者
- 引用展示与审计共用同一证据对象（answerId 关联）

### 性能目标
- 关键交互 P95 ≤ 5s
- 抓手：并行化（数据查询+检索）、热点缓存、降级（外部源不可用时回退内部知识库）、超时与熔断

## 数据存储分工

| 存储 | 用途 |
|------|------|
| MySQL | 会话/消息、配置与策略、FAQ、反馈、审计索引（热） |
| Redis | 会话上下文缓存、热点产品要素缓存、检索结果缓存、限流/幂等 |
| Milvus | chunk 向量 + 元数据（来源、权限、时间、标签） |
| MinIO | 原始文档、解析中间产物、审计冷数据归档 |

## 流式协议（SSE）

当前 SSE 事件类型（按顺序）：
1. `message_start` - 本轮回答开始（含 sessionId/answerId）
2. `status` - 阶段进度（accepted/planning/generating/compliance）
3. `message_delta` - 正文增量 token
4. `structured_update` - 结构化结果提前推送
5. `citation` - 引用片段
6. `done` - 结束（含 answerId、trace、suggestedQuestions、structuredOutputs 兜底）
7. `error` - 错误（含 code、message）

**兼容约定**：即使已推送 `structured_update`，`done` 中仍回传 `structuredOutputs[]` 作为兜底。

## 业务数据访问层（多机构适配）

- 对上游（编排、智能体）只暴露**统一领域模型与接口**
- 各机构 API 差异由**适配器**吸收，不向上暴露
- 产品搜索采用双通道：本地产品库优先，未命中时回退 `data_access` 统一接口
- 权限过滤、缓存、熔断在统一层完成

## 禁止事项

- 禁止反向依赖与循环依赖
- 禁止硬编码密钥、证书、内网地址（使用环境变量）
- 禁止将敏感明文（客户信息、受限内容）写入日志与监控
- 禁止直连公网服务（全内网私有化部署）
- 禁止业务 Agent 直接对接各机构原始 API（必须通过 data_access 统一层）
