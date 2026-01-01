#!/usr/bin/env python3
# test_enhanced_rules.py
# 测试增强的规则文本处理

import logging
from core.text_postprocessor import TextPostProcessor

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

print("=" * 60)
print("测试增强规则文本处理")
print("=" * 60)

# 创建处理器（不使用AI，使用增强规则）
processor = TextPostProcessor(use_ai=False)

# 测试用例
test_cases = [
    ("嗯嗯今天天气真不错啊", "今天天气真不错！"),
    ("那个那个我想问一下这个问题怎么解决呢", "我想问一下这个问题怎么解决呢？"),
    ("你知道就是那个怎么说呢就是那个事情对吧", "你知道就是那个事情对吧。"),
    ("啊啊今天天气怎么样", "今天天气怎么样？"),
    ("呃呃我想想啊这个问题很复杂", "我想想啊这个问题很复杂。"),
    ("嗯嗯你好", "你好。"),
    ("今天天气很好", "今天天气很好。"),
    ("这个地方真是太美了", "这个地方真是太美了！"),
]

print("\n测试结果:")
print("-" * 60)

all_passed = True
for original, expected in test_cases:
    result = processor.process(original)
    passed = result == expected
    all_passed = all_passed and passed

    status = "✅" if passed else "❌"
    print(f"{status} 原文: {original}")
    print(f"   期望: {expected}")
    print(f"   结果: {result}")
    if not passed:
        print(f"   ⚠️  不匹配!")
    print()

print("=" * 60)
if all_passed:
    print("✅ 所有测试通过!")
else:
    print("❌ 部分测试未通过，继续优化...")
print("=" * 60)
