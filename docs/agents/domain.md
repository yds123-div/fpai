# 领域文档

工程类 skill 在探索代码库时，应如何消费本仓库的领域文档。

## 探索之前，先读这些

- 仓库根目录的 **`CONTEXT.md`**；或者
- 如果根目录存在 **`CONTEXT-MAP.md`**——它指向每个上下文各自的 `CONTEXT.md`，阅读与主题相关的那些。
- **`docs/adr/`**——阅读涉及你即将动手区域的 ADR。在多上下文仓库中，还要检查 `src/<上下文>/docs/adr/` 里的上下文级决策。

如果这些文件不存在，**静默继续**。不要指出它们缺失；不要主动建议提前创建。`/domain-modeling` skill（经由 `/grill-with-docs` 和 `/improve-codebase-architecture` 触达）会在术语或决策真正得到解决时惰性创建它们。

## 文件结构

单上下文仓库（大多数仓库）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多上下文仓库（根目录存在 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 上下文级决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用词汇表中的术语

当你的输出命名一个领域概念时（在 issue 标题、重构提案、假设、测试名中），使用 `CONTEXT.md` 中定义的术语。不要漂移到词汇表明确避免的同义词。

如果你需要的概念还不在词汇表里，这是一个信号——要么你在发明项目并不使用的语言（重新考虑），要么确实存在缺口（记下来交给 `/domain-modeling`）。

## 指出 ADR 冲突

如果你的输出与现有 ADR 矛盾，要显式指出，而不是默默覆盖：

> *与 ADR-0007（事件溯源订单）矛盾——但值得重新讨论，因为……*
