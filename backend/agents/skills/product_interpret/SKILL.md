## Product Interpret (Fund Deep Fetch) Skill

该 skill 用于“产品解析/基金解读/适不适合/风险点/持仓行情”等问题的数据获取。

### 输入
- `question`: 用户问题（可能包含 6 位基金代码）
- `ctx`: 上下文（透传，当前用于从会话历史中回填基金代码）

### 输出（JSON 字符串）
- `mode = "single"`：按单只/近似单只解析，最多取前 3 只
- `symbols`: 本次解析到的基金代码数组
- `funds[]`: 每只基金的结构化数据

`funds[]` 内字段（均为 `{ok: bool, data: ...}` 或 `{ok:false, message:...}`）：
- `basic_info`: `fund_individual_basic_info_xq`
- `achievement`: `fund_individual_achievement_xq`
- `analysis`: `fund_individual_analysis_xq`
- `profit_probability`: `fund_individual_profit_probability_xq`
- `detail_hold`: `fund_individual_detail_hold_xq`（持仓行情/持仓明细）
- `detail_info`: `fund_individual_detail_info_xq`
- `risk`: `profit_probability` 的快速索引

### 说明
- AkShare 接口可能因版本/数据源变动导致字段或返回结构不同；本 skill 采用模块级降级，单模块失败不影响其它模块。
- 你可以在 `agents/product_interpret`（基金分析智能体）配置其 `skill_keys` 使用本 skill，或通过后台 `POST /skills` 导入 builtin/custom skill。

