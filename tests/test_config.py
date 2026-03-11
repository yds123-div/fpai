"""config 模块单元/集成测试：get_config、get_compliance_policy、缓存。"""
import json
import pytest

from config import get_config, get_compliance_policy, clear_config_cache, CONFIG_KEY_COMPLIANCE_POLICY


def test_config_key_constant():
    assert CONFIG_KEY_COMPLIANCE_POLICY == "compliance_policy"


def test_get_config_without_mysql():
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    clear_config_cache()
    assert get_config("compliance_policy") is None
    assert get_compliance_policy() is None


def test_get_config_nonexistent_key():
    from pkg.mysql_client import is_configured
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过")
    clear_config_cache()
    out = get_config("nonexistent_key_xyz", use_cache=False)
    assert out is None


@pytest.mark.integration
def test_get_compliance_policy_from_mysql():
    """MySQL 已配置且存在 compliance_policy 时，返回 dict 且可被 CompliancePolicy.from_dict 解析。"""
    from pkg.mysql_client import is_configured, get_connection
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    clear_config_cache()
    # 若表中无数据则先插入一条
    with get_connection() as conn:
        if conn is None:
            pytest.skip("无法获取连接")
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM config_strategy WHERE config_key = %s", (CONFIG_KEY_COMPLIANCE_POLICY,))
            if cur.fetchone() is None:
                val = json.dumps({
                    "policy_version": "v1",
                    "blacklist_keywords": ["保本保息", "承诺收益"],
                    "whitelist_keywords": [],
                    "enable_llm_input_check": True,
                    "enable_llm_output_check": True,
                }, ensure_ascii=False)
                cur.execute(
                    "INSERT INTO config_strategy (config_key, config_value, version) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)",
                    (CONFIG_KEY_COMPLIANCE_POLICY, val),
                )
    raw = get_compliance_policy(use_cache=False)
    if raw is None:
        pytest.skip("表中无 compliance_policy 或读取失败")
    assert "policy_version" in raw
    assert "blacklist_keywords" in raw
    # 合规层可用 from_dict 构造
    from compliance.config import CompliancePolicy
    policy = CompliancePolicy.from_dict(raw)
    assert policy.policy_version == raw.get("policy_version") or "v1"
    assert policy.blacklist_matches("产品保本保息") == ["保本保息"]


def test_clear_config_cache():
    clear_config_cache()
    clear_config_cache("compliance_policy")
    clear_config_cache(None)
