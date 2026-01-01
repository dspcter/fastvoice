#!/usr/bin/env python3
# test_updates.py
# 测试更新后的翻译和文本处理

import logging
from core.text_postprocessor import TextPostProcessor
from core.translate_engine import get_translate_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

print("=" * 60)
print("测试1: 文本处理规则")
print("=" * 60)

processor = TextPostProcessor(use_ai=False)

text_tests = [
    "嗯嗯今天天气真不错啊",
    "那个那个我想问一下这个问题怎么解决呢",
    "啊啊今天天气怎么样",
    "呃呃这个问题很复杂啊",
    "你好",
    "今天天气很好",
    "这个地方真是太美了",
]

for text in text_tests:
    result = processor.process(text)
    print(f"'{text}' → '{result}'")

print("\n" + "=" * 60)
print("测试2: 翻译功能")
print("=" * 60)

translator = get_translate_engine()

translation_tests = [
    ("今天天气很好", "en"),
    ("你好世界", "en"),
    ("我喜欢这个", "en"),
]

for text, target_lang in translation_tests:
    result = translator.translate(text, target_lang)
    print(f"'{text}' → {target_lang}: '{result}'")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
