#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式输出测试脚本

用法：
    python scripts/test_streaming.py

说明：
    测试 SSE 流式输出，观察进度事件和 token 级流式
"""
import asyncio
import httpx
import os
import time
from datetime import datetime


async def test_streaming():
    """测试流式输出"""
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    token = os.getenv("API_TOKEN", "")
    
    if not token:
        print("❌ 请先设置环境变量 API_TOKEN")
        print("   export API_TOKEN='your_token_here'")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "message": "帮我推荐一只基金",
        "stream": True,  # 流式模式
    }
    
    print("=" * 80)
    print("🚀 流式输出测试")
    print("=" * 80)
    print(f"📝 问题: {payload['message']}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    print("-" * 80)
    
    t_start = time.time()
    t_first_token = None
    t_first_status = None
    
    token_count = 0
    status_count = 0
    full_text = ""
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base_url}/api/v1/chat",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    print(f"❌ 请求失败: {response.status_code}")
                    return
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    
                    # 解析 SSE 数据
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    
                    try:
                        import json
                        data = json.loads(data_str)
                    except Exception:
                        continue
                    
                    # 获取事件类型（从前一行的 event: 字段）
                    # 简化处理：根据 data 内容判断
                    
                    # status 事件
                    if "stage" in data:
                        if t_first_status is None:
                            t_first_status = time.time()
                            elapsed = t_first_status - t_start
                            print(f"✅ 首个进度事件 | 延迟={elapsed:.3f}s")
                        
                        status_count += 1
                        stage = data.get("stage", "")
                        message = data.get("message", "")
                        elapsed = time.time() - t_start
                        print(f"📊 [{elapsed:.3f}s] {message or stage}")
                    
                    # message 事件（token）
                    elif "text" in data:
                        if t_first_token is None:
                            t_first_token = time.time()
                            elapsed = t_first_token - t_start
                            print(f"🎉 首个 token 到达 | 延迟={elapsed:.3f}s")
                            print("-" * 80)
                            print("💬 回答内容（实时流式）:")
                            print()
                        
                        token_count += 1
                        text = data.get("text", "")
                        full_text += text
                        
                        # 实时打印（模拟打字机效果）
                        print(text, end="", flush=True)
                    
                    # citation 事件
                    elif "source" in data or "chunk_id" in data:
                        print(f"\n📎 引用: {data}")
                    
                    # done 事件
                    elif "answerId" in data:
                        print("\n")
                        print("-" * 80)
                        elapsed = time.time() - t_start
                        print(f"✅ 回答完成 | 总耗时={elapsed:.3f}s")
                        print(f"📊 统计:")
                        print(f"   - 进度事件数: {status_count}")
                        print(f"   - token 数: {token_count}")
                        print(f"   - 回答长度: {len(full_text)} 字符")
                        if t_first_status:
                            print(f"   - 首个进度延迟: {t_first_status - t_start:.3f}s")
                        if t_first_token:
                            print(f"   - 首个 token 延迟: {t_first_token - t_start:.3f}s")
                        print(f"   - answerId: {data.get('answerId', 'N/A')}")
                        break
                    
                    # error 事件
                    elif "code" in data and "message" in data:
                        print(f"\n❌ 错误: {data}")
                        break
        
        print("=" * 80)
        print("✅ 测试完成")
        print()
        print("💡 提示:")
        print("   - 首个进度事件应在 0.1s 内到达（任务 1.1）")
        print("   - 首个 token 应在 1-2s 内到达（任务 1.2）")
        print("   - 如果首个 token 延迟 >3s，说明流式未生效")
        print()
        print("📝 查看后端日志:")
        print("   tail -f backend.log | grep PERF")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")


if __name__ == "__main__":
    asyncio.run(test_streaming())
