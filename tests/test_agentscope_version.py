"""T1 prefactor：验证 AgentScope 2.0 API 可用（#19）。

R1（#3）查明已装版本为 2.0.4.post1，2.0 为大重写（模块名单数化、
ReActAgent 改名 Agent）。本测试固化 2.0 API 入口，防止版本 pin
回退到失真的 0.x/1.x 后静默 ImportError。
"""
import pytest
from packaging.version import Version

agentscope = pytest.importorskip("agentscope")

# 与 backend/pyproject.toml / requirements.txt 的 agentscope pin 对齐
AGENTSCOPE_MIN_VERSION = Version("2.0.4")


def test_agentscope_version_meets_pin():
    """agentscope>=2.0.4（与 pyproject / requirements pin 对齐）。"""
    installed = Version(agentscope.__version__)
    assert installed >= AGENTSCOPE_MIN_VERSION, (
        f"agentscope {agentscope.__version__} < 2.0.4 pin"
    )


def test_agentscope_core_api_imports():
    """2.0 三大入口可 import（Agent / Toolkit / ChatModelBase）。"""
    from agentscope.agent import Agent
    from agentscope.tool import Toolkit
    from agentscope.model import ChatModelBase

    assert Agent is not None
    assert Toolkit is not None
    assert ChatModelBase is not None
