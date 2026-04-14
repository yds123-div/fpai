"""
警告过滤配置。

抑制第三方库的已知警告，减少日志噪音。
"""

import warnings


def suppress_known_warnings() -> None:
    """抑制已知的第三方库警告。
    
    包括：
    - JWT InsecureKeyLengthWarning（开发环境可忽略）
    - AgentScope 未知参数警告
    """
    # 抑制 JWT 密钥长度警告（开发环境）
    # 生产环境应使用至少 32 字符的密钥
    warnings.filterwarnings(
        "ignore",
        message="The HMAC key is .* bytes long",
        category=UserWarning,
    )
    
    # 抑制 AgentScope 未知参数警告
    warnings.filterwarnings(
        "ignore",
        message="Unknown keyword arguments.*enable_thinking",
    )


# 导出
__all__ = ["suppress_known_warnings"]
