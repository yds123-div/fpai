# 生成设计

按需使用 **api-designer** / **database-designer** / **data-model-designer** / **module-designer** skill。

**输入：**
- `.cursor/memory/prd.md`、`.cursor/memory/architecture.md`
- 需要设计的范围（API / 数据模型 / 模块划分）

**输出：**
- 技术设计文档（API 契约、数据模型、模块结构等）
- 保存到 `.cursor/memory/technical_design.md`
- 重要技术决策追加到 `.cursor/memory/decisions.md`

**步骤：**
1. 读取 memory 中的 prd 与 architecture
2. 按设计类型选用对应 design skill 生成设计
3. 写入 `.cursor/memory/technical_design.md`，决策写入 `decisions.md`
