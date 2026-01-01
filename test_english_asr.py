#!/usr/bin/env python3
# test_english_asr.py
# 测试中英文混合语音识别

import logging
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from core.asr_engine import get_asr_engine
from core.audio_capture import AudioCapture
from core.text_postprocessor import get_text_postprocessor

print("=" * 60)
print("中英文混合语音识别测试")
print("=" * 60)
print()
print("您可以测试以下内容：")
print("1. 纯中文：今天天气很好")
print("2. 纯英文：Hello world")
print("3. 中英混合：这个API很好用")
print("4. 英文单词：I used Python and Java")
print()
print("按住 Option 键开始说话，松开结束")
print("输入 'q' 退出")
print("=" * 60)
print()

asr_engine = get_asr_engine()
text_processor = get_text_postprocessor()

# 创建音频采集器
audio_capture = AudioCapture()
recording = False

def on_press():
    global recording
    recording = True
    print("\n🎤 开始录音...")
    audio_capture.start_recording()

def on_release():
    global recording
    recording = False
    print("\n⏹️ 停止录音")

    audio_data = audio_capture.stop_recording()
    if audio_data:
        # 识别
        text = asr_engine.recognize_bytes(audio_data)
        if text:
            # 文本处理
            processed = text_processor.process(text)
            print(f"\n识别结果: {text}")
            print(f"处理后:   {processed}")
            print("-" * 60)
        else:
            print("\n❌ 识别失败")
    else:
        print("\n❌ 没有录制到音频")

from core.hotkey_manager import HotkeyManager, HotkeyAction
hotkey_manager = HotkeyManager()

hotkey_manager.register_callback(HotkeyAction.VOICE_INPUT_PRESS, on_press)
hotkey_manager.register_callback(HotkeyAction.VOICE_INPUT_RELEASE, on_release)

if not hotkey_manager.start("option"):
    print("❌ 无法启动快捷键监听")
    sys.exit(1)

print("\n✅ 已启动，按住 Option 键开始说话...")
print()

import time
try:
    while True:
        cmd = input().strip()
        if cmd.lower() == 'q':
            break
except KeyboardInterrupt:
    pass

hotkey_manager.stop()
print("\n退出测试")
