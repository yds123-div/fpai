# 多模态输出实施计划（方案 A）

## 文档信息

- **创建日期**：2026-04-10
- **方案选择**：方案 A - 纯结构化 JSON
- **预计工期**：6-9 天
- **状态**：待开始

---

## 阶段 0：需求分析与架构设计（1天）

### 0.1 需求明确

**输出目标**：
- 将纯文本基金分析转换为结构化 JSON 输出
- 前端渲染为表格、图表、卡片等多模态形式

**核心功能**：
1. 单只基金解读（cards + sections + charts）
2. 基金对比（对比表格 + 对比图表）
3. 兜底机制（纯文本展示）

**数据类型**：
- **卡片**：基本信息、费率、核心表现
- **表格**：业绩对比、费率对比
- **图表**：环形图（资产配置）、折线图（净值走势）、雷达图（风格对比）

### 0.2 整体架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    前端展示层                              │
│  FundAnalysis.vue (主容器)                                │
│    ├─ InfoCard.vue (卡片)                                │
│    ├─ TableSection.vue (表格)                            │
│    ├─ TextSection.vue (文本)                             │
│    └─ ChartRenderer.vue (图表)                           │
└─────────────────────────────────────────────────────────┘
                          ↑
                    JSON 数据流
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    数据转换层                              │
│  fund_formatter.py (格式化工具)                           │
│    ├─ format_fund_cards()                                │
│    ├─ format_performance_table()                         │
│    ├─ format_asset_chart()                               │
│    └─ format_nav_chart()                                 │
└─────────────────────────────────────────────────────────┘
                          ↑
                    原始数据
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    Agent 层                               │
│  ProductInterpretAgent (单只基金)                         │
│  ProductCompareAgent (基金对比)                           │
└─────────────────────────────────────────────────────────┘
```

### 0.3 模块边界定义

**后端模块**：

1. **fund_formatter.py**：数据转换工具（独立模块）
   - 输入：原始基金数据（dict）
   - 输出：结构化 JSON（符合前端接口）
   - 职责：数据清洗、格式转换、默认值处理

2. **ProductInterpretAgent**：单只基金解读
   - 输入：基金代码 + 用户问题
   - 输出：结构化 JSON（mode="single"）
   - 职责：调用 LLM 生成分析 + 调用 formatter 格式化

3. **ProductCompareAgent**：基金对比
   - 输入：多个基金代码 + 用户问题
   - 输出：结构化 JSON（mode="compare"）
   - 职责：调用 LLM 生成对比分析 + 调用 formatter 格式化

**前端模块**：

1. **fundAnalysisParser.ts**：解析工具
   - 输入：Agent 返回的字符串
   - 输出：FundAnalysisOutput 对象 或 null
   - 职责：JSON 解析、类型校验

2. **FundAnalysis.vue**：主容器
   - 输入：FundAnalysisOutput 对象
   - 输出：渲染完整的分析页面
   - 职责：布局、组件编排

3. **InfoCard.vue**：卡片组件
   - 输入：InfoCard 对象
   - 输出：渲染单个卡片
   - 职责：卡片样式、数据展示

4. **TableSection.vue**：表格组件
   - 输入：TableSection 对象
   - 输出：渲染对比表格
   - 职责：表格渲染、高亮处理

5. **ChartRenderer.vue**：图表组件
   - 输入：ChartConfig 对象
   - 输出：渲染 ECharts 图表
   - 职责：图表初始化、配置转换、响应式更新

**任务清单**：
- [ ] 完成需求文档评审
- [ ] 完成架构设计评审
- [ ] 确认模块边界和接口定义

---

## 阶段 1：后端数据转换层（2-3天）

### 1.1 创建 TypeScript 类型定义（0.5天）

**目标**：定义前后端共享的数据接口

**任务清单**：
- [ ] 创建 `backend/pkg/types.py`（Python 类型定义）
- [ ] 创建 `frontend/src/types/fundAnalysis.ts`（TypeScript 类型定义）
- [ ] 定义核心接口：
  - [ ] `FundAnalysisOutput`
  - [ ] `InfoCard`
  - [ ] `AnalysisSection`（TableSection、TextSection）
  - [ ] `ChartConfig`
- [ ] 添加完整的字段注释
- [ ] 创建示例数据

**验收标准**：
- ✅ Python 和 TypeScript 类型定义一致
- ✅ 所有字段都有明确的类型和注释
- ✅ 包含完整的示例数据

**相关文件**：
- `backend/pkg/types.py`（新建）
- `frontend/src/types/fundAnalysis.ts`（新建）

---

### 1.2 创建数据转换工具（1天）

**目标**：将原始基金数据转换为结构化 JSON

**任务清单**：
- [ ] 创建 `backend/pkg/fund_formatter.py`
- [ ] 实现 `format_fund_cards()`：生成卡片数据
  - [ ] 基本信息卡片
  - [ ] 费率卡片
  - [ ] 核心表现卡片
- [ ] 实现 `format_performance_table()`：生成业绩对比表格
- [ ] 实现 `format_fee_table()`：生成费率对比表格
- [ ] 实现 `format_asset_chart()`：生成资产配置环形图
- [ ] 实现 `format_nav_chart()`：生成净值走势折线图
- [ ] 实现 `format_style_radar()`：生成风格雷达图
- [ ] 添加数据缺失处理（优雅降级）
- [ ] 添加单元测试

**验收标准**：
- ✅ 所有函数都有完整的类型注解
- ✅ 处理缺失数据（优雅降级）
- ✅ 单元测试覆盖率 > 80%
- ✅ 输出 JSON 符合前端接口定义

**相关文件**：
- `backend/pkg/fund_formatter.py`（新建）
- `tests/test_fund_formatter.py`（新建）

---

### 1.3 修改 ProductInterpretAgent（0.5天）

**目标**：输出结构化 JSON（单只基金）

**任务清单**：
- [ ] 修改 `backend/agents/fund_agent/product_interpret/agent.py`
- [ ] 导入 `fund_formatter` 模块
- [ ] 调用 `fund_formatter` 生成结构化数据
- [ ] 更新 LLM Prompt（引导输出 JSON）
- [ ] 添加 JSON 校验和修复逻辑
- [ ] 保留纯文本兜底机制
- [ ] 添加日志记录

**验收标准**：
- ✅ 输出 JSON 格式正确
- ✅ LLM 输出不规范时能自动修复
- ✅ 修复失败时降级为纯文本
- ✅ 日志记录完整

**相关文件**：
- `backend/agents/fund_agent/product_interpret/agent.py`（修改）

---

### 1.4 修改 ProductCompareAgent（0.5天）

**目标**：输出结构化 JSON（基金对比）

**任务清单**：
- [ ] 修改 `backend/agents/fund_agent/product_compare/agent.py`
- [ ] 导入 `fund_formatter` 模块
- [ ] 调用 `fund_formatter` 生成对比数据
- [ ] 更新 LLM Prompt（引导输出对比 JSON）
- [ ] 添加 JSON 校验和修复逻辑
- [ ] 保留纯文本兜底机制
- [ ] 添加日志记录

**验收标准**：
- ✅ 输出 JSON 格式正确（mode="compare"）
- ✅ 对比表格数据完整
- ✅ 对比图表配置正确
- ✅ 日志记录完整

**相关文件**：
- `backend/agents/fund_agent/product_compare/agent.py`（修改）

---

### 1.5 后端集成测试（0.5天）

**任务清单**：
- [ ] 创建 `tests/test_fund_formatter.py`
- [ ] 创建 `tests/test_product_interpret_structured.py`
- [ ] 创建 `tests/test_product_compare_structured.py`
- [ ] 测试正常流程
- [ ] 测试边界情况（缺失数据、异常输入）
- [ ] 测试 JSON 校验和修复
- [ ] 测试兜底机制

**验收标准**：
- ✅ 所有测试通过
- ✅ 覆盖正常流程和异常流程
- ✅ 测试覆盖率 > 80%

**相关文件**：
- `tests/test_fund_formatter.py`（新建）
- `tests/test_product_interpret_structured.py`（新建）
- `tests/test_product_compare_structured.py`（新建）

---

## 阶段 2：前端渲染组件（2-3天）

### 2.1 创建解析工具（0.5天）

**目标**：解析后端返回的 JSON

**任务清单**：
- [ ] 创建 `frontend/src/utils/fundAnalysisParser.ts`
- [ ] 实现 `parseFundAnalysis()`：解析 JSON
- [ ] 实现 `validateFundAnalysis()`：校验数据完整性
- [ ] 添加错误处理
- [ ] 添加单元测试

**验收标准**：
- ✅ 能正确解析合法 JSON
- ✅ 能处理非法 JSON（返回 null）
- ✅ 能校验数据完整性
- ✅ 单元测试通过

**相关文件**：
- `frontend/src/utils/fundAnalysisParser.ts`（新建）
- `frontend/src/utils/__tests__/fundAnalysisParser.test.ts`（新建）

---

### 2.2 创建卡片组件（0.5天）

**目标**：渲染置顶卡片

**任务清单**：
- [ ] 创建 `frontend/src/components/fund/InfoCard.vue`
- [ ] 实现基本信息卡片样式
- [ ] 实现费率卡片样式
- [ ] 实现核心表现卡片样式
- [ ] 实现风险卡片样式
- [ ] 添加响应式布局
- [ ] 添加动画效果

**验收标准**：
- ✅ 卡片样式美观
- ✅ 支持不同类型卡片（basic、fee、performance、risk）
- ✅ 移动端适配
- ✅ 动画流畅

**相关文件**：
- `frontend/src/components/fund/InfoCard.vue`（新建）

---

### 2.3 创建表格组件（0.5天）

**目标**：渲染对比表格

**任务清单**：
- [ ] 创建 `frontend/src/components/fund/TableSection.vue`
- [ ] 实现表格渲染
- [ ] 实现高亮列功能
- [ ] 实现排序功能（可选）
- [ ] 添加响应式布局（移动端横向滚动）
- [ ] 添加样式优化

**验收标准**：
- ✅ 表格样式清晰
- ✅ 高亮列明显
- ✅ 移动端可横向滚动
- ✅ 排序功能正常（如果实现）

**相关文件**：
- `frontend/src/components/fund/TableSection.vue`（新建）

---

### 2.4 创建文本组件（0.5天）

**目标**：渲染文本模块

**任务清单**：
- [ ] 创建 `frontend/src/components/fund/TextSection.vue`
- [ ] 实现文本渲染
- [ ] 实现标签展示（风险提示、专家观点）
- [ ] 添加 Markdown 支持（可选）
- [ ] 添加样式优化

**验收标准**：
- ✅ 文本排版清晰
- ✅ 标签样式明显
- ✅ Markdown 渲染正常（如果实现）

**相关文件**：
- `frontend/src/components/fund/TextSection.vue`（新建）

---

### 2.5 创建图表组件（1天）

**目标**：渲染 ECharts 图表

**任务清单**：
- [ ] 安装 ECharts：`npm install echarts`
- [ ] 创建 `frontend/src/components/fund/ChartRenderer.vue`
- [ ] 实现环形图渲染（资产配置）
- [ ] 实现折线图渲染（净值走势）
- [ ] 实现雷达图渲染（风格对比）
- [ ] 实现柱状图渲染（可选）
- [ ] 添加图表交互（tooltip、legend）
- [ ] 添加响应式更新
- [ ] 添加加载状态
- [ ] 添加错误处理

**验收标准**：
- ✅ 三种图表都能正确渲染
- ✅ 图表交互流畅
- ✅ 响应式更新正常
- ✅ 加载状态友好
- ✅ 错误处理完善

**相关文件**：
- `frontend/src/components/fund/ChartRenderer.vue`（新建）

---

### 2.6 创建主容器组件（0.5天）

**目标**：组装所有子组件

**任务清单**：
- [ ] 创建 `frontend/src/components/fund/FundAnalysis.vue`
- [ ] 实现布局（Grid + Flexbox）
- [ ] 集成所有子组件
- [ ] 添加兜底展示（纯文本）
- [ ] 添加加载状态
- [ ] 添加错误状态
- [ ] 添加空状态

**验收标准**：
- ✅ 布局美观
- ✅ 组件编排合理
- ✅ 兜底机制正常
- ✅ 各种状态展示友好

**相关文件**：
- `frontend/src/components/fund/FundAnalysis.vue`（新建）

---

### 2.7 集成到聊天界面（0.5天）

**目标**：在聊天界面中展示结构化输出

**任务清单**：
- [ ] 修改 `frontend/src/views/ChatView.vue`
- [ ] 检测消息类型（结构化 vs 纯文本）
- [ ] 渲染 `FundAnalysis.vue` 或纯文本
- [ ] 添加样式调整
- [ ] 添加过渡动画

**验收标准**：
- ✅ 能正确识别结构化输出
- ✅ 结构化输出和纯文本都能正常展示
- ✅ 样式与聊天界面协调
- ✅ 过渡动画流畅

**相关文件**：
- `frontend/src/views/ChatView.vue`（修改）

---

## 阶段 3：优化与完善（1-2天）

### 3.1 响应式布局优化（0.5天）

**任务清单**：
- [ ] 优化移动端布局
- [ ] 添加断点适配（手机、平板、桌面）
- [ ] 优化图表在小屏幕上的展示
- [ ] 优化表格在小屏幕上的展示
- [ ] 测试不同设备

**验收标准**：
- ✅ 在不同设备上都能正常展示
- ✅ 移动端体验流畅
- ✅ 无横向滚动（除表格外）

**相关文件**：
- 所有前端组件（修改）

---

### 3.2 图表交互优化（0.5天）

**任务清单**：
- [ ] 添加图表点击事件
- [ ] 添加图表缩放功能
- [ ] 添加图表导出功能（PNG）
- [ ] 添加图表全屏功能
- [ ] 优化 tooltip 展示

**验收标准**：
- ✅ 图表交互丰富
- ✅ 导出功能正常
- ✅ 全屏功能正常
- ✅ tooltip 展示友好

**相关文件**：
- `frontend/src/components/fund/ChartRenderer.vue`（修改）

---

### 3.3 数据导出功能（0.5天）

**任务清单**：
- [ ] 添加导出 PDF 功能
- [ ] 添加导出 Excel 功能（表格数据）
- [ ] 添加导出图片功能（整个分析页面）
- [ ] 添加导出按钮
- [ ] 添加导出进度提示

**验收标准**：
- ✅ 能导出完整的分析报告
- ✅ 导出格式正确
- ✅ 导出进度提示友好

**相关文件**：
- `frontend/src/components/fund/FundAnalysis.vue`（修改）
- `frontend/src/utils/exportUtils.ts`（新建）

---

### 3.4 性能优化（0.5天）

**任务清单**：
- [ ] 图表懒加载（IntersectionObserver）
- [ ] 虚拟滚动（长列表，如果需要）
- [ ] 图片压缩（导出时）
- [ ] 代码分割（动态导入）
- [ ] 添加性能监控

**验收标准**：
- ✅ 页面加载速度快
- ✅ 滚动流畅
- ✅ 内存占用合理

**相关文件**：
- 所有前端组件（修改）

---

### 3.5 错误处理与兜底（0.5天）

**任务清单**：
- [ ] 添加数据缺失处理
- [ ] 添加图表渲染失败处理
- [ ] 添加网络错误处理
- [ ] 完善纯文本兜底
- [ ] 添加错误上报

**验收标准**：
- ✅ 各种异常情况都有友好提示
- ✅ 不会出现白屏或崩溃
- ✅ 错误上报正常

**相关文件**：
- 所有前端组件（修改）
- `frontend/src/utils/errorHandler.ts`（新建）

---

## 阶段 4：测试与上线（1天）

### 4.1 端到端测试（0.5天）

**任务清单**：
- [ ] 测试单只基金解读流程
- [ ] 测试基金对比流程
- [ ] 测试各种边界情况
- [ ] 测试不同设备和浏览器
- [ ] 测试性能（加载速度、内存占用）
- [ ] 测试兼容性

**验收标准**：
- ✅ 所有功能正常
- ✅ 无明显 bug
- ✅ 性能达标
- ✅ 兼容性良好

**相关文件**：
- `tests/e2e/fund_analysis.spec.ts`（新建）

---

### 4.2 文档更新（0.5天）

**任务清单**：
- [ ] 更新 API 文档
- [ ] 更新前端组件文档
- [ ] 更新部署文档
- [ ] 记录架构决策（ADR）
- [ ] 更新 README

**验收标准**：
- ✅ 文档完整清晰
- ✅ 新人能快速上手
- ✅ ADR 记录完整

**相关文件**：
- `docs/api.md`（修改）
- `docs/frontend_components.md`（新建）
- `docs/deployment.md`（修改）
- `.kiro/steering/decisions.md`（修改）
- `README.md`（修改）

---

## 总结

### 关键里程碑

- **Day 1**：需求分析与架构设计完成 ✅
- **Day 2-4**：后端数据转换层完成
- **Day 5-7**：前端渲染组件完成
- **Day 8-9**：优化与测试完成

### 风险点与应对策略

| 风险点 | 影响 | 应对策略 |
|--------|------|----------|
| LLM 输出不稳定 | 高 | 严格的 JSON 校验和修复 + 纯文本兜底 |
| 数据缺失 | 中 | 优雅降级 + 默认值处理 |
| 图表性能 | 中 | 懒加载 + 虚拟滚动 + 代码分割 |
| 浏览器兼容性 | 低 | 使用成熟的库（ECharts）+ 兼容性测试 |

### 技术栈

- **后端**：Python 3.9+ + JSON 序列化
- **前端**：Vue 3 + TypeScript + ECharts
- **样式**：CSS Grid + Flexbox
- **测试**：Pytest + Vitest

### 相关文档

- [多模态输出设计文档](./multimodal_output_design.md)
- [架构决策记录](./.kiro/steering/decisions.md)
- [模块索引](./.cursor/memory/module_index.md)

---

## 进度跟踪

| 阶段 | 状态 | 开始日期 | 完成日期 | 备注 |
|------|------|----------|----------|------|
| 阶段 0：需求分析与架构设计 | ⏳ 待开始 | - | - | - |
| 阶段 1：后端数据转换层 | ⏳ 待开始 | - | - | - |
| 阶段 2：前端渲染组件 | ⏳ 待开始 | - | - | - |
| 阶段 3：优化与完善 | ⏳ 待开始 | - | - | - |
| 阶段 4：测试与上线 | ⏳ 待开始 | - | - | - |

---

## 下一步行动

1. ✅ 完成实施计划文档
2. ⏳ 开始阶段 0：需求分析与架构设计
3. ⏳ 开始阶段 1.1：创建类型定义

---

**最后更新**：2026-04-10
