# 功能导航文档

> 本文档是项目的"功能地图"，帮助 AI 快速定位已有功能的位置，避免全项目搜索。
> 

## 0. 当前实现基线（as-is）

- **聊天编排主链路**：`FundAgentRouter + Coordinator`（任务规划、路由、并行执行、结果融合）。
- **SSE 事件契约**：`message_start`、`message_delta`、`status`、`structured_update`、`citation`、`done`、`error`。
- **聊天结构化结果**：`structuredOutputs[]` 在非流式与 SSE `done` 透传。
- **产品搜索链路**：本地产品库优先，未命中回退 `data_access.get_data(model_code=products, ...)`。
- **会话恢复现状**：主要依赖消息 `content_summary`，结构化结果完整持久化待补齐。

## 1. 核心后端模块索引

- `backend/api/routes/chat.py`
  - `POST /api/v1/chat` 主入口（流式/非流式）
  - SSE 事件发射与会话上下文写回
  - `structuredOutputs[]` 透传与 `done` 兜底

- `backend/orchestrator/run.py`
  - `run_chat_turn_async()` 编排主流程
  - Coordinator 任务规划、路由执行、多任务并行融合
  - 输入/输出合规审查与审计落库对接

- `backend/api/routes/evidence_feedback_products_sessions.py`
  - `GET /products/search`（本地库优先 + data_access 回退）
  - evidence / feedback / sessions 路由聚合

## 2. 核心前端模块索引

- `frontend/src/api/chat.ts`
  - SSE 事件消费（`message_delta`、`status`、`structured_update`、`done`）
  - 流式连接与中断控制

- `frontend/src/views/fpai/ChatView.vue`
  - 聊天页渲染、思考过程折叠展示
  - `structuredOutputs` 解析与结构化组件渲染
  - 会话恢复（基于 `/sessions/{id}/messages`）

- `frontend/src/utils/fundAnalysisParser.ts`
  - 基金分析结构化输出解析
  - 与聊天渲染组件的数据结构适配

## 3. 测试与回归定位

- `tests/test_chat_sse_events.py`
  - 校验 SSE 事件顺序与 `structured_update` / `done` 协议一致性

- `tests/test_chat_api.py`
  - chat 基本契约与主流程回归

## 4. Memory 文档映射（先读顺序）

- 架构总览：`.cursor/memory/architecture.md`
- 技术细节：`.cursor/memory/technical_design.md`
- 决策记录：`.cursor/memory/decisions.md`
- 项目上下文：`.cursor/memory/project_context.md`
- 任务状态：`.cursor/memory/tasks.md`

## 5. 同步维护规则

- 当聊天编排、SSE 事件、产品搜索、会话恢复策略发生变更时，需同步更新：
  - `.cursor/memory/architecture.md`
  - `.cursor/memory/technical_design.md`
  - `.cursor/memory/decisions.md`
  - 本文件（`module_index.md`）
