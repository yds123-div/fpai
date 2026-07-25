# 栅栏 #2 安全意图检查清单（G3 验收依据）

> **来源**：E2（#11）决议--24 测试随 plan-JSON 机制在切换 PR 删除，安全意图不靠可执行测试代码承载，改由本 checklist 交给 G3（#6）逐条覆盖。
>
> **用途**：G3 把栅栏 #2 的 5 项安全意图用原生 AgentScope 机制重表达时，逐条对照本清单验收，确保原生机制不丢旧测试编码的具体行为。
>
> **旧测试文件**：`tests/test_plan_validation.py`（24 测试，ADR-0001 决策 7 落地）。旧机制：`backend/agents/plan_validation.py`（`validate_plan` / `build_retry_feedback` / `run_plan_with_retry`）。

## 栅栏 #2 五项原生机制

| # | 机制 | 语义 |
|---|------|------|
| M1 | 工具参数校验 | 工具参数 schema 校验（必填、非空、类型），一次收集全部错误 |
| M2 | 工具调用白名单 | Toolkit 只注册合法工具，模型无法调用白名单外工具 |
| M3 | 危险操作执行前验证（HITL） | 危险操作执行前人工确认 |
| M4 | 无效 tool_call 回灌重试 | 无效 tool_call 反馈回灌让模型自愈，有重试上限，耗尽后兜底 |
| M5 | 部分工具失败明确反馈 | 部分工具失败时合法结果保留、非法部分明确反馈给用户 |

---

## 安全意图逐条

每条：**意图** -> **旧测试如何验** -> **原生承接机制** -> **G3 验收点**。

### SI-1：合法工具集是单一权威，白名单外工具被拒

- **旧测试**：
  - `test_valid_task_types_is_the_four_authoritative_types`（L28）：`VALID_TASK_TYPES == ("product_query","product_interpret","product_compare","other")`，白名单唯一权威，prompt 与校验器共引。
  - `test_validate_plan_hallucinated_type_all_bad`（L104）：`type="fund_analysis"` -> `[L2]` 错误，含 `tasks[0]` 和坏 type 名。
  - `test_validate_plan_partial_hallucination_locates_bad_index`（L120）：多任务中 `tasks[1]` 是 `kb_search` -> `[L2]` 错误定位到 `tasks[1]`。
- **原生承接**：**M2 工具调用白名单**--AgentScope Toolkit 只注册合法工具（G2 #5 颗粒化取数工具），模型物理上无法调用未注册工具；白名单从"代码常量"变成"Toolkit 注册表"，单源。
- **G3 验收**：模型输出白名单外工具名时，AgentScope 不执行该 tool_call（-> M4 回灌重试）。白名单只有一处真相（Toolkit 注册），无散落副本。

### SI-2：工具参数必须存在且非空

- **旧测试**：
  - `test_validate_plan_missing_tasks`（L92）：缺 `tasks` -> `[L1]` 错误含 "tasks"。
  - `test_validate_plan_empty_tasks_array`（L99）：`tasks: []` -> `[L1] tasks 为空数组：至少输出 1 个子任务`。
  - `test_validate_plan_empty_question`（L138）：`question: "   "` -> `[L1]` 错误定位到 `tasks[0]`，含 "question"。
- **原生承接**：**M1 工具参数校验**--每个取数工具的参数 schema 标注必填 + 非空（`minLength`/`minItems`），AgentScope 在执行前校验。旧"至少 1 个子任务"在原生形态下 = "模型至少发起 1 次有效 tool_call"（ReAct 循环天然要求，若 0 调用则回复空->由 M4 兜底处理）。
- **G3 验收**：必填参数缺失/空白时，tool_call 被判无效（-> M4 回灌重试），错误反馈定位到具体参数。

### SI-3：一次收集全部错误（非短路）

- **旧测试**：`test_validate_plan_collects_multiple_errors_at_once`（L154）：`tasks[0]` 同时有 L2 幻觉 type + L1 空 question -> 2 条错误一次返回，非短路。
- **原生承接**：**M1 工具参数校验** + **M2 工具调用白名单**--多 tool_call 同一轮回合内，所有非法调用/参数错误一次收集，反馈一次回灌（而非逐条往返）。
- **G3 验收**：模型一轮发起多个非法 tool_call 时，错误反馈合并为一条消息回灌，而非逐个重试。

