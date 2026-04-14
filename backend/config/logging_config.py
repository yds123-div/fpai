"""
增强的日志配置。

提供日志轮转、模块级日志配置等高级功能。
基于 pkg.logger 的基础功能进行扩展。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Literal

from pkg.logger import TraceIdFormatter, TraceIdFilter


# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_module_logging(
    module_name: str,
    level: str | int | None = None,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_rotation: bool = True,
) -> logging.Logger:
    """配置模块级日志。
    
    为特定模块配置独立的日志处理器，支持日志轮转。
    
    Args:
        module_name: 模块名称（如 "pkg.akshare_client"）
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        log_file: 日志文件路径（相对或绝对）
        max_bytes: 单个日志文件最大字节数（默认 10MB）
        backup_count: 保留的备份文件数量（默认 5）
        use_rotation: 是否使用日志轮转（默认 True）
    
    Returns:
        配置好的 Logger 实例
    
    Example:
        >>> logger = configure_module_logging(
        ...     "pkg.akshare_client",
        ...     level="DEBUG",
        ...     log_file="logs/akshare.log",
        ... )
    """
    # 获取或创建 logger
    logger = logging.getLogger(module_name)
    
    # 设置日志级别
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 添加 TraceIdFilter（如果尚未添加）
    if not any(isinstance(f, TraceIdFilter) for f in logger.filters):
        logger.addFilter(TraceIdFilter())
    
    # 创建格式化器
    format_string = (
        "%(asctime)s [%(levelname)s] %(name)s trace_id=%(trace_id)s "
        "%(filename)s:%(lineno)d - %(message)s"
    )
    formatter = TraceIdFormatter(format_string)
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        # 创建日志目录
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        # 选择处理器类型
        if use_rotation:
            # 使用轮转文件处理器
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            # 使用普通文件处理器
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        
        # 避免重复添加
        if not any(
            isinstance(h, (RotatingFileHandler, logging.FileHandler))
            and getattr(h, "baseFilename", None) == file_handler.baseFilename
            for h in logger.handlers
        ):
            logger.addHandler(file_handler)
    
    # 防止日志传播到根 logger（避免重复输出）
    logger.propagate = False
    
    # 添加控制台处理器（如果尚未添加）
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def configure_timed_rotation_logging(
    module_name: str,
    level: str | int | None = None,
    log_file: str | None = None,
    when: Literal["S", "M", "H", "D", "W0", "W1", "W2", "W3", "W4", "W5", "W6", "midnight"] = "midnight",
    interval: int = 1,
    backup_count: int = 30,
) -> logging.Logger:
    """配置基于时间的日志轮转。
    
    按时间间隔轮转日志文件（如每天、每周）。
    
    Args:
        module_name: 模块名称
        level: 日志级别
        log_file: 日志文件路径
        when: 轮转时间单位
            - "S": 秒
            - "M": 分钟
            - "H": 小时
            - "D": 天
            - "W0"-"W6": 星期几（0=Monday）
            - "midnight": 每天午夜
        interval: 轮转间隔（默认 1）
        backup_count: 保留的备份文件数量（默认 30）
    
    Returns:
        配置好的 Logger 实例
    
    Example:
        >>> logger = configure_timed_rotation_logging(
        ...     "pkg.akshare_client",
        ...     log_file="logs/akshare.log",
        ...     when="midnight",
        ...     backup_count=30,
        ... )
    """
    # 获取或创建 logger
    logger = logging.getLogger(module_name)
    
    # 设置日志级别
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 添加 TraceIdFilter
    if not any(isinstance(f, TraceIdFilter) for f in logger.filters):
        logger.addFilter(TraceIdFilter())
    
    # 创建格式化器
    format_string = (
        "%(asctime)s [%(levelname)s] %(name)s trace_id=%(trace_id)s "
        "%(filename)s:%(lineno)d - %(message)s"
    )
    formatter = TraceIdFormatter(format_string)
    
    # 如果指定了日志文件，添加时间轮转处理器
    if log_file:
        # 创建日志目录
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        # 创建时间轮转处理器
        file_handler = TimedRotatingFileHandler(
            log_file,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        
        # 避免重复添加
        if not any(
            isinstance(h, TimedRotatingFileHandler)
            and getattr(h, "baseFilename", None) == file_handler.baseFilename
            for h in logger.handlers
        ):
            logger.addHandler(file_handler)
    
    # 防止日志传播到根 logger
    logger.propagate = False
    
    # 添加控制台处理器
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def configure_akshare_logging() -> logging.Logger:
    """配置 AkShare 客户端日志。
    
    从环境变量读取配置：
    - AKSHARE_LOG_LEVEL: 日志级别（默认 INFO）
    - AKSHARE_LOG_FILE: 日志文件路径（默认 logs/akshare.log）
    - AKSHARE_LOG_MAX_BYTES: 单个文件最大字节数（默认 10MB）
    - AKSHARE_LOG_BACKUP_COUNT: 备份文件数量（默认 5）
    
    Returns:
        配置好的 Logger 实例
    
    Example:
        >>> logger = configure_akshare_logging()
        >>> logger.info("AkShare client initialized")
    """
    level = os.getenv("AKSHARE_LOG_LEVEL", "INFO")
    log_file = os.getenv("AKSHARE_LOG_FILE", "logs/akshare.log")
    max_bytes = int(os.getenv("AKSHARE_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("AKSHARE_LOG_BACKUP_COUNT", "5"))
    
    return configure_module_logging(
        module_name="pkg.akshare_client",
        level=level,
        log_file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
        use_rotation=True,
    )


def configure_fund_agent_logging() -> logging.Logger:
    """配置基金 Agent 日志。
    
    从环境变量读取配置：
    - FUND_AGENT_LOG_LEVEL: 日志级别（默认 INFO）
    - FUND_AGENT_LOG_FILE: 日志文件路径（默认 logs/fund_agent.log）
    - FUND_AGENT_LOG_MAX_BYTES: 单个文件最大字节数（默认 10MB）
    - FUND_AGENT_LOG_BACKUP_COUNT: 备份文件数量（默认 5）
    
    Returns:
        配置好的 Logger 实例
    
    Example:
        >>> logger = configure_fund_agent_logging()
        >>> logger.info("Fund agent started")
    """
    level = os.getenv("FUND_AGENT_LOG_LEVEL", "INFO")
    log_file = os.getenv("FUND_AGENT_LOG_FILE", "logs/fund_agent.log")
    max_bytes = int(os.getenv("FUND_AGENT_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("FUND_AGENT_LOG_BACKUP_COUNT", "5"))
    
    return configure_module_logging(
        module_name="agents.fund_agent",
        level=level,
        log_file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
        use_rotation=True,
    )


def setup_all_logging() -> None:
    """初始化所有模块的日志配置。
    
    在应用启动时调用，配置所有模块的日志。
    
    Example:
        >>> # 在 main.py 或 app.py 中调用
        >>> setup_all_logging()
    """
    # 配置根 logger（基础配置）
    from pkg.logger import configure_logging
    configure_logging()
    
    # 配置 AkShare 客户端日志
    configure_akshare_logging()
    
    # 配置基金 Agent 日志
    configure_fund_agent_logging()
    
    # 抑制第三方库的 DEBUG 日志
    suppress_third_party_logs()
    
    # 抑制已知警告
    from config.warnings_filter import suppress_known_warnings
    suppress_known_warnings()
    
    # 记录初始化完成
    logger = logging.getLogger(__name__)
    logger.info("All logging configured successfully")


def suppress_third_party_logs() -> None:
    """抑制第三方库的详细日志输出。
    
    将常见第三方库的日志级别提升到 WARNING，减少噪音。
    可通过环境变量 THIRD_PARTY_LOG_LEVEL 控制级别。
    """
    # 从环境变量读取第三方库日志级别
    third_party_level = os.getenv("THIRD_PARTY_LOG_LEVEL", "WARNING")
    level = LOG_LEVELS.get(third_party_level.upper(), logging.WARNING)
    
    third_party_loggers = [
        "httpcore",
        "httpx",
        "urllib3",
        "openai",
        "asyncio",
    ]
    
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(level)


# 导出
__all__ = [
    "configure_module_logging",
    "configure_timed_rotation_logging",
    "configure_akshare_logging",
    "configure_fund_agent_logging",
    "setup_all_logging",
    "suppress_third_party_logs",
]
