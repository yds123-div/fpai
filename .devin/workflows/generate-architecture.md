---
description: 根据 PRD 生成系统架构
---

# 生成架构

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
2. 生成架构文档，包含以下章节：
   - 系统上下文图（Mermaid C4 Context）
   - 架构风格与设计原则
   - 服务/模块划分与边界
   - API 设计概览（RESTful/GraphQL 等）
   - 数据存储选型与数据流
   - 部署架构（容器化/编排）
   - 可观测性（日志、监控、链路追踪）
3. 将结果写入 `.cursor/memory/architecture.md`
