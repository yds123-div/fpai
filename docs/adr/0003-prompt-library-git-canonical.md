# ADR-0003：业务 prompt 集中到 git 文件库，退役 DB `system_prompt` 字段

- 状态：已接受
- 日期：2026-07-23
- 决策方式：`/grilling` 盘问会话（wayfinder 工单 E1，#10）
- 关联：栅栏 #5（业务 prompt 集中到同一处方便版本管理）；ADR-0001 决策 6（prompt 与校验器共引白名单）

## 上下文

业务 prompt 同时活在两处，运行时 DB 胜出，但只有一处有版本管理：

1. **Python 常量**（git 可追踪）：各 agent 模块的 `DEFAULT_SYSTEM_PROMPT` + `fund_agent_framework.COORDINATOR_DEFAULT_SYSTEM_PROMPT`。coordinator prompt 有 `assert` 把 type 列表绑到 `plan_validation.VALID_TASK_TYPES`（ADR-0001 决策 6 防漂移）。
2. **DB `agent_profiles.system_prompt`**（LONGTEXT，**不在** git）：启动时从 Python 常量 seed（仅填空字段、不覆盖管理员改动），管理 UI 可编辑（`upsert_agent`），运行时 `resolve_agent_overrides` 中 DB 非空则覆盖 Python 默认。无版本管理--管理员在 UI 改了什么、改前是什么，git 里看不到。

栅栏 #5 要「集中到同一处方便版本管理」；DB 字段正是逃逸版本控制的那一处。地图 Notes 说「DB 驱动配置（`agent_profiles`/`skill_profiles`）保留」，但那指 `skill_keys`/`model_id`/`enabled` 这类配置，不含 `system_prompt` 字段本身。

实测 `agent_profiles` 表存在但 **0 行**--override 路径从未在此环境启用，故收口无数据风险。

## 决策

1. **单一权威源 = git 纯文本文件**：`backend/agents/prompts/<agent_key>.md` 集中存放；启动时薄 loader 读一次进内存（缺文件即启动失败，fail-fast），缓存复用。prompt 是静态串（动态数据走 user message），不用模板引擎。
2. **版本管理 = git**：diff / review / rollback 即版本管理。不加显式 prompt 版本号--无消费者（业务评测 out-of-scope，Opik 暂停且在本 map 之外）。若 Opik 迁移后恢复，届时再捕获 git SHA。
3. **砍掉运行时 prompt override**：管理 UI 的 prompt 编辑器移除；`resolve_agent_overrides` 不再读 `system_prompt`，收窄为仅 `model_id` 覆盖。
4. **DROP `agent_profiles.system_prompt` 列**：schema 迁移直接删列。`agent_profiles` 表本身保留（`skill_keys`/`model_id`/`enabled` 即「DB 驱动配置」，符合地图契约），只退役 prompt 列。清理 `agent_store.py`、`api/routes/agents.py`、`runtime.py` 中所有引用 `system_prompt` 的 SQL 与代码。
5. **coordinator 防漂移 `assert` 迁到测试**：`tests/test_prompt_drift.py` 加载 prompt 文件校验 type 列表 == `VALID_TASK_TYPES`。import 时断言降级为测试时检查（启动不再对这一项 fail-fast，但漂移仍被 CI 拦）。

## 后果

正面：prompt 单一权威源，git 版本管理；prompt-only diff，非开发（合规/领域专家）能独立 review prompt 改动--金融产品 + 栅栏 #4 审计下这是实打实的好处；与「DB 驱动配置保留」契约不冲突（表在、配置在，只去 prompt 列）。

负面/代价：改 prompt 需发版，失去线上热修能力（用户明确接受）；coordinator 防漂移从 import 时降到测试时；需写 loader + 清理多处 SQL 引用；`_seed_builtin_agents` 不再写 `system_prompt`（seed 逻辑收窄为 name/enabled/skill_keys/model_id）。

边界：coordinator prompt 是否进库依赖 G2 / 栅栏 #2（plan-JSON 弃用后 coordinator 的命运），不在 E1 决定；E1 定义机制并迁移当前 prompt，coordinator prompt 去留随 G2 落定。

## 备选方案（已否决）

- **Python 常量集中到单模块**：保留 import 时 `assert`、零 loader、零文件 IO。否决--prompt 仍是 Python 三引号串、混在 `.py` 里，非开发 review 困难；金融场景需合规可独立 review。
- **DB 为权威 + git 迁移文件**（类 Django migration）：单一源在 DB，管理 UI 改的是真值。否决--迁移纪律对 prompt 微调过重，runtime UI 改动逃逸迁移历史，版本管理弱于纯 git。
- **git 规范 + DB override 槽**（空=用默认，非空=热修）：保留热修。否决--仍是两处、override 漂移风险还在；用户明确砍 override。
- **保留列不读**（dead column）：零 schema 风险。否决--0 行无数据风险，迁移重写期宜清理，留 dead column 反而误导后续读者。
