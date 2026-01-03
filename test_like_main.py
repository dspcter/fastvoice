#!/usr/bin/env python3
"""
模拟主应用的启动流程，测试 pynput 是否工作
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from pynput import keyboard
from pynput.keyboard import Key
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer
from config import get_settings
from core import HotkeyManager
from core.hotkey_manager import HotkeyAction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局标志
key_detected = False

def create_tray_icon(qt_app: QApplication) -> QSystemTrayIcon:
    """创建托盘图标（模拟主应用）"""
    tray_icon = QSystemTrayIcon()
    menu = QMenu()

    # 打开设置
    settings_action = QAction("打开设置", qt_app)
    menu.addAction(settings_action)

    menu.addSeparator()

    # 退出
    quit_action = QAction("退出", qt_app)
    quit_action.triggered.connect(qt_app.quit)
    menu.addAction(quit_action)

    tray_icon.setContextMenu(menu)
    tray_icon.show()

    return tray_icon

def main():
    logger.info("=" * 60)
    logger.info("模拟主应用启动流程测试")
    logger.info("=" * 60)

    # 步骤 1: 创建 Qt 应用（与主应用相同）
    logger.info("步骤 1: 创建 PyQt6 QApplication...")
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    logger.info("✓ PyQt6 QApplication 已创建")

    # 步骤 2: 获取设置（模拟 FastVoiceApp.__init__）
    logger.info("步骤 2: 加载设置...")
    settings = get_settings()
    logger.info(f"✓ 设置已加载, 语音快捷键: {settings.voice_input_hotkey}")

    # 步骤 3: 创建 HotkeyManager（模拟 FastVoiceApp.__init__）
    logger.info("步骤 3: 创建 HotkeyManager...")
    hotkey_manager = HotkeyManager()
    logger.info("✓ HotkeyManager 已创建")

    # 步骤 4: 创建托盘图标（与主应用相同顺序）
    logger.info("步骤 4: 创建托盘图标...")
    tray_icon = create_tray_icon(qt_app)
    logger.info("✓ 托盘图标已创建")

    # 步骤 5: 注册回调并启动 listener（与主应用相同）
    logger.info("步骤 5: 注册回调并启动 listener...")

    def on_voice_press():
        logger.info("✓✓✓ 语音输入回调被触发！")
        global key_detected
        key_detected = True

    def on_voice_release():
        logger.info("✓✓✓ 语音输入释放回调被触发！")

    hotkey_manager.register_callback(
        HotkeyAction.VOICE_INPUT_PRESS,
        on_voice_press
    )
    hotkey_manager.register_callback(
        HotkeyAction.VOICE_INPUT_RELEASE,
        on_voice_release
    )
    logger.info("✓ 回调已注册")

    # 启动 listener
    voice_hotkey = settings.voice_input_hotkey
    translate_hotkey = settings.quick_translate_hotkey
    if not hotkey_manager.start(voice_hotkey, translate_hotkey):
        logger.error("❌ Listener 启动失败")
        return 1
    logger.info("✓ Listener 已启动")

    # 步骤 6: 设置定时器检查结果
    def check_result():
        logger.info("=" * 60)
        if key_detected:
            logger.info("✓ 测试成功：快捷键检测工作正常")
        else:
            logger.error("❌ 测试失败：没有检测到快捷键")
            logger.error("请检查日志中是否有 [KEYBOARD EVENT] 输出")
        logger.info("=" * 60)
        qt_app.quit()

    timer = QTimer()
    timer.singleShot(15000, check_result)  # 15 秒后检查

    # 步骤 7: 进入 Qt 事件循环
    logger.info("=" * 60)
    logger.info("步骤 6: 进入 Qt 事件循环...")
    logger.info("请在 15 秒内按 Option 键测试...")
    logger.info("=" * 60)

    exit_code = qt_app.exec()

    # 清理
    hotkey_manager.stop()
    logger.info(f"测试结束，退出码: {exit_code}")

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
