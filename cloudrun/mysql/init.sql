-- 自动初始化：创建所有表 + 种子数据
-- 由 MySQL Docker entrypoint 在首次启动时执行

CREATE TABLE IF NOT EXISTS `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `account` varchar(64) NOT NULL,
  `password_hash` varchar(255) NOT NULL DEFAULT '',
  `name` varchar(128) NOT NULL DEFAULT '',
  `employee_no` varchar(64) NOT NULL DEFAULT '',
  `email` varchar(128) NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_account` (`account`),
  UNIQUE KEY `uk_users_name` (`name`),
  UNIQUE KEY `uk_users_employee_no` (`employee_no`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `users` (`id`, `account`, `password_hash`, `name`, `employee_no`, `email`, `created_at`, `updated_at`)
VALUES (1,'admin','$2b$12$ds0bLPOYwJFp8/WxMYfIpexJwZ0k8NkvuiHhHiKwKlgmQZZY/jeRG','管理员','admin','admin@local','2026-06-11 07:38:02','2026-06-11 07:38:02');

CREATE TABLE IF NOT EXISTS `roles` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL DEFAULT '',
  `description` varchar(255) NOT NULL DEFAULT '',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_roles_code` (`code`),
  KEY `idx_roles_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `roles` (`id`, `code`, `name`, `description`, `enabled`, `created_at`, `updated_at`)
VALUES (1,'admin','管理员','系统管理员（拥有全部菜单权限）',1,'2026-06-11 07:38:02','2026-06-11 07:38:02');

CREATE TABLE IF NOT EXISTS `user_roles` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) NOT NULL,
  `role_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_roles` (`user_id`,`role_id`),
  KEY `idx_user_roles_user` (`user_id`),
  KEY `idx_user_roles_role` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `user_roles` (`id`, `user_id`, `role_id`, `created_at`) VALUES (1,'1',1,'2026-06-11 07:38:02');

CREATE TABLE IF NOT EXISTS `menus` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL DEFAULT '',
  `path` varchar(255) NOT NULL DEFAULT '',
  `icon` varchar(64) NOT NULL DEFAULT '',
  `parent_id` bigint unsigned DEFAULT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_menus_code` (`code`),
  KEY `idx_menus_parent` (`parent_id`),
  KEY `idx_menus_enabled` (`enabled`),
  KEY `idx_menus_sort` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `menus` (`id`, `code`, `name`, `path`, `icon`, `parent_id`, `sort_order`, `enabled`, `created_at`, `updated_at`) VALUES
(1,'admin-user','用户管理','/admin/system/user','user',NULL,10,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(2,'admin-roles','角色管理','/admin/system/roles','team',NULL,11,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(3,'admin-menus','菜单管理','/admin/system/menus','appstore',NULL,12,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(4,'admin-params','参数管理','/admin/system/config','setting',NULL,20,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(5,'admin-model','模型管理','/admin/model','thunderbolt',NULL,30,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(6,'admin-knowledge','知识库','/admin/knowledge','database',NULL,40,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(7,'admin-agent','Agent管理','/admin/agent','tool',NULL,50,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(8,'admin-skill','Skill管理','/admin/skill','tool',NULL,51,1,'2026-06-11 07:38:02','2026-06-11 07:38:02'),
(9,'theme-settings','主题样式设置','/admin/theme-settings','setting',NULL,55,1,'2026-06-11 07:38:02','2026-06-11 07:38:02');

CREATE TABLE IF NOT EXISTS `role_menus` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `role_id` bigint unsigned NOT NULL,
  `menu_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_menus` (`role_id`,`menu_id`),
  KEY `idx_role_menus_role` (`role_id`),
  KEY `idx_role_menus_menu` (`menu_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `role_menus` (`id`, `role_id`, `menu_id`, `created_at`) VALUES
(1,1,1,'2026-06-11 07:38:02'),(2,1,2,'2026-06-11 07:38:02'),(3,1,3,'2026-06-11 07:38:02'),
(4,1,4,'2026-06-11 07:38:02'),(5,1,5,'2026-06-11 07:38:02'),(6,1,6,'2026-06-11 07:38:02'),
(7,1,7,'2026-06-11 07:38:02'),(8,1,8,'2026-06-11 07:38:02'),(9,1,9,'2026-06-11 07:38:02');

