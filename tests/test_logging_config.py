"""
测试日志配置。

测试场景：
1. 模块级日志配置
2. 日志轮转配置
3. 时间轮转配置
4. AkShare 日志配置
5. 基金 Agent 日志配置
"""

import pytest
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from config.logging_config import (
    configure_module_logging,
    configure_timed_rotation_logging,
    configure_akshare_logging,
    configure_fund_agent_logging,
    setup_all_logging,
)


class TestModuleLogging:
    """测试模块级日志配置。"""

    def test_configure_module_logging_basic(self):
        """测试基本的模块日志配置。"""
        logger = configure_module_logging(
            module_name="test.module",
            level="DEBUG",
        )
        
        assert logger.name == "test.module"
        assert logger.level == logging.DEBUG
        assert not logger.propagate  # 不传播到根 logger
        
        # 验证有控制台处理器
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_configure_module_logging_with_file(self):
        """测试带文件输出的模块日志配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            
            logger = configure_module_logging(
                module_name="test.module.file",
                level="INFO",
                log_file=log_file,
            )
            
            # 验证日志文件已创建
            assert os.path.exists(log_file)
            
            # 验证有文件处理器
            assert any(
                isinstance(h, (RotatingFileHandler, logging.FileHandler))
                for h in logger.handlers
            )
            
            # 写入日志
            logger.info("Test log message")
            
            # 验证日志已写入文件
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                assert "Test log message" in content

    def test_configure_module_logging_with_rotation(self):
        """测试带日志轮转的配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_rotation.log")
            
            logger = configure_module_logging(
                module_name="test.module.rotation",
                level="INFO",
                log_file=log_file,
                max_bytes=1024,  # 1KB
                backup_count=3,
                use_rotation=True,
            )
            
            # 验证有轮转文件处理器
            rotating_handlers = [
                h for h in logger.handlers
                if isinstance(h, RotatingFileHandler)
            ]
            assert len(rotating_handlers) > 0
            
            handler = rotating_handlers[0]
            assert handler.maxBytes == 1024
            assert handler.backupCount == 3

    def test_configure_module_logging_no_rotation(self):
        """测试不使用日志轮转的配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_no_rotation.log")
            
            logger = configure_module_logging(
                module_name="test.module.no_rotation",
                level="INFO",
                log_file=log_file,
                use_rotation=False,
            )
            
            # 验证没有轮转文件处理器
            rotating_handlers = [
                h for h in logger.handlers
                if isinstance(h, RotatingFileHandler)
            ]
            assert len(rotating_handlers) == 0
            
            # 验证有普通文件处理器
            file_handlers = [
                h for h in logger.handlers
                if isinstance(h, logging.FileHandler) and not isinstance(h, RotatingFileHandler)
            ]
            assert len(file_handlers) > 0

    def test_configure_module_logging_level_from_string(self):
        """测试从字符串设置日志级别。"""
        for level_str, level_int in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            logger = configure_module_logging(
                module_name=f"test.module.{level_str.lower()}",
                level=level_str,
            )
            assert logger.level == level_int


class TestTimedRotationLogging:
    """测试基于时间的日志轮转。"""

    def test_configure_timed_rotation_logging(self):
        """测试时间轮转日志配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_timed.log")
            
            logger = configure_timed_rotation_logging(
                module_name="test.module.timed",
                level="INFO",
                log_file=log_file,
                when="midnight",
                interval=1,
                backup_count=30,
            )
            
            # 验证有时间轮转处理器
            timed_handlers = [
                h for h in logger.handlers
                if isinstance(h, TimedRotatingFileHandler)
            ]
            assert len(timed_handlers) > 0
            
            handler = timed_handlers[0]
            assert handler.when == "MIDNIGHT"
            assert handler.interval == 1
            assert handler.backupCount == 30

    def test_configure_timed_rotation_logging_hourly(self):
        """测试按小时轮转的配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_hourly.log")
            
            logger = configure_timed_rotation_logging(
                module_name="test.module.hourly",
                log_file=log_file,
                when="H",
                interval=1,
            )
            
            timed_handlers = [
                h for h in logger.handlers
                if isinstance(h, TimedRotatingFileHandler)
            ]
            assert len(timed_handlers) > 0
            assert timed_handlers[0].when == "H"


class TestAkShareLogging:
    """测试 AkShare 日志配置。"""

    def test_configure_akshare_logging_default(self):
        """测试默认的 AkShare 日志配置。"""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as tmpdir:
                log_file = os.path.join(tmpdir, "akshare.log")
                
                with patch.dict(os.environ, {"AKSHARE_LOG_FILE": log_file}):
                    logger = configure_akshare_logging()
                    
                    assert logger.name == "pkg.akshare_client"
                    assert logger.level == logging.INFO  # 默认级别

    def test_configure_akshare_logging_custom(self):
        """测试自定义的 AkShare 日志配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "akshare_custom.log")
            
            env_vars = {
                "AKSHARE_LOG_LEVEL": "DEBUG",
                "AKSHARE_LOG_FILE": log_file,
                "AKSHARE_LOG_MAX_BYTES": "5242880",  # 5MB
                "AKSHARE_LOG_BACKUP_COUNT": "10",
            }
            
            with patch.dict(os.environ, env_vars, clear=True):
                logger = configure_akshare_logging()
                
                assert logger.level == logging.DEBUG
                
                # 验证轮转配置
                rotating_handlers = [
                    h for h in logger.handlers
                    if isinstance(h, RotatingFileHandler)
                ]
                if rotating_handlers:
                    handler = rotating_handlers[0]
                    assert handler.maxBytes == 5242880
                    assert handler.backupCount == 10


