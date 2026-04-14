"""演示14字段标准输出功能"""

import sys
import json

# 模拟基金数据（基于你提供的图片中的 000042 基金）
mock_fund_data = {
    "symbol": "000042",
    "basic_info": {
        "ok": True,
        "data": [
            {"item": "基金代码", "value": "000042"},
            {"item": "基金名称", "value": "中证财通可持续发展100指数A"},
            {"item": "基金全称", "value": "财通可持续发展主题股票型证券投资基金"},
            {"item": "成立时间", "value": "2013-02-06"},
            {"item": "最新规模", "value": "0.42亿"},
            {"item": "基金公司", "value": "财通基金管理有限公司"},
            {"item": "基金经理", "value": "姚思劼"},
            {"item": "托管银行", "value": "中国工商银行股份有限公司"},
            {"item": "基金类型", "value": "股票型"},
            {"item": "评级机构", "value": "null"},
            {"item": "基金评级", "value": "暂无评级"},
            {"item": "投资策略", "value": "本基金采用完全复制法，按照成份股在标的指数中的基准权重构建指数化投资组合。"},
            {"item": "投资目标", "value": "紧密跟踪标的指数，追求跟踪偏离度和跟踪误差最小化。"},
            {"item": "业绩比较基准", "value": "中证财通可持续发展100指数收益率×95%+银行活期存款利率(税后)×5%"},
        ]
    }
}

# 导入格式化函数
sys.path.insert(0, '.')
from pkg.fund_formatter import format_standard_14_fields_table

# 生成14字段表格
table_section = format_standard_14_fields_table(mock_fund_data)

if table_section:
    print("\n" + "="*80)
    print(f"📋 {table_section['title']}")
    print("="*80)
    
    headers = table_section['table']['headers']
    rows = table_section['table']['rows']
    
    # 打印表格
    print(f"\n{headers[0]:<20} | {headers[1]}")
    print("-"*80)
    
    for i, row in enumerate(rows, 1):
        field = row.get('字段', '')
        content = row.get('内容', '')
        print(f"{i:2d}. {field:<18} | {content}")
    
    print("-"*80)
    print(f"\n✅ 成功输出 {len(rows)} 个字段")
    
    # 输出 JSON 格式
    print("\n" + "="*80)
    print("📄 JSON 格式输出:")
    print("="*80)
    print(json.dumps(table_section, ensure_ascii=False, indent=2))
    
else:
    print("❌ 无法生成14字段表格")
