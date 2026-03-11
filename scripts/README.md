# 脚本（迁移、运维、离线任务）

## MySQL 迁移（T004 + 用户表）

- **001_initial_mysql_tables.sql**：`schema_migrations`、`sessions`、`messages`、`config_strategy`、`faq`、`feedback`、`audit_index`。依据 technical_design §4.1。
- **002_users_table.sql**：`users` 表（账号、密码哈希、姓名、工号、邮箱）；支持账号+密码登录，各表 `user_id` 业务上关联 `users.id`。

- **运行迁移**（需配置 `backend/.env` 中 `MYSQL_*`）：
  ```bash
  # 从项目根执行
  python scripts/run_migrations.py
  ```
  会按版本号顺序执行 `migrations/*.sql`，已应用版本记录在 `schema_migrations` 表中，不会重复执行。

- **手动执行**：也可用 MySQL 客户端执行 `migrations/001_initial_mysql_tables.sql`，表结构自包含。

冷热分层与 6 个月保留策略在 audit 模块实现时落地。
