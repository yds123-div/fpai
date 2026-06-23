#!/usr/bin/env python3
"""本地开发：初始化 fpai 数据库核心表与 admin 账号。"""
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from auth.service import create_user
from rbac.store import _ensure_tables, ensure_seed_admin
from models.store import _ensure_table as ensure_models
from agents.agent_store import _ensure_table as ensure_agents
from agents.skills_store import _ensure_table as ensure_skills
from knowledge.store import _ensure_table as ensure_kb
from products.store import _ensure_table as ensure_products
from pkg.minio_client import ensure_bucket, get_bucket_docs, get_bucket_audit
from pkg.mysql_client import get_connection, is_configured

BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL DEFAULT '',
  name VARCHAR(128) NOT NULL DEFAULT '',
  employee_no VARCHAR(64) NOT NULL DEFAULT '',
  email VARCHAR(128) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_account (account),
  UNIQUE KEY uk_users_name (name),
  UNIQUE KEY uk_users_employee_no (employee_no),
  UNIQUE KEY uk_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sessions (
  id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sessions_user (user_id),
  KEY idx_sessions_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  role VARCHAR(16) NOT NULL DEFAULT 'user',
  content_summary VARCHAR(2000) NOT NULL DEFAULT '',
  full_content LONGTEXT NULL,
  structured_outputs JSON NULL,
  answer_id VARCHAR(64) NULL,
  citation_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_messages_session (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS config_strategy (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  config_key VARCHAR(128) NOT NULL,
  config_value JSON NOT NULL,
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS feedback (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  answer_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  rating VARCHAR(32) NOT NULL,
  comment TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_feedback_answer (answer_id),
  KEY idx_feedback_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_index (
  answer_id VARCHAR(64) NOT NULL,
  session_id VARCHAR(64) NOT NULL DEFAULT '',
  user_id VARCHAR(64) NOT NULL DEFAULT '',
  intent VARCHAR(128) NOT NULL DEFAULT '',
  model_version VARCHAR(64) NOT NULL DEFAULT '',
  policy_version VARCHAR(64) NOT NULL DEFAULT '',
  cold_ref VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (answer_id),
  KEY idx_audit_user (user_id),
  KEY idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  answer_id VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_audit_events_answer (answer_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS faq (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  tags JSON NULL,
  effective_from DATETIME NULL,
  effective_to DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS domain_models (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  model_code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  description VARCHAR(512) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_domain_models_code (model_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS domain_model_fields (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  model_code VARCHAR(64) NOT NULL,
  field_name VARCHAR(64) NOT NULL,
  data_type VARCHAR(32) NOT NULL DEFAULT 'string',
  is_required TINYINT(1) NOT NULL DEFAULT 0,
  description VARCHAR(255) NOT NULL DEFAULT '',
  default_value VARCHAR(255) NOT NULL DEFAULT '',
  source_path VARCHAR(255) NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_dmf_model (model_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS data_sources (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  model_code VARCHAR(64) NOT NULL,
  org_id VARCHAR(64) NULL,
  type VARCHAR(32) NOT NULL DEFAULT 'http',
  base_url VARCHAR(512) NOT NULL DEFAULT '',
  auth_type VARCHAR(32) NOT NULL DEFAULT '',
  auth_config JSON NULL,
  request_spec JSON NULL,
  response_spec JSON NULL,
  timeout_seconds INT NOT NULL DEFAULT 30,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ds_model_org (model_code, org_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def main() -> None:
    if not is_configured():
        print("MySQL 未配置，请检查 backend/.env")
        sys.exit(1)

    with get_connection() as conn:
        if not conn:
            print("无法连接 MySQL")
            sys.exit(1)
        with conn.cursor() as cur:
            for stmt in [s.strip() for s in BOOTSTRAP_SQL.split(";") if s.strip()]:
                cur.execute(stmt)
        conn.commit()
    print("核心表已创建")

    for fn, name in [
        (_ensure_tables, "rbac"),
        (ensure_models, "ai_models"),
        (ensure_agents, "agent_profiles"),
        (ensure_skills, "skill_profiles"),
        (ensure_kb, "knowledge_bases"),
        (ensure_products, "fund_products"),
    ]:
        fn()
        print(f"已确保表: {name}")

    with get_connection() as conn:
        if not conn:
            sys.exit(1)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE account='admin' LIMIT 1")
            exists = cur.fetchone() is not None

    if exists:
        print("admin 用户已存在")
    else:
        user, err = create_user(
            "admin",
            "admin123",
            name="管理员",
            employee_no="admin",
            email="admin@local",
        )
        if not user:
            print(f"创建 admin 失败: {err}")
            sys.exit(1)
        print("已创建 admin 用户，密码: admin123")

    ensure_seed_admin()
    print("已初始化 admin 角色与菜单")

    ensure_bucket(get_bucket_docs())
    ensure_bucket(get_bucket_audit())
    print("MinIO bucket 已确保: fpai-docs, fpai-audit")
    print("完成")


if __name__ == "__main__":
    main()
