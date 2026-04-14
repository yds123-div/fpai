#!/usr/bin/env python3
"""
运行 AkShare 相关的所有测试。

使用方法：
    python tests/run_akshare_tests.py
    python tests/run_akshare_tests.py --verbose
    python tests/run_akshare_tests.py --client-only
    python tests/run_akshare_tests.py --formatter-only
"""

import subprocess
import sys
from pathlib import Path


def run_tests(test_files: list[str], verbose: bool = False) -> bool:
    """运行指定的测试文件。"""
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    cmd.extend(test_files)
    
    print(f"运行命令: {' '.join(cmd)}")
    print("-" * 60)
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    return result.returncode == 0


def main():
    """主函数。"""
    import argparse
    
    parser = argparse.ArgumentParser(description="运行 AkShare 相关测试")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--client-only", action="store_true", help="只运行 AkShareClient 测试")
    parser.add_argument("--formatter-only", action="store_true", help="只运行 fund_formatter 测试")
    
    args = parser.parse_args()
    
    # 确定要运行的测试文件
    test_files = []
    
    if args.client_only:
        test_files = [
            "tests/test_akshare_client.py",
            "tests/test_akshare_client_basic.py",
            "tests/test_akshare_cache.py",
        ]
    elif args.formatter_only:
        test_files = [
            "tests/test_fund_formatter_akshare.py",
        ]
    else:
        # 运行所有 AkShare 相关测试
        test_files = [
            "tests/test_akshare_client.py",
            "tests/test_akshare_client_basic.py", 
            "tests/test_akshare_cache.py",
            "tests/test_fund_formatter_akshare.py",
            "tests/test_akshare_integration.py",
            "tests/test_akshare_fund_data.py",
            "tests/test_akshare_nav_data.py",
            "tests/test_akshare_get_all_data.py",
        ]
    
    # 过滤存在的文件
    existing_files = []
    for file in test_files:
        if Path(file).exists():
            existing_files.append(file)
        else:
            print(f"警告: 测试文件不存在: {file}")
    
    if not existing_files:
        print("错误: 没有找到任何测试文件")
        return False
    
    print(f"将运行 {len(existing_files)} 个测试文件:")
    for file in existing_files:
        print(f"  - {file}")
    print()
    
    # 运行测试
    success = run_tests(existing_files, args.verbose)
    
    if success:
        print("\n✅ 所有测试通过!")
        return True
    else:
        print("\n❌ 部分测试失败!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)