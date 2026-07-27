本目录用于沉淀「产品对比 Agent」的可复用 skill 资产，便于后续：

- 维护提示词（system prompt / few-shot）
- 定义工具调用规范（输入/输出契约、参数校验、错误处理）
- 抽象成可测试的能力模块（便于单测与回归）

约定（建议）：

- `prompt.txt`：产品对比 Agent 的 system prompt（纯文本，不要 markdown 强调符号）
- `tools.md`：产品对比 Agent 可用工具清单与契约说明
- `runtime.py`：对外暴露一个 `run(question, ctx)` 的执行入口（后续接入）

你把具体 skill 内容发我后，我会按以上约定落文件并接入到 `ProductCompareAgent`。

