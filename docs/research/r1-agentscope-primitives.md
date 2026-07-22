# R1 研究笔记：已装 AgentScope 原生原语盘点

- 工单：[#3 R1：盘点已装 AgentScope 原生原语](https://github.com/yds123-div/fpai/issues/3)
- 分支：`research/agentscope-capabilities`
- 日期：2026-07-23
- 方法：直接读取 `backend/.venv` 内已装包源码（非文档猜测）

## 0. TL;DR

已装版本是 **AgentScope 2.0.4.post1**（`backend/.venv`），与 `backend/pyproject.toml` 的 `agentscope>=0.0.8`、`backend/requirements.txt` 的 `>=1.0.16` 均不符——实际是 2.x 大重写。2.0 的 API 形态与 0.x/1.x 完全不同（模块名单数化：`agent`/`tool`/`model`/`middleware`；`ReActAgent` 改名为 `Agent`；`memory` 模块消失）。

**栅栏 #2 想要的五项安全意图，2.0 全部原生支持**（工具参数校验、工具白名单、危险操作执行前验证、无效 tool_call 重试、部分失败反馈）。**`llm_chat` 作为模型 choke-point 的复用是最大缺口**：`llm_chat` 现是 `list[dict]->str` 的纯文本对话，无 tools/tool_choice/structured output/流式，无法直接喂给 `Agent`。下游需决策如何把 choke-point 嫁接到原生 `ChatModelBase`。

## 1. 版本与来源

| 项 | 值 |
|---|---|
| 已装版本 | `2.0.4.post1`（`agentscope.__version__`） |
| 安装路径 | `backend/.venv/Lib/site-packages/agentscope/` |
| `pyproject.toml` pin | `agentscope>=0.0.8`（optional `[agent]`）— 严重过期 |
| `requirements.txt` pin | `agentscope>=1.0.16` — 也低于实际 |
| 结论 | 版本声明失真；迁移须以 **2.0** API 为准，并修正 pin |

**旧路径已碎**：`agents/routing/implicit.py` 写的是 0.x/1.x API——`from agentscope.agent import ReActAgent`（2.0 已改名 `Agent`）、`from agentscope.memory import InMemoryMemory`（2.0 无 `memory` 模块）。该文件在 2.0.4 下 `ImportError`，印证 map「`routing/implicit.py` 不当种子、迁移中退役」。

## 2. 可用原语清单

### 2.1 `Agent`（即 ReActAgent）

2.0 把 ReActAgent 直接命名为 `Agent`，`from agentscope.agent import Agent`。`__init__` 签名（`agent/_agent.py:100`）：

```python
Agent(
    name: str,
    system_prompt: str,
    model: ChatModelBase,                 # 接受任意 ChatModelBase 子类（含自写）
    toolkit: Toolkit | None = None,       # 工具/MCP/skill 的唯一来源
    middlewares: list[MiddlewareBase] | None = None,
    state: AgentState | None = None,
    offloader: Offloader | None = None,
    model_config: ModelConfig | None = None,    # fallback_model + max_retries
    context_config: ContextConfig | None = None,
    react_config: ReActConfig | None = None,    # max_iters / stop_on_reject / 中断
)
```

- 内置 `PermissionEngine(self.state.permission_context)`（`_agent.py:156`）——权限是 agent 级一等公民。
- `async reply(inputs) -> Msg`：聚合所有事件返回最终消息。
- `async reply_stream(inputs) -> AsyncGenerator[AgentEvent]`：**原生 token/事件级流式**，yield `ReplyStartEvent`/`ToolResultTextDeltaEvent`/`ToolResultEndEvent` 等。
- 接受外部交互续轮：`UserConfirmResultEvent`（权限确认回执）、`ExternalExecutionResultEvent`（外部工具回执）、`UserInterruptEvent`（中断）。

### 2.2 `Toolkit` / `ToolGroup` / `FunctionTool`

`from agentscope.tool import Toolkit, ToolGroup, FunctionTool, ToolResponse, ToolChunk, ToolMiddlewareBase`。

- `Toolkit(tools=[], skills_or_loaders=[], mcps=[], tool_groups=[])`（`tool/_toolkit.py:88`）：工具按 **`ToolGroup`** 分组；agent 通过 `state.tool_context.activated_groups` 激活/停用组——这是**工具白名单的原生机制**（只把激活组的 schema 发给模型）。
- `check_tool_available(name, activated_groups)`（`:540`）：工具不在激活组 -> 触发错误反馈。
- `get_tool_schemas(groups)`：按组生成发给模型的 JSON schema。
- `FunctionTool(func, name=None, description=None, is_read_only=False, middlewares=[])`（`tool/_adapters.py:49`）：把普通 Python 函数包成工具，`input_schema` 由函数签名/docstring **自动抽取**（pydantic/类型注解 -> JSON schema）。`call()` 自动 await 协程函数。
  - ⚠️ **`FunctionTool.check_permissions` 默认返回 `PermissionBehavior.ASK`**（`_adapters.py:90`）——即自写工具默认每次都要用户确认。业务工具必须显式注册 ALLOW 权限规则，否则 agent 会在每次工具调用处暂停等待确认。

### 2.3 `ToolResponse` / `ToolChunk`

`tool/_response.py`：

- `ToolResponse.state` ∈ `SUCCESS | ERROR | DENIED | INTERRUPTED`。`DENIED`（权限拒）、`ERROR`（校验/执行失败）、`INTERRUPTED`（中断）都会被**回灌进对话**给模型，让其在下一轮 reasoning 自我修正。
- `ToolChunk`：流式工具的分片，`is_last` 标记结束，可累计成 `ToolResponse`。

### 2.4 `ChatModelBase`（模型层契约）

`from agentscope.model import ChatModelBase, OpenAIChatModel, DashScopeChatModel, ...`（`model/_base.py`）。`llm_chat` 现已用其中的 `OpenAIChatModel`/`DashScopeChatModel`。

- `__init__(credential, model, parameters, stream=True, max_retries=3, retry_delay=1.0, context_size=32768)`。
- `async __call__(messages: list[Msg], tools=None, tool_choice=None) -> ChatResponse | AsyncGenerator[ChatResponse]`：自带重试（仅 `_get_retryable_exceptions()` 内的异常计数）。
- `async _call_api(model_name, messages, tools, tool_choice, **kwargs)`：**子类唯一需实现的抽象方法**。
- `async generate_structured_output(messages, structured_model: Type[BaseModel] | dict) -> StructuredResponse`：原生结构化输出，pydantic 或 JSON schema，自带校验（`jsonschema.validate` / `model_validate`）。
- `_validate_tool_choice`：校验 `tool_choice` 里的工具名是否存在。
- `count_tokens`：上下文压缩用。

**关键差异**：`ChatModelBase` 吃 `list[Msg]`、吐 `ChatResponse`（带 `ToolCallBlock`）、原生支持 tools/streaming/structured；而 `llm_chat` 吃 `list[dict]`、吐 `str`、不支持 tools。二者签名不兼容。

### 2.5 `MiddlewareBase`（agent 级，5 个 hook）

`from agentscope.middleware import MiddlewareBase, TracingMiddleware, RAGMiddleware, ...`（`middleware/_base.py`）。洋葱模型 + 管道模型：

- `on_reply`：拦截整次回复。
- `on_reasoning`：拦截推理/模型调用阶段。
- `on_acting`：拦截**单次工具执行**（包 `toolkit.call_tool`）。注意：权限检查/输入校验在 hook **之外**由 agent 处理，此 hook 只见已校验已授权的 `tool_call`。
- `on_model_call`：拦截原始模型 API 调用（可拿到 `messages/tools/tool_choice/current_model`）。
- `on_system_prompt`：**管道式**变换 system prompt（多个中间件顺序套用）——用于把业务 prompt 集中到一处。
- `on_compress_context`：拦截上下文压缩。
- 每个 hook 可选；`is_implemented(hook_name)` 运行时探测。

### 2.6 `ToolMiddlewareBase`（工具级）

`from agentscope.tool import ToolMiddlewareBase`（`tool/_base.py:36`）：`on_tool_call(tool, input_kwargs, next_handler)`，洋葱式包**单个工具**的前/后逻辑，统一流式/非流式。粒度比 `on_acting` 更细（绑定到具体工具实例）。

### 2.7 `PermissionEngine`（权限/白名单/危险操作验证）

`from agentscope.permission import PermissionEngine, PermissionContext, PermissionDecision, PermissionRule, PermissionMode, PermissionBehavior`。agent 内置一个 engine。工具执行前（`_agent.py:1652`）调 `engine.check_permission(tool, parsed_input) -> PermissionDecision`：

- `ALLOW`：执行。
- `DENY`：`ToolResponse(state=DENIED)` 回灌模型。
- `ASK` / `PASSTHROUGH`：发 `RequireUserConfirmEvent`，**暂停**等人工确认（危险操作执行前验证 + HITL）。
- `PermissionRule`：按 `tool_name` + 可选 `rule_content`（细粒度模式，如路径/命令前缀）匹配。`ToolBase.match_rule` 支持自定义匹配。

### 2.8 `TracingMiddleware`（OTel）

`middleware/_tracing/_trace.py`：基于 **OpenTelemetry**（`from opentelemetry import trace`）。spans 覆盖 agent request/response、LLM request/response、tool request/response。需先 `setup_tracing` 初始化 `TracerProvider`，否则 `_check_tracing_enabled()` 返回 False 走 no-op。与 ADR-0002（Opik 暂停）无冲突——OTel 是另一条可观测路径，本 map 只保证不堵死。

### 2.9 `Skill`

`from agentscope.skill import Skill, SkillLoaderBase, LocalSkillLoader`。原生支持从目录加载 skill 并生成 prompt。但 map 要求「技能重写为**静态**工具 + DB 驱动配置（`agent_profiles`/`skill_profiles`）保留」——静态工具走 `FunctionTool` 即可；DB 驱动动态加载需自写 `SkillLoaderBase` 子类（缺口，见 §5）。

### 2.10 配置类

- `ModelConfig`：`max_retries`（默认 0）+ `fallback_model: ChatModelBase | None`。agent 的 `_call_model`（`_agent.py:2322`）按 `[主模型, fallback]` 顺序、每个 `max_retries+1` 次尝试——**原生模型级重试 + fallback**。
- `ReActConfig`：`max_iters`（默认 20）、`stop_on_reject`（工具被权限拒时是否停止）、中断处理。
- `ContextConfig`：上下文压缩触发/保留比例、`tool_result_limit`（工具结果截断）。

## 3. 最小用法示例

```python
from agentscope.agent import Agent, ModelConfig, ReActConfig
from agentscope.tool import Toolkit, FunctionTool, ToolGroup
from agentscope.model import OpenAIChatModel
from agentscope.message import Msg, UserMsg, TextBlock

# 1. 业务能力 -> 静态工具（input_schema 自动从签名抽取）
def product_query(fund_code: str) -> str:
    """查询基金产品信息。

    Args:
        fund_code: 6 位基金代码。
    """
    ...  # 现有 skill 逻辑

# 2. toolkit（分组即白名单；激活哪组就只把哪组 schema 发给模型）
toolkit = Toolkit(tool_groups=[
    ToolGroup(name="fund_query", tools=[FunctionTool(product_query)]),
])

# 3. 模型（llm_chat 的 choke-point 如何嫁接见 §5 缺口）
model = OpenAIChatModel(model_name="...", api_key="...", stream=True, client_kwargs={"base_url": "..."})

# 4. agent
agent = Agent(
    name="fund_agent",
    system_prompt="...",                       # 业务 prompt（可经 on_system_prompt 中间件集中管理）
    model=model,
    toolkit=toolkit,
    model_config=ModelConfig(max_retries=1, fallback_model=...),
    react_config=ReActConfig(max_iters=8),
    # middlewares=[AuditMiddleware(), TracingMiddleware()],  # 审计/可观测
)

# 5. 调用（流式拿事件；非流式用 await agent.reply(...)）
async for event in agent.reply_stream(UserMsg(name="user", content=[TextBlock(text="...")])):
    ...  # 转 SSE / 进度回调
```

## 4. 栅栏原生重表达映射（#1–#6）

| 栅栏 | 原生落位 | 结论 |
|---|---|---|
| **#1 基金代码可信集** | `FunctionTool` 包确定性 skill（name->code->可信集->清洗->查不到 abort）；`input_schema` 校验入参；工具内部确定性逻辑不变 | ✅ 原生可落，确定性保留 |
| **#2 plan-JSON 弃，安全意图重写** | 参数校验=`jsonschema.validate(input_schema)`；白名单=`Toolkit.activated_groups`+`PermissionEngine`；危险操作前验证=`PermissionBehavior.ASK`->`RequireUserConfirmEvent`；无效 tool_call 重试=`AgentOrientedException`->`ERROR` 回灌模型在 `max_iters` 内自愈（`_agent.py:1605-1640`）；部分失败=批调用 `return_exceptions=True`+每工具独立 `ToolResponse` 状态 | ✅ **五项全部原生** |
| **#3 启发式兜底** | ReActAgent 本身依赖模型推理，无「LLM 挂时启发式路由」原生对应。`ModelConfig.fallback_model` 仅处理模型 API 失败，非业务意图分类兜底 | ❌ **缺口**：需自写（前置路由层或 `on_reply` 中间件拦截模型不可用） |
| **#4 审计/合规** | `on_acting`/`on_reply` 中间件调 `audit.append_event`；`TracingMiddleware`(OTel) 补观测 | ✅ 原生 hook 在，接受一层手写适配（符合栅栏契约） |
| **#5 业务 prompt + structured_outputs** | `on_system_prompt` 管道集中 prompt 版本；`ChatModelBase.generate_structured_output(pydantic)` 原生结构化+校验 | ✅ 原生可落 |
| **#6 流式/SSE/进度回调** | `reply_stream` yield `AgentEvent`（含 `ToolResultTextDeltaEvent` 等）；`ChatModel(stream=True)` 吐 `AsyncGenerator[ChatResponse]` | ✅ 原生机制在；但 `llm_chat` 现为 `stream=False`，见 §5 |

## 5. 缺口（需自写的部分）

1. **`llm_chat` choke-point 嫁接（最大缺口，阻塞下游）**：`llm_chat` 是 `list[dict]->str` 纯文本，无 tools/tool_choice/structured/streaming；`Agent` 要的是 `ChatModelBase`（`list[Msg]->ChatResponse`，支持 tool_call）。三条路（留待后续 grilling/prototype ticket 决策）：
   - (a) 写 `ChatModelBase` 子类，`_call_api` 内部调 `llm_chat`——但 `llm_chat` 不支持 tools，需扩 `llm_chat` 或在子类里另起工具调用通道；
   - (b) 直接把 `llm_chat` 现用的 `OpenAIChatModel`/`DashScopeChatModel` 传给 `Agent`，绕过 `llm_chat` 函数——与「保留 choke-point」栅栏冲突；
   - (c) 把 `llm_chat` 重构为 `ChatModelBase` 子类本身（choke-point 即模型层），熔断/fallback 下沉到 `ModelConfig`+`_get_retryable_exceptions`。
   - 当前 `llm_chat_stream` 是独立 httpx SSE，与原生流式两套——需统一。
2. **#3 启发式兜底**：ReActAgent 无原生对应；需自写前置启发式路由（可复用现有 `_heuristic_classify`），在模型不可用/超时时短路到确定性分支。
3. **业务工具权限规则**：`FunctionTool` 默认 `ASK`，必须为 4 个业务工具注册 ALLOW 的 `PermissionRule`（或实现 `check_permissions` 直接 ALLOW 只读类），否则每次调用都暂停等确认。
4. **DB 驱动配置**：原生 `Skill`/`Toolkit` 是静态的；`agent_profiles`/`skill_profiles` 的 DB 驱动动态装配需自写 `SkillLoaderBase` 子类 + agent 工厂。
5. **#4 审计适配层**：一层手写中间件（栅栏已接受）。
6. **版本 pin 修正**：`pyproject.toml`/`requirements.txt` 需对齐到 `agentscope>=2.0.4`，否则新装环境会拉到错误版本。

## 6. 对下游 ticket 的影响 / fog 毕业

- **#3 阻塞 #4/#5/#6/#9/#12** 的关系成立：本笔记为它们提供事实基础。解除阻塞后，下游可基于「2.0 原语清单 + 缺口」展开。
- **fog 毕业**（map「Not yet specified」里「AgentScope 是否需升级」）：**已毕业**——已装 2.0.4.post1，无需升级；但需修正 pin。可转成一张 task ticket（修正版本声明）。
- **新 fog / 待票**：
  - `llm_chat` choke-point 嫁接策略（§5.1 的 a/b/c）是 G 系列前置决策，应起一张 grilling ticket 锁定路线。
  - #3 启发式兜底的自写形态（前置路由 vs 中间件）应并入栅栏 #3 的落实 ticket 一起盘问。
- **未变**：「multi-task / `final_instruction` 融合是否被原生推理吸收」仍待 G2 后毕业（原生 ReActAgent 单轮内多工具调用可能吸收多任务，但 `final_instruction` 融合语义需原型验证）。