### SI-4：模型输出不可解析时不静默通过

- **旧测试**：
  - `test_validate_plan_empty_input`（L63）：空串/纯空白 -> `[L1] 输出为空`。
  - `test_validate_plan_unparseable_json`（L68）：截断 JSON（括号永不闭合）-> `[L1]` 含 "解析"。
  - `test_parse_plan_returns_none_for_garbage`（L183）：纯文本/空串 -> `parse_plan` 返回 `None`。
- **原生承接**：**M4 无效 tool_call 回灌重试**--AgentScope 无法从模型输出解析出合法 tool_call 时，判无效并回灌重试，不静默降级。
- **G3 验收**：模型输出无合法 tool_call（纯文本/截断/空）时，触发 M4 重试，不直接走兜底（除非重试耗尽）。

### SI-5：可救活的格式容错不算失败、不消耗重试预算

- **旧测试**：
  - `test_validate_plan_rescuable_format_passes`（L77）：` ```json ...}} ` 代码块包裹 + 多余 `}` -> `validate_plan` 返回 `[]`（通过），不消耗重试预算。
  - `test_parse_plan_strips_think_block`（L176）：`<think>...</think>` 前缀被剥离后正常解析。
- **原生承接**：**M4 无效 tool_call 回灌重试（容错解析层）**--AgentScope 的 tool_call 解析器对模型常见格式噪声（markdown 包裹、思考块、多余符号）做容错修复，修复成功算有效调用、不触发重试。
- **G3 验收**：模型输出带代码块包裹/思考块/多余符号但语义合法时，被容错解析为有效 tool_call，不计入重试次数。需确认 AgentScope 2.0.4 原生解析器的容错边界（R1 #3 盘点），不足部分自写薄层。

### SI-6：错误反馈让模型自愈--含错误定位 + 白名单回灌 + 修正指令

- **旧测试**：
  - `test_build_retry_feedback_contains_count_whitelist_and_instruction`（L191）：反馈含"共 N 条"、4 类白名单全回灌、"请直接输出修正后的完整 plan JSON"、错误原文精确到 `tasks[0]` + 坏 type 名。
  - `test_retry_feedback_appended_to_history_for_next_call`（L308）：续轮历史 = 原始 user + assistant（错误原文）+ user（反馈含"合法 type 白名单"）。
- **原生承接**：**M4 无效 tool_call 回灌重试**--无效 tool_call 的错误反馈回灌进对话历史，反馈三要素：① 错误原因定位到具体工具/参数；② 合法工具白名单回灌；③ 修正指令。AgentScope 原生 error message 若不足，自写反馈构造层补充白名单+定位。
- **G3 验收**：重试反馈消息含上述三要素；续轮历史结构正确（错误原文 + 反馈追加）。

### SI-7：重试有上限，耗尽后不卡死

- **旧测试**：`test_max_plan_retries_is_two`（L37）：`MAX_PLAN_RETRIES == 2`（最多 1+2=3 次 LLM 调用）。
- **原生承接**：**M4 无效 tool_call 回灌重试**--重试次数有上限（`ModelConfig` 管控，G1 #4 决议），耗尽后走兜底，不无限重试。
- **G3 验收**：重试上限可配、有默认值；耗尽后不卡死，进入兜底路径。

### SI-8：重试耗尽后兜底--启发式路由

- **旧测试**：`test_retry_exhausted_fallback_heuristic`（L249）：3 次全败（不可解析）-> `status="fallback_heuristic"`，`plan=None`，`llm_calls=3`，事件序列含 3 次 `plan_validation_error` + 1 次 `plan_fallback_heuristic`。
- **原生承接**：**M4 无效 tool_call 回灌重试（耗尽后兜底）**-> **栅栏 #3 启发式兜底**（#8 自写退路）--LLM 挂时仍可路由，降级为安全网。
- **G3 验收**：重试耗尽后触发启发式兜底（-> #8），不抛异常中断；兜底触发有审计事件。

### SI-9：重试耗尽后部分放行--保留合法任务、丢弃非法任务

- **旧测试**：`test_retry_exhausted_partial_pass`（L265）：部分幻觉（`tasks[1]` 是 `fund_analysis`）重试耗尽 -> `status="partial_pass"`，保留 `tasks[0]`（合法）、丢弃 `tasks[1]`，`dropped` 记录被丢任务 index+task+reasons，末事件 `plan_partial_drop`。
- **原生承接**：**M5 部分工具失败明确反馈**--多 tool_call 中部分合法部分非法时，合法工具结果保留、非法工具失败明确反馈给用户（模板化提示，不调 LLM）；被丢任务的技术细节落审计。
- **G3 验收**：一轮多工具调用中部分失败时，合法结果不丢、失败部分有用户可见反馈 + 审计记录。

### SI-10：重试不修改输入对话历史

- **旧测试**：`test_retry_does_not_mutate_input_messages`（L297）：重试后 `messages == snapshot`（输入未被修改）。
- **原生承接**：**M4 无效 tool_call 回灌重试（实现约束）**--回灌反馈时追加到历史副本，不原地修改传入的 messages。
- **G3 验收**：重试机制的回灌不破坏原始对话历史引用（实现层约束，防副作用）。

### SI-11：重试环各分支可观测（首次通过/二次自愈/兜底/部分放行）

- **旧测试**：
  - `test_retry_first_pass`（L220）：首次通过 -> `status="first_pass"`，`llm_calls=1`，`events=[]`。
  - `test_retry_success_on_second_attempt`（L235）：二次自愈 -> `status="retry_success"`，`llm_calls=2`，事件 `["plan_validation_error","plan_retry_success"]`。
  - `test_retry_exhausted_fallback_heuristic`（L249）：兜底 -> 事件含 3 次 `plan_validation_error` + `plan_fallback_heuristic`。
  - `test_retry_exhausted_partial_pass`（L265）：部分放行 -> 末事件 `plan_partial_drop`。
- **原生承接**：**栅栏 #4 审计/合规**（`audit.append_event` + answer_id）--四个分支（first_pass / retry_success / partial_pass / fallback_heuristic）均有对应审计事件，失败率可度量。G3 需保证原生机制产生的事件可被审计适配层消费。
- **G3 验收**：原生重试/失败路径产生的事件能被审计适配层（栅栏 #4）捕获并重表达；first_pass 无多余事件。

### SI-12：接线完整性--主链实际走重试机制、失败任务透传

- **旧测试**：`test_coordinator_plan_wires_retry_and_propagates_dropped`（L339）：`CoordinatorAgent.plan()` 实际调用 `run_plan_with_retry`（非单次调用），`dropped` 透传到 plan 结果。动机：机制坏了会静默退化为旧行为。
- **原生承接**：**M4 + M5 接线**--原生 ReActAgent 的 tool_call 失败处理实际生效（非被绕过），失败工具信息透传到最终回复。
- **G3 验收**：原生主链的无效 tool_call 确实走 M4 重试（非静默跳过）；部分失败走 M5 反馈（非静默丢弃）。

---

## 旧测试 -> 安全意图 -> 原生机制 映射表

| # | 旧测试（行号） | 安全意图 | 原生机制 | 栅栏 |
|---|---------------|---------|---------|------|
| 1 | `test_valid_task_types_is_the_four_authoritative_types`（L28） | SI-1 白名单单一权威 | M2 | #2 |
| 2 | `test_max_plan_retries_is_two`（L37） | SI-7 重试上限 | M4 | #2 |
| 3 | `test_validate_plan_legal`（L59） | 基线：合法通过 | M1+M2 | #2 |
| 4 | `test_validate_plan_empty_input`（L63） | SI-4 不可解析不静默通过 | M4 | #2 |
| 5 | `test_validate_plan_unparseable_json`（L68） | SI-4 不可解析不静默通过 | M4 | #2 |
| 6 | `test_validate_plan_rescuable_format_passes`（L77） | SI-5 可救活格式容错 | M4 | #2 |
| 7 | `test_validate_plan_missing_tasks`（L92） | SI-2 参数必须存在 | M1 | #2 |
| 8 | `test_validate_plan_empty_tasks_array`（L99） | SI-2 参数非空 | M1 | #2 |
| 9 | `test_validate_plan_hallucinated_type_all_bad`（L104） | SI-1 白名单外被拒 | M2 | #2 |
| 10 | `test_validate_plan_partial_hallucination_locates_bad_index`（L120） | SI-1 部分幻觉定位 | M2+M5 | #2 |
| 11 | `test_validate_plan_empty_question`（L138） | SI-2 参数非空 | M1 | #2 |
| 12 | `test_validate_plan_collects_multiple_errors_at_once`（L154） | SI-3 一次收集全部错误 | M1+M2 | #2 |
| 13 | `test_parse_plan_strips_think_block`（L176） | SI-5 可救活格式容错 | M4 | #2 |
| 14 | `test_parse_plan_returns_none_for_garbage`（L183） | SI-4 不可解析不静默通过 | M4 | #2 |
| 15 | `test_build_retry_feedback_contains_count_whitelist_and_instruction`（L191） | SI-6 反馈三要素 | M4 | #2 |
| 16 | `test_retry_first_pass`（L220） | SI-11 首次通过分支可观测 | M4+#4 | #2/#4 |
| 17 | `test_retry_success_on_second_attempt`（L235） | SI-6+SI-11 二次自愈 | M4+#4 | #2/#4 |
| 18 | `test_retry_exhausted_fallback_heuristic`（L249） | SI-8 兜底 | M4+#3 | #2/#3 |
| 19 | `test_retry_exhausted_partial_pass`（L265） | SI-9 部分放行 | M5+#4 | #2/#4 |
| 20 | `test_retry_does_not_mutate_input_messages`（L297） | SI-10 不修改输入 | M4 | #2 |
| 21 | `test_retry_feedback_appended_to_history_for_next_call`（L308） | SI-6 续轮历史追加 | M4 | #2 |
| 22 | `test_coordinator_plan_wires_retry_and_propagates_dropped`（L339） | SI-12 接线完整 | M4+M5 | #2 |
| 23 | `test_emit_plan_audit_events_writes_when_answer_id_present`（L385） | SI-11 审计落事件 | #4 | #4 |
| 24 | `test_emit_plan_audit_events_skips_when_no_answer_id`（L415） | SI-11 无 answer_id 不落 | #4 | #4 |

---

## 无对应旧测试的原生机制

- **M3 危险操作执行前验证（HITL）**：24 测试无对应--plan-JSON 链路只做路由决策，无"危险操作"概念（不执行交易/修改）。**G3 需新增定义**：原生形态下哪些工具属"危险操作"（如交易下单、用户资料修改），并在执行前加 HITL 确认。这是原生架构新增的安全能力，非旧测试迁移。

## 属于其他栅栏的意图（G3 验收范围外，需保证不堵死）

- **SI-11 审计事件**（测试 16-19、23-24）：属**栅栏 #4 审计/合规**。G3 不负责审计实现，但需保证 M4/M5 各分支产生的事件可被审计适配层（`audit.append_event` + answer_id 重表达）消费。具体事件类型映射（`plan_validation_error` -> 原生等价事件等）由栅栏 #4 落地。
- **SI-8 启发式兜底**（测试 18）：属**栅栏 #3 启发式兜底**（-> #8 自写退路）。G3 只负责"重试耗尽 -> 触发兜底"的交接点，兜底实现由 #8 落地。

---

## G3 验收用法

G3（#6）逐条对照本清单：
1. 对 SI-1 ~ SI-12 每条，确认原生机制（M1-M5）已覆盖且行为等价或更优。
2. 对 M3（HITL），确认已定义危险操作集合 + HITL 接入点（旧测试无对应，新增项）。
3. 对跨栅栏意图（SI-8 兜底、SI-11 审计），确认交接点清晰、不堵死其他栅栏。
4. 验收通过 = 本清单所有条目有原生落点，旧测试编码的安全行为无遗漏。
