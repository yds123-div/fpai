#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控测试脚本

用法：
    python scripts/test_perf_monitoring.py

说明：
    发送一个测试请求到 /api/v1/chat，观察日志中的 [PERF] 标记
"""
import asyncio
import httpx
import json
import os
from datetime import datetime


async def test_chat_performance():
    """测试聊天性能监控"""
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    token = os.getenv("API_TOKEN", "")  # 需要先登录获取 token
    
    if not token:
        print("❌ 请先设置环境变量 API_TOKEN（通过 /api/v1/auth/login 获取）")
        print("   或者修改脚本中的 token 变量")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "message": "帮我推荐一只基金",
        "stream": False,  # 非流式，方便观察完整耗时
    }
    
    print(f"🚀 发送测试请求: {payload['message']}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    print("-" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/api/v1/chat",
                headers=headers,
                json=payload,
            )
            
            print(f"✅ 响应状态: {response.status_code}")
            print(f"⏰ 结束时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            print("-" * 60)
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 响应数据:")
                print(f"   - answerId: {data.get('data', {}).get('answerId', 'N/A')}")
                print(f"   - 回复长度: {len(str(data.get('data', {}).get('answerBlocks', [])))} 字符")
                print(f"   - 引用数量: {len(data.get('data', {}).get('citations', []))}")
            else:
                print(f"❌ 请求失败: {response.text}")
            
            print("\n" + "=" * 60)
            print("📝 请查看后端日志中的 [PERF] 标记，分析延迟分布：")
            print("   - [PERF][xxx] 请求开始")
            print("   - [PERF][xxx] 初始化完成")
            print("   - [PERF][xxx] 开始任务规划")
            print("   - [PERF][xxx] 任务规划完成")
            print("   - [PERF][xxx] 开始 Agent 执行")
            print("   - [PERF][xxx] Agent 执行完成")
            print("   - [PERF][xxx] 开始输出合规检查")
            print("   - [PERF][xxx] 输出合规检查完成")
            print("   - [PERF][xxx] 请求结束")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")


if __name__ == "__main__":
    asyncio.run(test_chat_performance())
