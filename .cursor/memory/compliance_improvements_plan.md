# 合规服务改进规划（S1/S2/S3）

<!-- 依据：T011 实现总结、technical_design §3.3/§4.1/§5.4、architecture 合规与 config、decisions S2。实现时需满足：T014 config 模块从 MySQL 加载合规策略与版本。 -->

## 目标

- **S1 稳定性/扩展**：策略来源可插拔；**T014 config 模块从 MySQL 加载合规策略与版本**；可选合规专用 LLM 路由。
- **S2 性能/安全**：输入/输出长度与频率限制；LLM 审查超时与熔断与 model_gateway 一致。
- **S3 可维护性**：LLM 审查 prompt 抽成常量或配置；审查结果写入审计（与 T012 对接）。

### 0.1 与当前实现对齐（as-is）

- 聊天主链路为 `FundAgentRouter + Coordinator`，合规改进需兼容“单任务/多任务并行融合”两种执行形态。
- chat SSE 当前事件为 `message_start`、`message_delta`、`status`、`structured_update`、`citation`、`done`、`error`；合规相关状态建议通过 `status` 暴露，不新增破坏性事件类型。
- `structuredOutputs[]` 已在 chat 返回和 `done` 事件透传；合规对输出文本和结构化结果的审查策略应同时覆盖两者（见 §2.1 输出长度与 §3.2 审计落库）。
- 会话恢复当前依赖 `content_summary`；合规审查结果若影响结构化输出展示，应在审计中明确记录决策与版本，避免刷新后解释不一致。

---

## 一、S1：策略来源可插拔与 T014 从 MySQL 加载

### 1.1 现状

- 合规策略当前为内存 `CompliancePolicy`，默认使用 `DEFAULT_POLICY`。
- 策略含：`blacklist_keywords`、`whitelist_keywords`、`enable_llm_input_check`、`enable_llm_output_check`、`policy_version`。

### 1.2 MySQL 存储约定（与 T004 一致）

- 使用已有表 **`config_strategy`**（迁移 001）：
  - `config_key`：固定键，如 `compliance_policy`，表示合规策略。
  - `config_value`：JSON，结构见下。
  - `version`：整型版本号，便于灰度与回滚。

**config_value JSON 结构建议：**

```json
{
  "policy_version": "v1.2",
  "blacklist_keywords": ["保本保息", "稳赚不赔", "承诺收益", "绝对收益"],
  "whitelist_keywords": ["历史收益仅供参考"],
  "enable_llm_input_check": true,
  "enable_llm_output_check": true,
  "llm_timeout_seconds": 30,
  "llm_circuit_key": "compliance_llm"
}
```

- 可选扩展：`compliance_prompt_input`、`compliance_prompt_output` 存 prompt 模板（见 S3），或另用 `config_key = compliance_prompts`。

### 1.3 T014 config 模块职责（从 MySQL 加载）

| 项 | 说明 |
|----|------|
| **接口** | `config.get_compliance_policy() -> CompliancePolicy \| None`；MySQL 未配置或不可用时返回 `None`，compliance 层回退到 `DEFAULT_POLICY`。 |
| **数据源** | 从 `config_strategy` 表 `WHERE config_key = 'compliance_policy'` 取最新一条，解析 `config_value` JSON → 构造 `CompliancePolicy`。 |
| **版本** | `policy_version` 以 JSON 内 `policy_version` 为准（或与表 `version` 组合，如 `v{version}`），写入审查结果与审计。 |
| **缓存** | 建议内存缓存 + TTL（如 60s）或版本变更时失效，避免每次审查都查库。 |
| **依赖** | config 模块依赖 `pkg.mysql_client`；compliance 依赖 config 获取策略，不直接依赖 MySQL。 |

### 1.4 合规侧“策略来源”可插拔

- 定义 **策略提供方接口**（可选）：例如 `CompliancePolicyProvider` 仅含 `get_policy() -> CompliancePolicy | None`。
- **默认实现**：`config.get_compliance_policy()`；若 T014 未实现则使用 `DEFAULT_POLICY`。
- 编排/API 调用 `check_input`/`check_output` 时，若不传 `policy` 则从 **config 取**（若存在），否则 `DEFAULT_POLICY`。
- 可选：环境变量 `COMPLIANCE_POLICY_SOURCE=mysql|file|memory`，由 config 或 compliance 在启动时选择加载方式；T014 优先实现 `mysql`。

