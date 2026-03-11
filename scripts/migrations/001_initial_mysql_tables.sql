-- T004: MySQL 建表与迁移（会话、消息、配置与策略、FAQ、反馈、审计索引）
-- 依据 technical_design §4.1；冷热分层与 6 个月保留在 audit 实现时落地
-- 字符集 utf8mb4

-- 迁移记录表（run_migrations.py 会先创建，此处便于手动执行时自包含）
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `version` VARCHAR(64) NOT NULL PRIMARY KEY,
  `name` VARCHAR(255) NOT NULL,
  `applied_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户表：支持账号+密码登录，存储姓名、工号、邮箱
-- 各表中的 user_id（sessions、feedback、audit_index）业务上关联本表 id
CREATE TABLE IF NOT EXISTS `users` (
  `id` VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '用户主键，业务层生成（如 UUID）',
  `account` VARCHAR(64) NOT NULL COMMENT '登录账号，唯一',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希（如 bcrypt/argon2），不存明文',
  `name` VARCHAR(128) NULL DEFAULT NULL COMMENT '用户姓名',
  `employee_no` VARCHAR(64) NULL DEFAULT NULL COMMENT '工号',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY `uk_users_account` (`account`),
  INDEX `idx_users_employee_no` (`employee_no`),
  INDEX `idx_users_email` (`email`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话：会话 id、用户 id（来自 BFF/SSO 注入）、创建/更新时间
CREATE TABLE IF NOT EXISTS `sessions` (
  `id` VARCHAR(64) NOT NULL PRIMARY KEY,
  `user_id` VARCHAR(64) NOT NULL COMMENT '关联 users.id（见迁移 002）',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX `idx_sessions_user_id` (`user_id`),
  INDEX `idx_sessions_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 消息：会话 id、角色、内容摘要、answer_id、引用块数等（正文过大可放冷存储）
CREATE TABLE IF NOT EXISTS `messages` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `session_id` VARCHAR(64) NOT NULL,
  `role` ENUM('user', 'assistant') NOT NULL,
  `content_summary` VARCHAR(2000) NOT NULL DEFAULT '',
  `answer_id` VARCHAR(64) NULL DEFAULT NULL,
  `citation_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `content_cold_ref` VARCHAR(512) NULL DEFAULT NULL COMMENT 'MinIO 等冷存储路径，正文过大时使用',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX `idx_messages_session_id` (`session_id`),
  INDEX `idx_messages_answer_id` (`answer_id`),
  INDEX `idx_messages_created_at` (`created_at`),
  CONSTRAINT `fk_messages_session` FOREIGN KEY (`session_id`) REFERENCES `sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 配置与策略：合规策略版本、路由策略、报告模板、对比维度模板、智能体注册信息等
CREATE TABLE IF NOT EXISTS `config_strategy` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `config_key` VARCHAR(128) NOT NULL,
  `config_value` JSON NOT NULL,
  `version` INT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FAQ 库：标准问、标准答、标签、生效时间
