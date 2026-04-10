# -*- coding: utf-8 -*-
"""
LLM 调用监控包装器

为 LLM 调用添加性能监控，记录：
- 输入/输出 tokens
- 首 token 延迟
- 总耗时
"""

from __future__ import annotations

import time
import logging
from typing import Any, AsyncIterator

from pkg.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


async def monitor_llm_stream(
    stream_generator: AsyncIterator[str],
    llm_name: str,
    input_tokens: int,
) -> AsyncIterator[str]:
    """
    监控流式 LLM 调用
    
    Args:
        stream_generator: 流式生成器
        llm_name: 模型名称
        input_tokens: 输入 tokens 数量
    
    Yields:
        生成的文本片段
    """
    metrics_collector = get_metrics_collector()
    
    start_time = time.time()
    first_token_time: float | None = None
    output_text = ""
    
    try:
        async for chunk in stream_generator:
            if not chunk:
                continue
            
            # 记录首 token 延迟
            if first_token_time is None:
                first_token_time = time.time() - start_time
            
            output_text += chunk
            yield chunk
        
        # 记录完整指标
        duration = time.time() - start_time
        output_tokens = len(output_text) // 4  # 粗略估计
        
        metrics_collector.record_llm_call(
            llm_name=llm_name,
            duration=duration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            first_token_latency=first_token_time,
        )
        
        logger.info(
            f"[PERF] LLM 流式调用 - 模型: {llm_name}, "
            f"耗时: {duration:.3f}s, 首token: {first_token_time:.3f}s, "
            f"输入tokens: {input_tokens}, 输出tokens: {output_tokens}"
        )
    
    except Exception as e:
        logger.error(f"LLM 流式调用异常: {e}")
        raise


def monitor_llm_call(
    result: str,
    llm_name: str,
    input_tokens: int,
    duration: float,
) -> str:
    """
    监控非流式 LLM 调用
    
    Args:
        result: LLM 返回结果
        llm_name: 模型名称
        input_tokens: 输入 tokens 数量
        duration: 调用耗时
    
    Returns:
        原始结果
    """
    metrics_collector = get_metrics_collector()
    
    output_tokens = len(result) // 4  # 粗略估计
    
    metrics_collector.record_llm_call(
        llm_name=llm_name,
        duration=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        first_token_latency=None,
    )
    
    logger.info(
        f"[PERF] LLM 非流式调用 - 模型: {llm_name}, "
        f"耗时: {duration:.3f}s, "
        f"输入tokens: {input_tokens}, 输出tokens: {output_tokens}"
    )
    
    return result


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    
    粗略估计：1 token ≈ 4 字符（中文）或 4 字符（英文）
    
    Args:
        text: 输入文本
    
    Returns:
        估算的 token 数量
    """
    return max(1, len(text) // 4)
