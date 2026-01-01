#!/usr/bin/env python3
# test_marianmt.py
# 测试 MarianMT 翻译引擎

import logging
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

print("=" * 60)
print("MarianMT 翻译引擎测试")
print("=" * 60)

from models import get_model_manager, ModelType
from core import get_marianmt_engine

manager = get_model_manager()

# 检查模型是否已下载
print("\n1. 检查模型...")
zh_en_exists = manager.check_translation_model("marianmt-zh-en")
en_zh_exists = manager.check_translation_model("marianmt-en-zh")

print(f"   中文→英文模型: {'已下载' if zh_en_exists else '未下载'}")
print(f"   英文→中文模型: {'已下载' if en_zh_exists else '未下载'}")

# 自动下载模型（如果需要）
if not zh_en_exists:
    print("\n2. 下载中文→英文模型 (约300MB)...")
    print("   模型ID: Helsinki-NLP/opus-mt-zh-en")
    print("   开始下载...")
    manager.download_translation_model("marianmt-zh-en")

    # 等待下载完成
    print("   等待下载完成...")
    while manager.is_downloading("marianmt-zh-en"):
        time.sleep(2)

    # 再次检查
    zh_en_exists = manager.check_translation_model("marianmt-zh-en")
    if zh_en_exists:
        print("   下载完成!")
    else:
        print("   下载失败或未完成")
        sys.exit(1)

# 测试翻译
if zh_en_exists or manager.check_translation_model("marianmt-zh-en"):
    print("\n3. 测试中文→英文翻译...")
    engine = get_marianmt_engine("zh-en")

    test_cases = [
        "今天天气很好",
        "你好世界",
        "我喜欢这个",
        "今天天气怎么样",
        "这个问题很复杂",
    ]

    for text in test_cases:
        result = engine.translate(text)
        print(f"   '{text}' → '{result}'")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
