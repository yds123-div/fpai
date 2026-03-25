# 产品推荐 Skill（数据获取）

## 目标

为“产品推荐/根据客户画像推荐产品及推荐原因”类问题提供结构化候选产品数据（含稳定性、安全性与流动性线索），供上层大模型生成最终自然语言推荐。

## 输入

- `question`: 用户问题（建议包含“客户画像”文本，以及期望推荐数量字段，如 `目标推荐数量：3`）
- `ctx`: 上下文（目前仅透传，主要用于兼容框架）

## 输出（JSON 字符串）

- `ok: bool`
- `mode = "recommend_candidates"`
- `recommend_count: int`（推荐数量）
- `target_allocation: {wealth: number, bond: number, hybrid: number}`（画像偏好权重，取值 0~1）
- `selected_candidates[]`（最终选出的候选产品，长度尽量等于 `recommend_count`）

`selected_candidates[]` 内字段：

- `category: "wealth"|"bond"|"hybrid"`
- `symbol: string`（基金代码）
- `name: string`
- `score: number`（综合评分：稳定性优先）
- `return_horizon_pct: number|null`（来自基金排行的近期收益近似指标）
- `profit_probability`: `{ok, sample}`（来自 `fund_individual_profit_probability_xq` 的稳定性/胜率样本）
- `basic_info`: `{ok, extracted}`（来自 `fund_individual_basic_info_xq` 的基础安全/流动性线索）
- `name_keyword_tags[]`：用于解释分类的名称关键字标签

## 需要的 AkShare 接口

为了贴合“稳健型、保守型偏好 + 重视安全与流动性”的画像，Skill 主要使用：

1. `ak.fund_open_fund_rank_em`：拉取基金排行候选与收益近似指标
2. `ak.fund_individual_profit_probability_xq`：获取盈亏概率/胜率等稳定性参考
3. `ak.fund_individual_basic_info_xq`：获取风险等级、申赎状态等安全/流动性线索

## 说明

- “低风险/稳健”在本 Skill 中通过“胜率/盈亏概率 + 风险等级（若可解析）”做近似，不等同于最大回撤/波动率等严格风险指标。
- AkShare 字段结构可能随版本变化；本 Skill 采用模块级降级：单接口失败不影响其它接口字段输出。

