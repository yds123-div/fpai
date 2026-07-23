"""T1 prefactor：验证 AgentScope 2.0 API 可用（#19）。

R1（#3）查明已装版本为 2.0.4.post1，2.0 为大重写（模块名单数化、
ReActAgent 改名 Agent）。本测试固化 2.0 API 入口，防止版本 pin
回退到失真的 0.x/1.x 后静默 ImportError。
"""
import pytest

agentscope = pytest.importorskip("agentscope")


def test_agentscope_version_meets_pin():
    """agentscope>=2.0.4（与 pyproject.toml / requirements.txt pin 对齐）。"""
    version = agentscope.__version__
    numeric = [int(p) for p in version.split(".") if p.isdigit()]
    assert tuple(numeric[:3]) >= (2, 0, 4), f"agentscope {version} < 2.0.4 pin"


def test_agent_2_0_api_imports():
    """2.0 三大入口可 import（Agent / Toolkit / ChatModelBase）。"""
    from agentscope.agent import Agent
    from agentscope.tool import Toolkit
    from agentscope.model import ChatModelBase

    assert Agent is not None
    assert Toolkit is not None
    assert ChatModelBase is not None
