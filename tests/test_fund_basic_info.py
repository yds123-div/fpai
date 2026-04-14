"""
测试查询基金基本信息。

用于查看 AkShare 返回的基金数据结构。
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加 backend 到路径
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from pkg.akshare_client import AkShareClient


async def test_fund_basic_info(fund_code: str = "000029"):
    """测试获取基金基本信息。
    
    Args:
        fund_code: 基金代码（6位数字）
    """
    print(f"\n{'='*80}")
    print(f"查询基金 {fund_code} 的基本信息")
    print(f"{'='*80}\n")
    
    client = AkShareClient()
    
    try:
        # 1. 获取基本信息
        print("📋 基本信息 (fund_individual_basic_info_xq):")
        print("-" * 80)
        basic_info = await client.get_basic_info(fund_code)
        
        if basic_info.get("ok"):
            data = basic_info.get("data")
            print(f"\n✅ 获取成功")
            print(f"数据类型: {type(data)}")
            
            if isinstance(data, list) and len(data) > 0:
                print(f"数据条数: {len(data)}")
                print(f"\n第一条数据的字段:")
                for key, value in data[0].items():
                    print(f"  {key}: {value}")
            else:
                print(f"\n数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
        else:
            print(f"❌ 获取失败: {basic_info.get('message')}")
        
        # 2. 获取业绩数据
        print(f"\n\n{'='*80}")
        print("📈 业绩数据 (fund_individual_achievement_xq):")
        print("-" * 80)
        achievement = await client.get_achievement(fund_code)
        
        if achievement.get("ok"):
            data = achievement.get("data")
            print(f"\n✅ 获取成功")
            print(f"数据类型: {type(data)}")
            
            if isinstance(data, list) and len(data) > 0:
                print(f"数据条数: {len(data)}")
                print(f"\n前 3 条数据:")
                for i, record in enumerate(data[:3]):
                    print(f"\n  [{i+1}] {json.dumps(record, ensure_ascii=False, indent=4)}")
            else:
                print(f"\n数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
        else:
            print(f"❌ 获取失败: {achievement.get('message')}")
        
        # 3. 获取分析数据
        print(f"\n\n{'='*80}")
        print("📊 分析数据 (fund_individual_analysis_xq):")
        print("-" * 80)
        analysis = await client.get_analysis(fund_code)
        
        if analysis.get("ok"):
            data = analysis.get("data")
            print(f"\n✅ 获取成功")
            print(f"数据类型: {type(data)}")
            
            if isinstance(data, list) and len(data) > 0:
                print(f"数据条数: {len(data)}")
                print(f"\n数据内容:")
                for record in data:
                    print(f"  {json.dumps(record, ensure_ascii=False, indent=4)}")
            else:
                print(f"\n数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
        else:
            print(f"❌ 获取失败: {analysis.get('message')}")
        
        print(f"\n\n{'='*80}")
        print("✅ 测试完成")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 可以通过命令行参数指定基金代码
    fund_code = sys.argv[1] if len(sys.argv) > 1 else "000029"
    asyncio.run(test_fund_basic_info(fund_code))
