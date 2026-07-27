# ADR-0001：Coordinator plan 输出的三层校验与重试闭环

- 状态：已接受（核心假设"真模型收到错误反馈后能自愈"待原型验证）
- 日期：2026-07-22
- 决策方式：`/grilling` 盘问会话，7 项决策逐项锁定

## 上下文

主对话链路（`orchestrator/run.py` → `agents/fund_agent_framework.py` 的 `CoordinatorAgent.plan`）让 LLM 输出 plan JSON（`{multi, tasks:[{type, question}], final_instruction}`），再按 `type` 路由到四个业务 Agent。大模型输出不稳定（幻觉 type、JSON 格式错误、臆测基金代码），而现状的防御哲学是**静默降级**：

- JSON 解析失败 → 直接回退启发式分类 `_heuristic_classify`，不重试；
- 幻觉 `type` → 静默 `continue` 丢弃该子任务（用户问了两个问题可能只得到一个回答，无任何提示）；
- 白名单写在两处（system prompt 散文 + 过滤代码），存在漂移风险；
- 无任何校验失败/重试/兜底的埋点，"失败率"无从测量。

目标：将"不信任大模型输出，先校验拦截、报错回灌自愈、兜底对用户透明"的工程机制落到该链路。

## 决策

### 1. 校验对象：仅 Coordinator plan JSON 链路

废弃的 AgentScope Toolkit 隐式路由路径（`agents/routing/implicit.py`，主链路已不再回退到它）不改动。plan 的 `type` 即"工具名"，`question`/基金代码即"参数"。

### 2. 重试闭环（L1 格式 / L2 白名单错误）

- 校验失败 → 对话历史续轮：追加 `assistant`（错误输出原文）+ `user`（错误反馈），让 LLM 自我修正；
- 错误反馈含三样：① 具体错误原因（精确到 `tasks[i].type`）；② 错误输出原文（已在 assistant 消息中）；③ 可用 type 白名单回灌；
- 最多重试 2 次（`MAX_PLAN_RETRIES = 2`）；耗尽后回退 `_heuristic_classify`（现有行为降级为安全网）；
- 代码能救活的格式伤（代码块包裹、多余 `}`，即现有 `_extract_json_object`/`_try_fix_json` 能修复的）算通过，不消耗重试预算；
- 重试循环内 skill 数据（`fund_name_to_code`）只在循环前算一次，复用。

### 3. 部分幻觉：整体重试 → 耗尽后部分放行 + 用户透明

- 多任务 plan 中任一非法 `type` → 整个 plan 判不过检，触发重试（反馈精确到病灶）；
- 重试耗尽后仍有非法任务 → 丢弃非法任务、保留合法任务继续执行（最坏情况不劣于现状），并：
  - 在最终答复开头插入模板化用户提示（如"您的问题中，以下部分我暂时无法处理：「…」"），对用户隐藏内部 jargon；模板拼接生成，不调 LLM；
  - 审计记录被丢弃任务的技术细节（type 原值、question、错误原因）。

### 4. L3 参数校验（基金代码可信集合）不进重试环

L1/L2 是模型**有能力自愈**的错误（规范在其上下文内）；L3 是**事实性错误**（真实代码不在模型脑子里，重试只会再编一个）。基金代码维持现有确定性处理：skill 查证 → 可信集合 → 清洗不可信代码 / `fund_code_not_found` 中断，一行不改；不新增参数规则。

### 5. 可观测性：复用 audit，新增 4 种事件

复用 `audit.append_event`，新增事件：`plan_validation_error`（attempt、层、错误清单）、`plan_retry_success`、`plan_fallback_heuristic`、`plan_partial_drop`。不引入新指标系统；Opik 接入明确推迟。失败率数字（"首次通过率 → 重试修复率 → 兜底触发率"）等真实测量后再对外讲，不编造。

### 6. 代码组织：新模块 + 白名单单一权威

新建 `backend/agents/plan_validation.py`：`VALID_TASK_TYPES`（白名单唯一权威，prompt 与校验器共同引用，消灭两处漂移）、`validate_plan(raw) -> list[str]`（L1+L2 纯函数，一次收集全部错误）、`build_retry_feedback(errors) -> str`、常量 `MAX_PLAN_RETRIES = 2`（不接配置系统）。`CoordinatorAgent.plan()` 只增加重试循环并调用该模块。

### 7. 测试：建立项目首个测试文件

新建 `backend/tests/test_plan_validation.py`（uv 加 pytest dev 依赖）：校验器单测（合法/烂 JSON/可救活格式/幻觉 type/部分幻觉/空 question）、反馈消息单测、stub `llm_chat` 的重试环分支测试（一次修好 / 三次全败兜底 / 部分放行）。动机：该机制坏了会静默退化为旧行为，无测试则上线后失效也无感知。

## 实现清单

- 新建 `backend/agents/plan_validation.py`
- 修改 `backend/agents/fund_agent_framework.py`（plan() 重试环、删除散落白名单过滤、plan 标注 `dropped`、落审计事件）
- 修改 `backend/orchestrator/run.py`（多任务分支检测 `plan.dropped`，注入用户提示行至 `_format_multi_task_response` 输出开头）
- 新建 `backend/tests/test_plan_validation.py` + `pyproject.toml` 加 pytest
- 不动：L3 基金代码逻辑、abort 机制、业务 Agent、合规审查、AgentScope 废弃路径

## 后果

正面：LLM 输出不再被无条件信任；低频幻觉场景下用户问题不再被静默吞掉；白名单单源化；校验失败可度量；核心逻辑有测试。对 99% 正常请求零延迟影响（仅首次调用即通过）。

负面/代价：校验失败的请求多 1-2 次 LLM 调用（每次 30s 超时上限不变）；plan 环节代码复杂度上移，靠纯函数模块与测试对冲。

待验证假设（原型先行回答）：**真实模型（deepseek-v4-flash，经火山 Ark 网关）收到续轮错误反馈后能否稳定自愈**。若不能，需迭代 `build_retry_feedback` 话术或重审决策 2。

备选方案（已否决）：全部塞 `fund_agent_framework.py`（文件已 750 行）；L3 也进重试环（事实性错误模型无自愈能力）；静默部分放行（用户问题被吞）；接 Opik 做埋点（推迟）；重试次数接配置（镀金）。
