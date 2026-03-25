-- 初始数据填充脚本
-- 说明：
-- 1. 仅在空表或开发环境中使用，避免覆盖生产数据
-- 2. 与 001_initial_mysql_tables.sql 中的表结构保持一致
-- 3. 如需调整默认数据，请在后续迁移中追加，不要直接修改历史脚本

SET NAMES utf8mb4;

-- 基础用户：默认管理员账号（密码需在应用层重置）
INSERT INTO `users` (`account`, `password_hash`, `name`, `employee_no`, `email`)
VALUES
  ('admin', '$2b$12$REPLACE_WITH_REAL_HASH_____________', '系统管理员', '000000', 'admin@example.com')
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `employee_no` = VALUES(`employee_no`),
  `email` = VALUES(`email`);

-- 配置与策略：基础合规策略、路由策略、报告模板、对比维度模板等占位
INSERT INTO `config_strategy` (`config_key`, `config_value`, `version`)
VALUES
  (
    'compliance.default_policy',
    JSON_OBJECT(
      'name', '默认合规策略',
      'version', 1,
      'rules', JSON_ARRAY('block_sensitive_info', 'log_all_answers')
    ),
    1
  ),
  (
    'routing.default_strategy',
    JSON_OBJECT(
      'name', '默认路由策略',
      'version', 1,
      'intents', JSON_ARRAY('faq', 'rag_summary', 'product_list', 'product_compare', 'product_recommend', 'report_generate')
    ),
    1
  ),
  (
    'report.templates',
    JSON_OBJECT(
      'weekly', JSON_OBJECT('templateId', 'weekly', 'name', '周报模板'),
      'monthly', JSON_OBJECT('templateId', 'monthly', 'name', '月报模板')
    ),
    1
  ),
  (
    'compare.dimension_templates',
    JSON_OBJECT(
      'default', JSON_ARRAY('收益', '风险等级', '期限', '流动性')
    ),
    1
  )
ON DUPLICATE KEY UPDATE
  `config_value` = VALUES(`config_value`),
  `version` = `version` + 1;

-- FAQ 示例数据：便于验证 FAQ 能力与检索
INSERT INTO `faq` (`question`, `answer`, `tags`, `effective_from`)
VALUES
  (
    'fpai 系统主要功能有哪些？',
    'fpai 提供智能对话、产品对比、产品推荐、报告生成、证据查询与反馈能力。',
    JSON_ARRAY('功能', '总览'),
    NOW(3)
  ),
  (
    '如何对某条回答进行反馈？',
    '在前端「回答反馈」页面或对话区，选择对应回答的 answerId，提交有用/无用/不准确评价及可选说明。',
    JSON_ARRAY('反馈', '使用指引'),
    NOW(3)
  );

-- 领域模型示例：便于验证数据访问与适配层
INSERT INTO `domain_models` (`model_code`, `name`, `description`)
VALUES
  ('0731H016', '基金基本信息查询', '示例领域模型：用于查询基金基本信息'),
  ('PRODUCT_LIST', '产品列表查询', '用于智能体产品列表/筛选能力的数据访问模型')
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `description` = VALUES(`description`);

