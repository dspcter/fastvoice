#!/usr/bin/env python3
"""简化的快捷键测试脚本"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from pynput import keyboard
from pynput.keyboard import Key

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模拟原始版本的简单快捷键检测
pressed_keys = set()

def on_press(key):
    global pressed_keys

    key_str = str(key)
    if isinstance(key, Key):
        key_str = str(key).replace('Key.', '')

    logger.info(f"按键: {key_str}")

    # 简单的 Option 键检测
    if key_str == 'alt':
        logger.info("✓ 检测到 Option 键！语音输入应该触发！")

def on_release(key):
    key_str = str(key)
    if isinstance(key, Key):
        key_str = str(key).replace('Key.', '')
    logger.info(f"释放: {key_str}")

    if key_str == 'alt':
        logger.info("✓ Option 键释放！语音输入应该结束！")

    if key_str == 'esc':
        return False

print("=" * 60)
print("简单快捷键测试")
print("=" * 60)
print("请按 Option 键测试...")
print("按 ESC 退出")
print()

# 启动监听
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
