#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标点恢复集成测试
"""

import sys
import os

# Get the directory of this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add the fastvoice directory to the path
sys.path.insert(0, SCRIPT_DIR)

# Add the CT-Transformer-punctuation directory to the path
ct_transformer_dir = os.path.join(SCRIPT_DIR, 'external', 'CT-Transformer-punctuation')
sys.path.insert(0, ct_transformer_dir)

# Import cttPunctuator first (needed by punctuation_restorer)
from cttPunctuator import CttPunctuator

# Direct import to avoid the __init__.py issue
import importlib.util
spec = importlib.util.spec_from_file_location(
    'punctuation_restorer',
    os.path.join(SCRIPT_DIR, 'core/punctuation_restorer.py')
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PunctuationRestorer = module.PunctuationRestorer


def main():
    """测试标点恢复功能"""
    print(f'=== 标点恢复器测试 ===')
    restorer = PunctuationRestorer()

    print(f'模型路径: {restorer._model_path}')
    print(f'模型存在: {os.path.exists(restorer._model_path)}')
    print()

    if not restorer.initialize():
        print('❌ 模型初始化失败')
        return 1

    print(f'✅ 模型初始化成功')
    print()

    test_cases = [
        ('今天天气很好我们去公园吧', '今天天气很好，我们去公园吧。'),
        ('你好请问这个多少钱', '你好，请问这个多少钱？'),
        ('对这个字没问题', '对这个字，没问题。'),
        ('为什么这样啊', '为什么这样啊？'),
        ('太棒了真的很棒', '太棒了，真的很棒！'),
    ]

    print(f'=== 标点恢复测试 ===')
    passed = 0
    total = len(test_cases)
    for test_text, expected in test_cases:
        result = restorer.restore(test_text)
        match = '✅' if result == expected else '⚠️'
        if result == expected:
            passed += 1
        print(f'{match} 输入: {test_text}')
        print(f'   期望: {expected}')
        print(f'   实际: {result}')
        print()

    print(f'准确率: {passed}/{total} ({passed*100//total}%)')
    print(f'✅ 测试完成！')
    return 0


if __name__ == '__main__':
    sys.exit(main())
