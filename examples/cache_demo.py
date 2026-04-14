"""
AkShareClient 缓存机制演示。

演示如何使用缓存机制来提升性能和减少 API 调用。
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from pkg.akshare_client import AkShareClient


async def demo_cache_hit():
    """演示缓存命中场景。"""
    print("=" * 60)
    print("演示 1: 缓存命中场景")
    print("=" * 60)
    
    client = AkShareClient(cache_ttl=300, enable_cache=True)
    
    # 第一次调用 - 缓存未命中，会调用 API
    print("\n第一次调用 get_basic_info('000001')...")
    start_time = time.time()
    result1 = await client.get_basic_info("000001")
    elapsed1 = time.time() - start_time
    print(f"耗时: {elapsed1:.3f}秒")
    print(f"结果: {'成功' if result1['ok'] else '失败'}")
    
    # 第二次调用 - 缓存命中，直接返回缓存数据
    print("\n第二次调用 get_basic_info('000001')...")
    start_time = time.time()
    result2 = await client.get_basic_info("000001")
    elapsed2 = time.time() - start_time
    print(f"耗时: {elapsed2:.3f}秒")
    print(f"结果: {'成功' if result2['ok'] else '失败'}")
    
    # 显示缓存统计
    print("\n缓存统计:")
    stats = client.get_cache_stats()
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    print(f"  命中率: {stats['hit_rate']:.2f}%")
    print(f"  缓存条目数: {stats['cache_size']}")
    
    print(f"\n性能提升: {elapsed1 / elapsed2:.1f}x 倍")


async def demo_cache_expiration():
    """演示缓存过期场景。"""
    print("\n" + "=" * 60)
    print("演示 2: 缓存过期场景")
    print("=" * 60)
    
    # 使用 2 秒的 TTL
    client = AkShareClient(cache_ttl=2, enable_cache=True, request_interval=0.1)
    
    # 第一次调用
    print("\n第一次调用 get_basic_info('000001')...")
    result1 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result1['ok'] else '失败'}")
    
    # 立即第二次调用 - 缓存命中
    print("\n立即第二次调用 get_basic_info('000001')...")
    result2 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result2['ok'] else '失败'}")
    
    # 等待缓存过期
    print("\n等待 2.5 秒，让缓存过期...")
    await asyncio.sleep(2.5)
    
    # 第三次调用 - 缓存已过期，重新调用 API
    print("\n第三次调用 get_basic_info('000001')（缓存已过期）...")
    result3 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result3['ok'] else '失败'}")
    
    # 显示缓存统计
    print("\n缓存统计:")
    stats = client.get_cache_stats()
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    print(f"  命中率: {stats['hit_rate']:.2f}%")


async def demo_different_params():
    """演示不同参数使用不同缓存。"""
    print("\n" + "=" * 60)
    print("演示 3: 不同参数使用不同缓存")
    print("=" * 60)
    
    client = AkShareClient(cache_ttl=300, enable_cache=True)
    
    # 调用不同的基金代码
    print("\n调用 get_basic_info('000001')...")
    result1 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result1['ok'] else '失败'}")
    
    print("\n调用 get_basic_info('000002')...")
    result2 = await client.get_basic_info("000002")
    print(f"结果: {'成功' if result2['ok'] else '失败'}")
    
    # 再次调用第一个基金代码 - 缓存命中
    print("\n再次调用 get_basic_info('000001')...")
    result3 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result3['ok'] else '失败'}")
    
    # 显示缓存统计
    print("\n缓存统计:")
    stats = client.get_cache_stats()
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    print(f"  命中率: {stats['hit_rate']:.2f}%")
    print(f"  缓存条目数: {stats['cache_size']}")


async def demo_cache_disabled():
    """演示禁用缓存。"""
    print("\n" + "=" * 60)
    print("演示 4: 禁用缓存")
    print("=" * 60)
    
    client = AkShareClient(cache_ttl=300, enable_cache=False)
    
    # 多次调用同一个基金代码
    print("\n第一次调用 get_basic_info('000001')...")
    result1 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result1['ok'] else '失败'}")
    
    print("\n第二次调用 get_basic_info('000001')...")
    result2 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result2['ok'] else '失败'}")
    
    print("\n第三次调用 get_basic_info('000001')...")
    result3 = await client.get_basic_info("000001")
    print(f"结果: {'成功' if result3['ok'] else '失败'}")
    
    # 显示缓存统计
    print("\n缓存统计:")
    stats = client.get_cache_stats()
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    print(f"  命中率: {stats['hit_rate']:.2f}%")
    print(f"  缓存条目数: {stats['cache_size']}")
    print("\n注意: 禁用缓存时，每次都会调用 API，缓存命中率为 0%")


async def demo_cache_management():
    """演示缓存管理功能。"""
    print("\n" + "=" * 60)
    print("演示 5: 缓存管理功能")
    print("=" * 60)
    
    client = AkShareClient(cache_ttl=300, enable_cache=True)
    
    # 调用几个不同的基金
    print("\n调用多个基金...")
    await client.get_basic_info("000001")
    await client.get_basic_info("000002")
    await client.get_basic_info("000003")
    
    # 显示缓存统计
    print("\n初始缓存统计:")
    stats = client.get_cache_stats()
    print(f"  缓存条目数: {stats['cache_size']}")
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    
    # 清空缓存
    print("\n清空缓存...")
    client.clear_cache()
    
    stats = client.get_cache_stats()
    print(f"  缓存条目数: {stats['cache_size']}")
    print(f"  缓存命中: {stats['cache_hits']} (统计保留)")
    print(f"  缓存未命中: {stats['cache_misses']} (统计保留)")
    
    # 重置统计
    print("\n重置缓存统计...")
    client.reset_cache_stats()
    
    stats = client.get_cache_stats()
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")


async def main():
    """运行所有演示。"""
    print("\n" + "=" * 60)
    print("AkShareClient 缓存机制演示")
    print("=" * 60)
    
    try:
        # 演示 1: 缓存命中
        await demo_cache_hit()
        
        # 演示 2: 缓存过期
        await demo_cache_expiration()
        
        # 演示 3: 不同参数
        await demo_different_params()
        
        # 演示 4: 禁用缓存
        await demo_cache_disabled()
        
        # 演示 5: 缓存管理
        await demo_cache_management()
        
        print("\n" + "=" * 60)
        print("所有演示完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
