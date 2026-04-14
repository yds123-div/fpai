#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 AkShare 库是否正常工作
"""
import pytest


def test_akshare_import():
    """测试 AkShare 是否已安装"""
    try:
        import akshare as ak
        assert ak is not None
        print(f"\n✅ AkShare 已安装，版本：{ak.__version__}")
    except ImportError as e:
        pytest.fail(f"❌ AkShare 未安装：{e}")


def test_akshare_fund_name_em():
    """测试获取基金名称列表（东方财富）"""
    try:
        import akshare as ak
        
        print("\n正在调用 ak.fund_name_em() 获取基金列表...")
        df = ak.fund_name_em()
        
        assert df is not None, "返回数据为空"
        assert len(df) > 0, "未获取到任何基金数据"
        
        print(f"✅ 成功获取 {len(df)} 条基金数据")
        print("\n前 5 条数据：")
        print(df.head())
        
        # 检查必要的列是否存在
        expected_columns = ["基金代码", "基金简称"]
        for col in expected_columns:
            assert col in df.columns, f"缺少必要列：{col}"
        
        print(f"\n✅ 数据结构正确，包含列：{list(df.columns)}")
        
    except Exception as e:
        pytest.fail(f"❌ 调用 fund_name_em 失败：{e}")


def test_akshare_fund_open_fund_rank_em():
    """测试获取开放式基金排行榜（东方财富）"""
    try:
        import akshare as ak
        
        print("\n正在调用 ak.fund_open_fund_rank_em() 获取基金排行...")
        df = ak.fund_open_fund_rank_em(symbol="全部")
        
        assert df is not None, "返回数据为空"
        assert len(df) > 0, "未获取到任何排行数据"
        
        print(f"✅ 成功获取 {len(df)} 条基金排行数据")
        print("\n前 3 条数据：")
        print(df.head(3))
        
    except Exception as e:
        pytest.fail(f"❌ 调用 fund_open_fund_rank_em 失败：{e}")


def test_akshare_fund_individual_basic_info_xq():
    """测试获取单只基金基本信息（雪球）"""
    try:
        import akshare as ak
        
        # 使用一个常见的基金代码测试
        test_symbol = "161039"  # 富国通胀通缩主题轮动混合A
        
        print(f"\n正在调用 ak.fund_individual_basic_info_xq(symbol={test_symbol})...")
        df = ak.fund_individual_basic_info_xq(symbol=test_symbol)
        
        assert df is not None, "返回数据为空"
        
        print(f"✅ 成功获取基金 {test_symbol} 的基本信息")
        print("\n数据内容：")
        print(df)
        
    except Exception as e:
        # 雪球接口可能不稳定，给出警告而不是失败
        print(f"⚠️  雪球接口调用失败（可能是网络或接口限制）：{e}")
        pytest.skip(f"雪球接口暂时不可用：{e}")


def test_akshare_network_connectivity():
    """测试网络连接性"""
    try:
        import akshare as ak
        
        print("\n测试网络连接...")
        # 尝试获取少量数据测试网络
        df = ak.fund_name_em()
        
        if df is not None and len(df) > 0:
            print("✅ 网络连接正常，可以访问东方财富数据源")
        else:
            print("⚠️  网络连接可能存在问题，返回数据为空")
            
    except Exception as e:
        print(f"❌ 网络连接测试失败：{e}")
        print("提示：请检查服务器是否能访问外网（东方财富、雪球等网站）")
        pytest.fail(f"网络连接失败：{e}")


if __name__ == "__main__":
    """直接运行此文件进行快速测试"""
    print("=" * 60)
    print("AkShare 功能测试")
    print("=" * 60)
    
    # 测试 1：导入
    print("\n[测试 1/5] 检查 AkShare 是否已安装...")
    try:
        test_akshare_import()
    except Exception as e:
        print(f"失败：{e}")
        exit(1)
    
    # 测试 2：基金名称列表
    print("\n[测试 2/5] 测试获取基金名称列表...")
    try:
        test_akshare_fund_name_em()
    except Exception as e:
        print(f"失败：{e}")
    
    # 测试 3：基金排行榜
    print("\n[测试 3/5] 测试获取基金排行榜...")
    try:
        test_akshare_fund_open_fund_rank_em()
    except Exception as e:
        print(f"失败：{e}")
    
    # 测试 4：单只基金信息
    print("\n[测试 4/5] 测试获取单只基金信息...")
    try:
        test_akshare_fund_individual_basic_info_xq()
    except Exception as e:
        print(f"失败：{e}")
    
    # 测试 5：网络连接
    print("\n[测试 5/5] 测试网络连接...")
    try:
        test_akshare_network_connectivity()
    except Exception as e:
        print(f"失败：{e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
