-- 刷新恢复内容不一致修复：新增 full_content 列，存储完整回复（含 thinking）
-- content_summary 继续用于上下文构建与摘要展示，full_content 仅用于刷新恢复
ALTER TABLE messages ADD COLUMN full_content TEXT NULL DEFAULT NULL
  COMMENT '完整回复内容（含thinking），用于刷新恢复' AFTER content_summary;
