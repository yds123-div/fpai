# Bugfix Requirements Document

## Introduction

用户在 AI 对话页面提问后，模型的思考过程（`<think>...</think>` 内容）没有实时显示出来；
刷新页面后思考过程才出现，且刷新后显示的内容与流式输出时的内容不一致。

该 Bug 涉及两个独立缺陷：
1. **流式阶段**：thinking 内容未实时渲染到折叠面板
2. **持久化阶段**：thinking 内容未被保存，刷新后无法正确恢复

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户发送问题且后端以 SSE `message_delta` 事件推送含 `<think>...</think>` 的文本片段时，THEN 系统将 thinking 内容追加到 `streamingRaw`，但折叠面板（`<details>`）不实时更新显示

1.2 WHEN 后端编排器模式下 `stream_callback` 未被 agent 调用（无 `message_delta` 事件），仅在 `done` 事件的 `answerBlocks` 中返回完整文本时，THEN 系统在流式阶段不显示任何 thinking 内容

1.3 WHEN `done` 事件触发后，系统将 `answerBlocks[0]`（已经过 `_strip_think_blocks` 剥离 thinking 的纯文本）存入 MySQL `messages.content_summary` 时，THEN 系统丢失了 thinking 内容，无法持久化

1.4 WHEN 用户刷新页面，系统从 `content_summary` 恢复历史消息时，THEN 系统对 assistant 消息调用 `splitThink(content_summary)`，但 content_summary 中已无 `<think>` 标签，导致 `thinking` 字段为空

1.5 WHEN 刷新后显示的内容与流式阶段显示的内容不一致时，THEN 系统展示的是 `answerBlocks`（剥离 thinking 后的纯文本），而流式阶段展示的是 `streamingRaw`（含 thinking 的原始文本）

### Expected Behavior (Correct)

2.1 WHEN 后端以 SSE `message_delta` 事件推送含 `<think>...</think>` 的文本片段时，THEN 系统 SHALL 实时将 thinking 部分渲染到折叠面板，将正文部分渲染到消息内容区

2.2 WHEN 后端编排器模式下仅通过 `done` 事件的 `answerBlocks` 返回完整文本时，THEN 系统 SHALL 在 `done` 事件处理时解析 thinking 并补充显示到折叠面板

2.3 WHEN `done` 事件触发，系统持久化 assistant 消息时，THEN 系统 SHALL 将含 `<think>...</think>` 的原始完整文本（或分别存储 thinking 与 answer）保存到 `content_summary`，确保 thinking 内容不丢失

2.4 WHEN 用户刷新页面，系统从 `content_summary` 恢复历史消息时，THEN 系统 SHALL 能正确解析出 thinking 字段并在折叠面板中展示

2.5 WHEN 流式阶段结束后，THEN 系统 SHALL 保证刷新后显示的 thinking 内容与流式阶段显示的内容完全一致

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户发送问题且模型不输出 `<think>` 内容时，THEN 系统 SHALL CONTINUE TO 正常显示回答，不出现空白折叠面板

3.2 WHEN 用户发送问题且后端正常推送 `message_delta` 事件时，THEN 系统 SHALL CONTINUE TO 实时流式显示正文内容

3.3 WHEN `done` 事件触发时，THEN 系统 SHALL CONTINUE TO 正确处理 citations、suggestedQuestions、fundAnalysis 等字段

3.4 WHEN 用户刷新页面时，THEN 系统 SHALL CONTINUE TO 从 sessionId 恢复历史对话消息列表

3.5 WHEN 后端返回结构化输出（fundAnalysis）时，THEN 系统 SHALL CONTINUE TO 正确渲染基金分析组件

3.6 WHEN 合规检查拦截输入时，THEN 系统 SHALL CONTINUE TO 返回合规提示，不受 thinking 显示逻辑影响
