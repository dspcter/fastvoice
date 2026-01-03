#!/usr/bin/env python3
"""
测试 pynput 与 PyQt6 的兼容性

这个脚本测试在 PyQt6 环境下 pynput 是否能正常工作
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from pynput import keyboard
from pynput.keyboard import Key
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局标志
key_detected = False

def on_press(key):
    global key_detected
    key_detected = True

    key_str = str(key)
    if isinstance(key, Key):
        key_str = str(key).replace('Key.', '')

    logger.info(f"✓ pynput 检测到按键: {key_str}")

    if key_str == 'alt':
        logger.info("✓✓✓ Option 键被检测到！pynput 在 PyQt6 环境下工作正常！")

def on_release(key):
    key_str = str(key)
    if isinstance(key, Key):
        key_str = str(key).replace('Key.', '')
    logger.info(f"✓ pynput 检测到释放: {key_str}")

    if key_str == 'esc':
        return False  # 停止监听

def main():
    logger.info("=" * 60)
    logger.info("测试 pynput 与 PyQt6 的兼容性")
    logger.info("=" * 60)

    # 1. 先创建 PyQt6 应用
    logger.info("步骤 1: 创建 PyQt6 QApplication...")
    qt_app = QApplication(sys.argv)
    logger.info("✓ PyQt6 QApplication 已创建")

    # 2. 启动 pynput listener
    logger.info("步骤 2: 启动 pynput keyboard listener...")
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release,
        suppress=False
    )
    listener.start()

    import time
    time.sleep(1.0)  # 等待 listener 启动

    if not listener.is_alive:
        logger.error("❌ Listener 启动失败！")
        return 1

    logger.info(f"✓ pynput listener 已启动 (alive={listener.is_alive})")

    # 3. 设置定时器在 10 秒后检查结果
    def check_result():
        logger.info("=" * 60)
        if key_detected:
            logger.info("✓ 测试成功：pynput 在 PyQt6 环境下工作正常")
        else:
            logger.error("❌ 测试失败：10 秒内没有检测到任何键盘事件")
            logger.error("这表明 PyQt6 与 pynput 存在冲突")
        logger.info("=" * 60)
        qt_app.quit()

    timer = QTimer()
    timer.singleShot(10000, check_result)  # 10 秒后检查

    # 4. 进入 Qt 事件循环
    logger.info("步骤 3: 进入 Qt 事件循环...")
    logger.info("请在 10 秒内按任意键（特别是 Option 键）...")
    logger.info("按 ESC 可提前退出测试")

    exit_code = qt_app.exec()

    # 清理
    listener.stop()
    logger.info(f"测试结束，退出码: {exit_code}")

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
