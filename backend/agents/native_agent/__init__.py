# -*- coding: utf-8 -*-
"""T6 (#24)：原生 ReActAgent 装配 + M1-M5 安全机制 + structured_outputs collector。

本包装配 AgentScope 2.0 原生 ``Agent``（ReActAgent），把 T2（sys_prompt 文件库）、
T4（GatewayChatModel）、T5（取数 Toolkit + ALLOW 权限规则）三块产出组装成新链路核心，
并以五项原生机制（M1-M5）重表达栅栏 #2 安全意图（SI-1~12，见
``docs/migration/fence2-safety-checklist.md``）。

- ``assembly.build_fund_agent``：装配 ``Agent``（sys_prompt + GatewayChatModel(stream=True) +
  Toolkit + AgentState(permission_context) + ReActConfig(max_iters=8) + collector 中间件 +
  T7 AuditMiddleware）。
- ``structured_collector``：``on_acting`` 中间件攥取数 payload，回复后按取数形状跑
  ``build_single_output``（单只/榜单）/ ``build_compare_output``（多只对比），
  不走 ``generate_structured_output``。
- ``audit_middleware``（T7 #25，栅栏 #4）：``AuditMiddleware`` 把 agent 事件流桥接到
  ``audit.append_event``（两层事件 tool_call / reply_outcome + model_call_error），
  不动 audit 持久化契约；``answer_id`` 经 contextvars 线程化。
- ``shape_adapter``（T8 #26，栅栏 #6）：``ShapeAdapter`` 把 ``reply_stream`` 事件流
  适配为既有 ``progress_callback`` / ``stream_callback`` 契约（保形，不改前端 SSE）--
  5 核心阶段全命中 + token 分片（首 token 先发 ``model_first_token``）+ ``ihad`` 透传/剥离
  + ``reset_tools`` 噪音过滤 + 双 provider（OpenAI 兼容 / DashScope）保形。
  主 seam ``run_chat_turn_async`` 接线在 T10。
"""
