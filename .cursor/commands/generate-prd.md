# 生成 PRD

使用 **product-manager** / **prd-generator** skill。

**输入：** 业务需求（用户提供的业务需求、想法或用户故事）

**输出：**
- 生成完整 PRD（产品需求文档）
- 保存到 `.cursor/memory/prd.md`
- 包含：产品概述、目标用户、用户故事、功能/非功能需求、用户流程、成功指标

**步骤：**
1. 阅读并理解用户输入的业务需求
2. 按 `.cursor/skills/product/prd-generator.md` 的格式生成 PRD
3. 将结果写入 `.cursor/memory/prd.md`