CREATE TABLE IF NOT EXISTS `sessions` (
  `id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_sessions_user` (`user_id`),
  KEY `idx_sessions_updated` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `messages` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `session_id` varchar(64) NOT NULL,
  `role` varchar(16) NOT NULL DEFAULT 'user',
  `content_summary` varchar(2000) NOT NULL DEFAULT '',
  `full_content` longtext,
  `structured_outputs` json DEFAULT NULL,
  `answer_id` varchar(64) DEFAULT NULL,
  `citation_count` int NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_messages_session` (`session_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `config_strategy` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `config_key` varchar(128) NOT NULL,
  `config_value` json NOT NULL,
  `version` int NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `feedback` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `answer_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `rating` varchar(32) NOT NULL,
  `comment` text,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_feedback_answer` (`answer_id`),
  KEY `idx_feedback_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `audit_index` (
  `answer_id` varchar(64) NOT NULL,
  `session_id` varchar(64) NOT NULL DEFAULT '',
  `user_id` varchar(64) NOT NULL DEFAULT '',
  `intent` varchar(128) NOT NULL DEFAULT '',
  `model_version` varchar(64) NOT NULL DEFAULT '',
  `policy_version` varchar(64) NOT NULL DEFAULT '',
  `cold_ref` varchar(512) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`answer_id`),
  KEY `idx_audit_user` (`user_id`),
  KEY `idx_audit_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `audit_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `answer_id` varchar(64) NOT NULL,
  `event_type` varchar(64) NOT NULL,
  `payload` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_events_answer` (`answer_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `faq` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `question` text NOT NULL,
  `answer` text NOT NULL,
  `tags` json DEFAULT NULL,
  `effective_from` datetime DEFAULT NULL,
  `effective_to` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `domain_models` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `model_code` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL DEFAULT '',
  `description` varchar(512) NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_domain_models_code` (`model_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `domain_model_fields` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `model_code` varchar(64) NOT NULL,
  `field_name` varchar(64) NOT NULL,
  `data_type` varchar(32) NOT NULL DEFAULT 'string',
  `is_required` tinyint(1) NOT NULL DEFAULT '0',
  `description` varchar(255) NOT NULL DEFAULT '',
  `default_value` varchar(255) NOT NULL DEFAULT '',
  `source_path` varchar(255) NOT NULL DEFAULT '',
  `sort_order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_dmf_model` (`model_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `data_sources` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `model_code` varchar(64) NOT NULL,
  `org_id` varchar(64) DEFAULT NULL,
  `type` varchar(32) NOT NULL DEFAULT 'http',
  `base_url` varchar(512) NOT NULL DEFAULT '',
  `auth_type` varchar(32) NOT NULL DEFAULT '',
  `auth_config` json DEFAULT NULL,
  `request_spec` json DEFAULT NULL,
  `response_spec` json DEFAULT NULL,
  `timeout_seconds` int NOT NULL DEFAULT '30',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ds_model_org` (`model_code`,`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_profiles` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `agent_key` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL DEFAULT '',
  `type` varchar(32) NOT NULL DEFAULT 'custom',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `system_prompt` longtext,
  `skill_keys` longtext,
  `model_id` bigint unsigned DEFAULT NULL,
  `created_by` varchar(64) NOT NULL DEFAULT '',
  `updated_by` varchar(64) NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_profiles_key` (`agent_key`),
  KEY `idx_agent_profiles_type` (`type`),
  KEY `idx_agent_profiles_enabled` (`enabled`),
  KEY `idx_agent_profiles_deleted_at` (`deleted_at`),
  KEY `idx_agent_profiles_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `skill_profiles` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `skill_key` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL DEFAULT '',
  `type` varchar(32) NOT NULL DEFAULT 'builtin',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `module_path` varchar(255) NOT NULL DEFAULT '',
  `description` varchar(255) NOT NULL DEFAULT '',
  `created_by` varchar(64) NOT NULL DEFAULT '',
  `updated_by` varchar(64) NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_skill_profiles_key` (`skill_key`),
  KEY `idx_skill_profiles_type` (`type`),
  KEY `idx_skill_profiles_enabled` (`enabled`),
  KEY `idx_skill_profiles_deleted_at` (`deleted_at`),
  KEY `idx_skill_profiles_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_models` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `source` varchar(32) NOT NULL,
  `vendor` varchar(64) NOT NULL DEFAULT '',
  `model_name` varchar(128) NOT NULL DEFAULT '',
  `base_url` varchar(512) NOT NULL DEFAULT '',
  `api_key` varchar(512) NOT NULL DEFAULT '',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_models_name` (`name`),
  KEY `idx_ai_models_enabled` (`enabled`),
  KEY `idx_ai_models_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- AI 模型种子数据（LLM 对话模型）- api_key 留空，实际密钥从环境变量 LLM_API_KEY 注入
INSERT IGNORE INTO `ai_models` (`name`, `source`, `vendor`, `model_name`, `base_url`, `api_key`, `enabled`) VALUES
('DeepSeek-V4 (火山引擎)', 'remote', 'Volcengine', 'deepseek-v4-flash-260425', 'https://ark.cn-beijing.volces.com/api/v3', '', 1);

CREATE TABLE IF NOT EXISTS `knowledge_bases` (
  `uuid` varchar(64) NOT NULL,
  `name` varchar(255) NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`uuid`),
  KEY `idx_kb_enabled` (`enabled`),
  KEY `idx_kb_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `fund_products` (
  `product_code` varchar(32) NOT NULL,
  `product_name` varchar(255) NOT NULL DEFAULT '',
  `product_type` varchar(64) NOT NULL DEFAULT '',
  `risk_level` varchar(32) NOT NULL DEFAULT '-',
  `term` varchar(64) NOT NULL DEFAULT '-',
  `source` varchar(32) NOT NULL DEFAULT 'akshare',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`product_code`),
  KEY `idx_fund_products_name` (`product_name`),
  KEY `idx_fund_products_type` (`product_type`),
  KEY `idx_fund_products_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
