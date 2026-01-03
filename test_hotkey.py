#!/usr/bin/env python3
# 测试快捷键监听

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=" * 60)
print("快捷键监听测试")
print("=" * 60)
print("请按下 Option 键（语音输入快捷键）...")
print("按 Ctrl+C 退出")
print()

# 记录按键
def on_press(key):
    key_str = str(key)
    key_type = type(key).__name__
    logger.info(f"按下: {key_str} (类型: {key_type})")

    # 检查是否是 Option 键
    if isinstance(key, Key):
        key_name = str(key).replace('Key.', '')
        logger.info(f"  -> 特殊键: {key_name}")
        if key_name == 'alt':
            logger.info("  -> 这是 Option/Alt 键！")
    elif isinstance(key, KeyCode):
        if hasattr(key, 'char'):
            logger.info(f"  -> 字符键: char={key.char}")

def on_release(key):
    key_str = str(key)
    logger.debug(f"释放: {key_str}")

    if key == keyboard.Key.esc:
        logger.info("检测到 ESC 键，退出...")
        return False

# 启动监听
try:
    with keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    ) as listener:
        listener.join()
except KeyboardInterrupt:
    logger.info("用户中断，退出...")