CREATE TABLE IF NOT EXISTS `faq` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `question` TEXT NOT NULL,
  `answer` TEXT NOT NULL,
  `tags` JSON NULL COMMENT '标签数组',
  `effective_from` DATETIME(3) NULL DEFAULT NULL,
  `effective_to` DATETIME(3) NULL DEFAULT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX `idx_faq_effective` (`effective_from`, `effective_to`),
  FULLTEXT INDEX `ft_faq_question` (`question`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 反馈：answer_id、用户 id、rating、comment、时间
CREATE TABLE IF NOT EXISTS `feedback` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `answer_id` VARCHAR(64) NOT NULL,
  `user_id` VARCHAR(64) NOT NULL COMMENT '关联 users.id',
  `rating` ENUM('useful', 'not_useful', 'inaccurate') NOT NULL,
  `comment` TEXT NULL DEFAULT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX `idx_feedback_answer_id` (`answer_id`),
  INDEX `idx_feedback_user_id` (`user_id`),
  INDEX `idx_feedback_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 审计索引（热）：answer_id、session_id、user_id、intent、model_version、policy_version、created_at
-- 审计正文或大字段冷分层后存 MinIO 或归档表
CREATE TABLE IF NOT EXISTS `audit_index` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `answer_id` VARCHAR(64) NOT NULL,
  `session_id` VARCHAR(64) NOT NULL,
  `user_id` VARCHAR(64) NOT NULL COMMENT '关联 users.id',
  `intent` VARCHAR(128) NULL DEFAULT NULL,
  `model_version` VARCHAR(128) NULL DEFAULT NULL,
  `policy_version` VARCHAR(128) NULL DEFAULT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `cold_ref` VARCHAR(512) NULL DEFAULT NULL COMMENT '审计正文冷存储路径',
  UNIQUE KEY `uk_audit_answer_id` (`answer_id`),
  INDEX `idx_audit_session_id` (`session_id`),
  INDEX `idx_audit_user_id` (`user_id`),
  INDEX `idx_audit_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- T004b: 领域模型与数据源表，支持 docs/领域模型与API适配器设计.md §8 配置存储
-- 依赖 T004（001/002 已存在）；字符集 utf8mb4

-- 领域模型：模型编码、名称、描述（一接口一模型，如 0731H016）
CREATE TABLE IF NOT EXISTS `domain_models` (
  `model_code` VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '接口/模型编码，如 0731H016',
  `name` VARCHAR(255) NOT NULL COMMENT '模型名称，如 基金基本信息查询',
  `description` TEXT NULL DEFAULT NULL COMMENT '业务说明',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX `idx_domain_models_name` (`name`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 领域模型元数据（字段）：字段名、类型、必填、描述、默认值、source_path（映射用）
CREATE TABLE IF NOT EXISTS `domain_model_fields` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `model_code` VARCHAR(64) NOT NULL COMMENT '关联 DOMAIN_MODELS.model_code',
  `field_name` VARCHAR(128) NOT NULL COMMENT '模型侧字段名',
  `data_type` VARCHAR(32) NOT NULL DEFAULT 'string' COMMENT 'string/number/boolean/date/array/object',
  `is_required` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否必填',
  `description` VARCHAR(512) NULL DEFAULT NULL,
  `default_value` VARCHAR(512) NULL DEFAULT NULL COMMENT '默认值，简单类型',
  `source_path` VARCHAR(512) NULL DEFAULT NULL COMMENT '响应取值路径，如 $.fundCode，映射用',
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY `uk_domain_model_fields_model_field` (`model_code`, `field_name`),
  INDEX `idx_domain_model_fields_model_code` (`model_code`),
  CONSTRAINT `fk_domain_model_fields_model` FOREIGN KEY (`model_code`) REFERENCES `DOMAIN_MODELS` (`model_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 数据源：为领域模型配置获取方式（如 HTTP REST）、连接信息、请求/响应/映射
CREATE TABLE IF NOT EXISTS `data_sources` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `model_code` VARCHAR(64) NOT NULL COMMENT '关联 DOMAIN_MODELS.model_code',
  `org_id` VARCHAR(64) NULL DEFAULT NULL COMMENT '机构/租户 id，NULL 表示默认数据源',
  `type` VARCHAR(32) NOT NULL DEFAULT 'http_rest' COMMENT 'http_rest / 后续 gRPC 等',
  `base_url` VARCHAR(512) NULL DEFAULT NULL COMMENT 'HTTP 时 base_url',
  `auth_type` VARCHAR(32) NULL DEFAULT NULL COMMENT 'bearer / api_key / none',
  `auth_config` JSON NULL DEFAULT NULL COMMENT '认证配置，如 header 名、key 占位',
  `request_spec` JSON NULL DEFAULT NULL COMMENT 'method, path, query_params, body_params, path_params, headers',
  `response_spec` JSON NULL DEFAULT NULL COMMENT 'list_path, total_path, single_path',
  `mapping_spec` JSON NULL DEFAULT NULL COMMENT '可选，[{"model_field","response_path"}]，覆盖 fields.source_path',
  `timeout_seconds` INT UNSIGNED NULL DEFAULT 30,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY `uk_data_sources_model_org` (`model_code`, `org_id`),
  INDEX `idx_data_sources_model_code` (`model_code`),
  INDEX `idx_data_sources_org_id` (`org_id`),
  CONSTRAINT `fk_data_sources_model` FOREIGN KEY (`model_code`) REFERENCES `DOMAIN_MODELS` (`model_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 映射规则（可选独立表）：数据源维度的 response_path -> model_field，与 domain_model_fields.source_path 二选一或并存
CREATE TABLE IF NOT EXISTS mapping_rules (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `data_source_id` INT UNSIGNED NOT NULL COMMENT '关联 DATA_SOURCES.id',
  `model_field` VARCHAR(128) NOT NULL COMMENT '领域模型字段名',
  `response_path` VARCHAR(512) NOT NULL COMMENT '响应中取值路径，如 $.fundName',
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX `idx_mapping_rules_data_source_id` (`data_source_id`),
  CONSTRAINT `fk_mapping_rules_data_source` FOREIGN KEY (`data_source_id`) REFERENCES `DATA_SOURCES` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- T012: 审计事件表，支持 appendEvent 按 answer_id 追加事件；与 audit_index 配合冷热分层
-- 依据 technical_design §4.1、architecture S3 证据与审计

CREATE TABLE IF NOT EXISTS `audit_events` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `answer_id` VARCHAR(64) NOT NULL COMMENT '关联 audit_index.answer_id',
  `event_type` VARCHAR(64) NOT NULL COMMENT '事件类型：request、intent、compliance_result、answer_generated 等',
  `payload` JSON NOT NULL COMMENT '事件载荷',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX `idx_audit_events_answer_id` (`answer_id`),
  INDEX `idx_audit_events_created_at` (`created_at`),
  INDEX `idx_audit_events_answer_created` (`answer_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
