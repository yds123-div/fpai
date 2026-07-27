---
inclusion: manual
---
每次进行 Plan/Architect（规划/架构）类任务之前，始终先做三件事：
a. 阅读 `.cursor/memory/` 中已有文档：i. `.cursor/memory/architecture.md`、ii. `.cursor/memory/prd.md`、iii. `.cursor/memory/technical_design.md`
b. 阅读 `.cursor/memory/tasks.md` 中的计划与任务规划
c. 阅读 `.cursor/memory/project_context.md`中的项目上下文 
d. 从 `src` 及其它位置的代码文件中获取所需的方案上下文
---
# Below is the Planning Workflow to follow:

1. 理解需求（UNDERSTAND the REQUIREMENTS）：
<CLARIFICATION>
- 始终提出澄清问题与追问。
- 识别描述不充分的需求并索取更详细的信息。
- 全面理解问题各方面并收集细节，使问题表述尽可能精准清晰。
- 对需要做出的假设进行追问，消除所有歧义与不确定性。
- 提出我可能没想到的方案/细节，即预判我的需求与需要补充的约束。
- 只有在 100% 清晰且有把握后，才进入 SOLUTION 阶段。
</CLARIFICATION>

2. 构建解决方案（FORMULATING the SOLUTION）：
<STEP BY STEP REASONING>
<DECOMPOSE>
- 为解决方案先建立一个“元架构（meta architecture）”层面的总体规划。
- 将问题拆分为关键概念与更小的子问题。
</DECOMPOSE>
a. 思考所有可能的解决路径。
b. 建立评估标准与取舍维度，用于衡量不同方案的优劣。
c. 找到最优方案，并明确其最优的依据以及相关 trade-offs。

<MULTI ATTEMPTS>
a. 严格推导并论证方案的最优性。
b. 质疑每一个假设与推断，并用充分的推理支撑它们。
c. 尝试组合不同方案的优势，寻找比当前方案更优的解法。
d. 重复 <MULTI ATTEMPTS> 的过程：不断细化与融合不同方案，直到得到一个强健方案。
e. 如有需要可使用 <WEB USE> 做进一步调研。
</MULTI ATTEMPTS>
</STEP BY STEP REASONING>

3. 方案校验（SOLUTION VALIDATION）：

<REASONING PRESENTATION>
- 尽可能详细地给出 PLAN。
- 将方案按步骤拆解，并把每一步都想清楚、讲清楚。
- 相对其它可行方案，论证该方案的最优性。
- 明确写出所有假设、选择与决策。
- 解释方案中的 trade-offs。
- 必要时在给出方案后，用你自己的话复述我的问题，确保对齐。
</REASONING PRESENTATION>
- 在实施前，先验证 <REASONING PRESENTATION> 输出的解决方案计划。

---
# Features of the Plan:
1. 计划应具备以下特性：
a. `extendable`（可扩展）：后续代码可以在该计划上容易地继续构建，并能良好支持未来扩展；预判未来功能，使计划可适配。
b. `detailed`（详细）：计划需足够细，覆盖所有受影响的方面以及可能的影响方式。
c. `robust`（健壮）：考虑错误场景与失败情况，并为可能的失败提供回退方案。
d. `accurate`（准确）：各部分相互一致；每个组件与接口定义正确且可对接。
---

每次 Plan/Architect 任务结束后，始终做两件事：
a. 将计划写入现有文档并更新 `.cursor/memory/` 下文件：i. `.cursor/memory/architecture.md`、ii. `.cursor/memory/prd.md`、iii. `.cursor/memory/technical_design.md`
b. 将计划与相关任务规划记录到 `.cursor/memory/tasks.md` 下文件，与项目上下文相关的记录到 `.cursor/memory/project_context.md`