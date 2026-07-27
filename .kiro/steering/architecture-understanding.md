---
inclusion: manual
---
# 架构理解
READ_ARCHITECTURE: |
  File: `.cursor/memory/architecture.md`
  必须解析：
  1. 加载并解析完整的 Mermaid 图
  2. 提取并理解：
     - 模块边界与关系
     - 数据流模式
     - 系统接口
     - 组件依赖
  3. 任何改动都要对照架构约束进行校验
  4. 确保新增代码保持既定的关注点分离（Separation of Concerns）
  5. 当 architecture 与现有代码实现不一致时，先标注“as-is（当前实现）”与“to-be（目标架构）”，再给出更新建议；禁止在未说明差异时直接按旧文档强行约束实现。
  
  错误处理：
  1. 若文件不存在：停止并通知用户
  2. 若图解析失败：请求用户澄清/补充
  3. 若发现架构违背：提示用户风险并给出警告
  4. 若发现文档滞后于代码：优先建议同步更新 `.cursor/memory/architecture.md`、`technical_design.md`、`decisions.md`，并说明受影响段落。