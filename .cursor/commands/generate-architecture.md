# 生成架构

使用 **system-architect** / **tech-architect** skill。

**输入：**
- 业务需求或已有 `.cursor/memory/prd.md`
- 可选：技术约束、现有系统说明

**输出：**
- 生成系统架构与技术架构
- 保存到 `.cursor/memory/architecture.md`
- 包含：系统上下文、架构风格、微服务、API 设计、数据存储、部署、可观测性
- 使用 Mermaid 绘制架构图

**步骤：**
1. 读取 `.cursor/memory/prd.md`（若存在）
2. 按 `.cursor/skills/architecture/system-architect.md` 与 `tech-architect.md` 的格式输出
3. 将结果写入 `.cursor/memory/architecture.md`