class TestFundAgentLogging:
    """测试基金 Agent 日志配置。"""

    def test_configure_fund_agent_logging_default(self):
        """测试默认的基金 Agent 日志配置。"""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as tmpdir:
                log_file = os.path.join(tmpdir, "fund_agent.log")
                
                with patch.dict(os.environ, {"FUND_AGENT_LOG_FILE": log_file}):
                    logger = configure_fund_agent_logging()
                    
                    assert logger.name == "agents.fund_agent"
                    assert logger.level == logging.INFO

    def test_configure_fund_agent_logging_custom(self):
        """测试自定义的基金 Agent 日志配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "fund_agent_custom.log")
            
            env_vars = {
                "FUND_AGENT_LOG_LEVEL": "WARNING",
                "FUND_AGENT_LOG_FILE": log_file,
                "FUND_AGENT_LOG_MAX_BYTES": "20971520",  # 20MB
                "FUND_AGENT_LOG_BACKUP_COUNT": "3",
            }
            
            with patch.dict(os.environ, env_vars, clear=True):
                logger = configure_fund_agent_logging()
                
                assert logger.level == logging.WARNING


class TestSetupAllLogging:
    """测试初始化所有日志配置。"""

    def test_setup_all_logging(self):
        """测试初始化所有模块的日志。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "AKSHARE_LOG_FILE": os.path.join(tmpdir, "akshare.log"),
                "FUND_AGENT_LOG_FILE": os.path.join(tmpdir, "fund_agent.log"),
            }
            
            with patch.dict(os.environ, env_vars, clear=True):
                # 不应该抛出异常
                setup_all_logging()
                
                # 验证日志文件已创建
                assert os.path.exists(env_vars["AKSHARE_LOG_FILE"])
                assert os.path.exists(env_vars["FUND_AGENT_LOG_FILE"])


class TestLoggerUsage:
    """测试日志使用场景。"""

    def test_logger_with_trace_id(self):
        """测试带 trace_id 的日志。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_trace.log")
            
            logger = configure_module_logging(
                module_name="test.trace",
                level="INFO",
                log_file=log_file,
            )
            
            # 设置 trace_id
            from pkg.logger import bind_trace_id
            bind_trace_id("test-trace-123")
            
            # 写入日志
            logger.info("Test message with trace_id")
            
            # 验证日志包含 trace_id
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                assert "test-trace-123" in content
                assert "Test message with trace_id" in content

    def test_logger_multiple_messages(self):
        """测试写入多条日志。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_multiple.log")
            
            logger = configure_module_logging(
                module_name="test.multiple",
                level="DEBUG",
                log_file=log_file,
            )
            
            # 写入不同级别的日志
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            
            # 验证所有日志都已写入
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                assert "Debug message" in content
                assert "Info message" in content
                assert "Warning message" in content
                assert "Error message" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
