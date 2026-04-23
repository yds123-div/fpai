-- 图表刷新丢失修复：新增 structured_outputs 列，存储结构化输出（含图表 JSON）
ALTER TABLE messages ADD COLUMN structured_outputs JSON NULL DEFAULT NULL
  COMMENT '结构化输出JSON（含fund_analysis图表等），用于刷新恢复' AFTER full_content;