### 1.5 合规专用 LLM 路由（可选）

- 在 `config_value` 或 model_gateway 配置中增加：`compliance_llm_base_url`、`compliance_llm_model`（可留空表示与主 LLM 共用）。
- 合规服务调用 LLM 时：若配置了合规专用端点则用该端点，否则使用现有 `llm_chat`（与 model_gateway 一致）。
- 熔断 key 使用独立 `compliance_llm`，与主对话 LLM 隔离，避免合规审查故障影响主链路。

---

## 二、S2：长度与频率限制、LLM 超时与熔断

### 2.1 输入/输出长度限制

| 项 | 建议 | 说明 |
|----|------|------|
| **输入审查** | 单次 `check_input` 文本最大长度（如 8KB 字符或 2k tokens 估算） | 超长截断并记录日志；避免大文本滥用审查接口。 |
| **输出审查** | 单次 `check_output` 文本 + structured_output 序列化后最大长度（如 32KB） | 同上，截断后审查，并在 decision 中可标注“已截断”。 |
| **配置方式** | 环境变量或 `config_value`：`max_input_length`、`max_output_length` | 默认值写死在 compliance 或 config，可被 MySQL 配置覆盖。 |

### 2.2 审查接口频率限制

| 项 | 建议 | 说明 |
|----|------|------|
| **维度** | 按 `user_id` 限流（与 chat 类似） | 使用现有 `pkg.redis_keys`：`ratelimit:{userId}:chat` 已存在；若需单独限制“合规调用”可新增 scope `ratelimit:{userId}:compliance`。 |
| **策略** | 与 chat 共用或略严（如每分钟 N 次审查） | 由 Redis 限流键 + TTL 实现；compliance 在入口处调用 `ratelimit_incr`，超限返回“请求过于频繁”或直接拒答。 |
| **可选** | 仅对“调用 LLM 的审查”计费/计数，规则审查不计 | 便于成本与风控统计。 |

### 2.3 LLM 审查超时与熔断

| 项 | 建议 | 说明 |
|----|------|------|
| **超时** | 与 model_gateway 一致或略短（如 30s） | 在 `config_value` 中 `llm_timeout_seconds`；调用 `llm_chat` 时传入 timeout（若 gateway 支持），否则在合规侧用 `asyncio.wait_for` 或同步超时包装。 |
| **熔断** | 独立 key `compliance_llm`（或从配置读） | 复用 `model_gateway._circuit`：`is_open("compliance_llm")`、`record_success`/`record_failure`；阈值与 window 可与主 LLM 相同或单独配置。 |
| **降级** | 熔断或超时时：审查结果降级为“规则通过”，并打日志 | 与当前“LLM 异常时降级为通过”一致，保证可用性。 |

---

## 三、S3：Prompt 可配置与审计对接

### 3.1 LLM Prompt 抽成常量或配置

| 项 | 说明 |
|----|------|
| **现状** | 输入/输出审查的 system / user prompt 写在 `compliance/service.py` 内联字符串。 |
| **目标** | 抽成常量或从 config（MySQL/文件）读取，便于合规同学评审与迭代，且不依赖发版。 |
| **实现** | 1）在 `compliance/` 下新增 `prompts.py`，定义默认 `COMPLIANCE_INPUT_SYSTEM_PROMPT`、`COMPLIANCE_OUTPUT_SYSTEM_PROMPT` 及 JSON 格式说明。2）可选：`config_strategy` 中 `config_key = compliance_prompts`，`config_value` 含 `input_system`、`output_system`；compliance 调用时优先用 config，缺失则用代码内常量。 |

### 3.2 审查结果写入审计（与 T012 对接）

