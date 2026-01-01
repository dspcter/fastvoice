#!/usr/bin/env python3
# test_workflow.py
# 测试完整工作流程：ASR → 文本处理 → 翻译

import logging
from core.text_postprocessor import get_text_postprocessor
from core.translate_engine import get_translate_engine

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

print("=" * 60)
print("测试工作流程")
print("=" * 60)

# 模拟 ASR 识别结果
asr_output = "嗯嗯今天天气真不错啊"

print(f"\n1. ASR 识别结果: {asr_output}")

# 初始化处理器
text_processor = get_text_postprocessor()
translate_engine = get_translate_engine()

# 场景1: 语音输入（不翻译）
print("\n--- 场景1: 语音输入（不翻译）---")
processed_text = text_processor.process(asr_output)
print(f"文本处理结果: {processed_text}")
print(f"→ 注入: {processed_text}")

# 场景2: 快速翻译（AI文本处理 + 翻译）
print("\n--- 场景2: 快速翻译（AI文本处理开启）---")
# 假设用户启用了AI文本处理
text_processor.use_ai = True
processed_for_translation = text_processor.process(asr_output)
print(f"文本处理结果: {processed_for_translation}")

translated = translate_engine.translate(processed_for_translation, "en")
print(f"翻译结果: {translated}")
print(f"→ 注入: {translated}")

# 场景3: 快速翻译（AI文本处理关闭）
print("\n--- 场景3: 快速翻译（AI文本处理关闭）---")
text_processor.use_ai = False
processed_no_ai = text_processor.process(asr_output)
print(f"文本处理结果(规则): {processed_no_ai}")

translated_no_ai = translate_engine.translate(processed_no_ai, "en")
print(f"翻译结果: {translated_no_ai}")
print(f"→ 注入: {translated_no_ai}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
