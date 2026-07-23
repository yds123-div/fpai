# E3 原型笔记：流式/SSE/进度保形（栅栏 #6）

- 工单：[#12 E3：流式/SSE/进度保形原型](https://github.com/yds123-div/fpai/issues/12)
- 分支：`worktree-e3-streaming-prototype`
- 日期：2026-07-23
- 原型代码：`backend/prototype/e3_streaming/`
- 依赖：R1（#3，原生原语清单）、G1（#4，GatewayChatModel 决策）

## 0. 结论

**栅栏 #6 流式/SSE/进度回调可以原生保形。** 用原生 `Agent.reply_stream` 的事件流，
经一层 `ShapeAdapter` 映射，可完整复刻现有 `progress_callback(stage)` + `stream_callback(token)` 契约，
且 token 粒度更细、推理通道更干净。已在真实模型端点（LLM_BASE_URL）跑通基金查询。

## 1. 现有契约（须保形）

来源：`agents/fund_agent/runtime.py`、`orchestrator/run.py`、`api/routes/chat.py`。

| 回调 | 签名 | 语义 |
|---|---|---|
| `progress_callback` | `(stage: str, **kwargs)` sync/async | 离散阶段：accepted / thinking / planning_* / skill_fetching / llm_generating / model_first_token / done |
| `stream_callback` | `(token_text: str)` sync/async | token 级文本增量，拼接即最终回答 |
| `show_thinking` | bool | True 透传 `<think>...</think>`；False 剥离 |
| `llm_chat_stream` | `AsyncGenerator[str]` | 独立 httpx SSE，剥离 `<think>` 的状态机 |

SSE 层（`chat.py`）把 `progress_callback` -> SSE `progress` 事件，`stream_callback` -> SSE `message_delta:{text}`。

## 2. 原生事件 -> 现有契约 映射（ShapeAdapter 实现）

`Agent.reply_stream` yield `AgentEvent`，映射如下（`backend/prototype/e3_streaming/shape_adapter.py`）：

| 原生事件 | 现有契约映射 |
|---|---|
| `ReplyStartEvent` | `progress("thinking")` |
| `ToolCallStartEvent` | `progress("skill_fetching", tool=name)` |
| `ToolResultStartEvent` | `progress("skill_fetching", tool=name, phase="result")` |
| `ModelCallStartEvent` | `progress("llm_generating")` |
| `TextBlockDeltaEvent.delta` | 首个先 `progress("model_first_token")`；每个 -> `stream_callback(delta)` |
| `ThinkingBlockStartEvent` | `show_thinking` 时 `stream_callback("<think>")` |
| `ThinkingBlockDeltaEvent.delta` | `show_thinking` 时 `stream_callback(delta)`（原始，不包） |
| `ThinkingBlockEndEvent` | `show_thinking` 时 `stream_callback("</think>")` |
| `ReplyEndEvent` | `progress("done")` |
| `RequireUserConfirmEvent` | `progress("awaiting_confirm")`（HITL 暂停，现有契约无直接对应） |
| `ExceedMaxItersEvent` | `progress("exceed_max_iters")` |

## 3. 跑通验证

### 3.1 真实模型（LLM_BASE_URL 端点）

`python -m prototype.e3_streaming.run_prototype`（无 `--stub`）：

```
progress: accepted -> thinking -> llm_generating -> skill_fetching(reset_tools)
  -> llm_generating -> skill_fetching(query_fund) -> llm_generating
  -> model_first_token -> [68 个 token 分片] -> done
final_text (108 chars): 易方达蓝筹精选混合（代码005827）是一只混合型基金...
核心阶段命中: accepted/done/llm_generating/model_first_token/thinking ｜ 缺失: 无
skill_fetching 命中: True ｜ token 流式生效: True（68 分片）
```

- token 级流式：68 个字符/子词分片经 `stream_callback` 透传，与 `llm_chat_stream` 粒度等价。
- 进度阶段：核心 5 阶段全命中；`model_first_token` 在首个 `TextBlockDeltaEvent` 触发，复刻现有 TTFT 语义。
- 工具调用：`query_fund` 的 `ToolCallStartEvent` 触发 `skill_fetching`，与现有 `_emit_progress(ctx,"skill_fetching")` 对齐。

### 3.2 离线 stub

`python -m prototype.e3_streaming.run_prototype --stub`：用 `_StubChatModel`
（先发 `ToolCallBlock(query_fund)`，再流式 `TextBlock`）验证映射代码路径，不连模型。同样跑通。

### 3.3 show_thinking 路径

`--show-thinking` 下，Qwen3 经该端点会把推理分离到 `ThinkingBlockDeltaEvent`（AgentScope 的
`OpenAIChatModel` 把 `reasoning_content` 映射为 `ThinkingBlock`）。ShapeAdapter 用
`ThinkingBlockStartEvent`/`EndEvent` 包一次 `<think>...</think>`，中间透传原始 delta。

## 4. 缺口清单（移交下游）

1. **`reset_tools` 元工具噪音**：原生 `Toolkit` 的 `ToolGroup` 激活机制会让 agent 先调一次
   `reset_tools`（meta-tool）再调业务工具，产生额外 `skill_fetching(reset_tools)` 进度。
   现有架构无此概念。**决策点**：SSE 层过滤掉 `reset_tools` 进度，还是暴露给前端？
   （-> 建议并入 G2 #5 或 G3 #6 落实时决定。）

2. **`<think>` 包裹粒度**（已修，留作教训）：naive 做法是每个 `ThinkingBlockDeltaEvent` 包一次
   `<think>delta</think>`，产出 `<think>用</think><think>户</think>...` 碎片，破坏前端折叠。
   正解是用 `Start/EndEvent` 包一次。**移交**：生产 ShapeAdapter 须沿用此 start/end 包法。

3. **`llm_chat_stream` 双实现统一**（R1 §5.1）：现 `llm_chat_stream` 是独立 httpx SSE；
   原生路径经 `ChatModelBase(stream=True)` -> `reply_stream` 统一了流式。
   `llm_chat_stream` 的命运（保留薄包装 / 退役）-> **E2 #11** 已在候补。

4. **HITL 暂停无对应阶段**：`RequireUserConfirmEvent`（危险操作前验证，栅栏 #2）在现有契约里
   没有进度阶段。ShapeAdapter 映射为 `awaiting_confirm`，但 SSE 层如何向前端表达"等待确认"
   需新增事件类型。**-> G3 #6（栅栏 #2 原生重表达）落实时定。**

5. **进度阶段更细，需对齐前端契约**：原生 `ModelCallStart`/`ToolCallStart`/`ToolResultStart`
   是分离事件，可暴露比现有更细的阶段。保形 = 至少复刻现有粗阶段；是否升级到细阶段是
   前端契约决策（map Notes：前端改动除非流式契约变化才在范围内）。**默认保粗阶段。**

6. **GatewayChatModel 仍是薄实现**：本原型的 `GatewayChatModel` 只验证了"组合 inner 模型 +
   `_call_api` 委派 + stream=True 透传"可工作。G1 决策里的 Opik span / httpx 回退 / 熔断 key
   上移到类，留 G1 落地时补（当前熔断复用 `model_gateway._circuit`，no-op 兜底）。

7. **DashScope 原生流式未验**：G1 决策提到"DashScope 原生流式验证 ->#12"。本原型仅验了
   OpenAI 兼容端点（有 base_url）。DashScope（仅 api_key，无 base_url）的 `stream=True`
   路径未跑（当前 .env 配的是 base_url 端点）。**未阻塞，但 G1/G2 落地时需补验。**

## 5. 对下游 ticket 的影响

- **#12 本身**：保形可行，已验证。无新阻塞。
- **#11 E2（切换策略/旧代码命运）**：`llm_chat_stream` 的双实现问题（缺口 3）是 E2 的输入。
- **#5 G2（4 业务 agent 形态）**：`reset_tools` 噪音（缺口 1）应在 G2 落实时定夺。
- **#6 G3（栅栏 #2 原生重表达）**：HITL 暂停的 SSE 表达（缺口 4）并入 G3。
- **未毕业新 fog**：原生流式比现有更细，是否升级前端契约——默认不升级（保形），除非前端主动要求。
