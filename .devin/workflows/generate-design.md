---
description: 根据 PRD 和架构生成技术设计
---

# 生成设计

**输入：**
- `.cursor/memory/prd.md`、`.cursor/memory/architecture.md`
- 需要设计的范围（API / 数据模型 / 模块划分）

**输出：**
- 技术设计文档（API 契约、数据模型、模块结构等）
- 保存到 `.cursor/memory/technical_design.md`
- 重要技术决策追加到 `.cursor/memory/decisions.md`

**步骤：**
1. 读取 memory 中的 prd 与 architecture
2. 按设计类型生成设计文档：
   - API 设计：端点、请求/响应格式、状态码、鉴权
   - 数据模型：实体关系图（Mermaid ERD）、字段定义、索引
   - 模块结构：目录组织、依赖关系、接口定义
3. 写入 `.cursor/memory/technical_design.md`
4. 重要技术决策（选型理由、trade-off）追加到 `.cursor/memory/decisions.md`