| 项 | 说明 |
|----|------|
| **写入内容** | `answerId`、`policy_version`、`complianceDecision`（如 action、reason、suggestion；可存 to_dict() 或精简字段）。 |
| **写入时机** | 输出审查完成后，由编排层或合规层调用 `audit.appendEvent(answerId, event)`；event 中 type 如 `compliance_result`，payload 含 policy_version、decision。 |
| **依赖** | T012 审计服务需提供 `appendEvent(answerId, event)` 或等价接口；compliance 仅返回 decision，由编排层统一落库，或 compliance 接受可选 `audit_callback` 在通过/拒答后回写。 |

### 3.3 与 SSE 和结构化输出的协同约束

| 项 | 说明 |
|----|------|
| **状态事件** | 当进入输入审查/输出审查时，编排层可通过 `status` 事件提示（例如 `compliance_checking`、`compliance_final`），不改变既有前端事件消费模型。 |
| **structuredOutputs 一致性** | 若输出审查触发改写/拒答，需保证 `answerBlocks` 与 `structuredOutputs` 语义一致；必要时清空或重建不合规的结构化片段，避免前端“文本已拒答但图表仍展示原内容”。 |
| **done 兜底** | 即使中途存在 `structured_update`，最终 `done` 仍应回传经过合规处理后的 `structuredOutputs[]`，作为单一可信结果。 |
| **追溯性** | 审计中需关联 `answerId`、`policy_version`、`decision`、是否改写结构化结果，便于排查“展示与审查不一致”问题。 |

---

## 四、实施顺序与任务拆分建议

| 步骤 | 内容 | 归属 |
|------|------|------|
| 1 | **T014 config 模块**：实现从 MySQL `config_strategy` 读取 `compliance_policy`，解析为 `CompliancePolicy`；提供 `get_compliance_policy()`；可选内存缓存+TTL。 | T014 |
| 2 | **Compliance 策略来源**：`check_input`/`check_output` 在未传 `policy` 时调用 config.get_compliance_policy()，若为 None 再用 DEFAULT_POLICY。 | 合规改进 |
| 3 | **S3 Prompt**：抽 prompt 到 `compliance/prompts.py`；可选从 config 读 `compliance_prompts` 覆盖。 | 合规改进 |
| 4 | **S2 长度限制**：在 check_input/check_output 入口做 max_input_length / max_output_length 截断与日志。 | 合规改进 |
| 5 | **S2 频率限制**：审查入口调用 Redis 限流（复用或新增 scope）；超限返回明确错误。 | 合规改进 |
| 6 | **S2 LLM 超时与熔断**：合规 LLM 调用使用独立 key、可配置超时；熔断与 model_gateway 一致。 | 合规改进 / model_gateway |
| 7 | **S3 审计**：编排或合规在输出审查后调用 audit.appendEvent(answerId, { compliance_result })；T012 提供接口。 | T012 + 编排 |

---

## 五、与 tasks.md 的对应

- **T014**：须实现“从 MySQL 加载策略与版本”，即本规划 §1.2、§1.3；合规策略的 config_key、config_value 结构按 §1.2 约定。
- **T012**：审计需支持写入 compliance 结果（§3.2），以便与合规改进同步落地。
- 本规划中“合规改进”部分可在 T011 完成后、T014/T012 并行或之后按步骤 2–7 实现。

---

## 六、配置表示例（MySQL config_strategy）

```sql
-- 示例：插入或更新合规策略（实际由运维/配置平台执行）
INSERT INTO config_strategy (config_key, config_value, version)
VALUES (
  'compliance_policy',
  '{
    "policy_version": "v1",
    "blacklist_keywords": ["保本保息", "稳赚不赔", "承诺收益", "绝对收益"],
    "whitelist_keywords": ["历史收益仅供参考"],
    "enable_llm_input_check": true,
    "enable_llm_output_check": true,
    "max_input_length": 8192,
    "max_output_length": 32768,
    "llm_timeout_seconds": 30,
    "llm_circuit_key": "compliance_llm"
  }',
  1
)
ON DUPLICATE KEY UPDATE config_value = VALUES(config_value), version = version + 1;
```

以上为合规 S1/S2/S3 改进的完整规划，**且明确 T014 config 模块从 MySQL 加载合规策略与版本**。
