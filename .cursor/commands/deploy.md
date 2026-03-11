# Deploy（部署 / 发布）

准备或执行部署时使用 **devops-engineer** / **ci-cd-engineer** skill。

**输入：**
- 目标环境：本地 / 开发 / 预发 / 生产（或项目约定名称）
- 可选：`.cursor/memory/architecture.md`、`memory/project_context.md`、现有 CI/CD 配置

**输出：**
- 部署步骤说明或可执行命令（构建、推送、发布、健康检查）
- 若项目尚无部署流程：产出初始部署方案（如 Dockerfile、docker-compose 或 CI 配置片段）并写入合适位置
- 回滚方案简述（如可能）

**步骤：**
1. 读取 `memory/architecture.md`、`memory/project_context.md`（若有），了解部署架构与技术栈
2. 若已有 CI/CD 或脚本：按环境执行对应流程，并确认部署结果
3. 若尚无：根据架构与技术栈起草部署方案（容器化、环境变量、数据库迁移顺序等），并提醒用户配置密钥与环境
4. 部署后：建议做基础冒烟（如健康检查接口、首页可访问）

**注意事项：**
- 不在此处写入真实密钥、生产域名等敏感信息；用占位符或引用「环境变量」
- 重大变更（如数据库 schema）需与 `memory/technical_design.md`、迁移脚本一致

**与流程的关系：**
- 通常在「编码实现」「测试」之后执行
- 首次部署前建议先执行 `run-tests` 并通过
