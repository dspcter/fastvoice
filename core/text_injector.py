# core/text_injector.py
# 文字注入模块 (模拟键盘输入)

import logging
import time
from typing import Optional

import pyautogui
import pyperclip

from config import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)

# pyautogui 设置
pyautogui.PAUSE = 0.01  # 每次操作后暂停 10ms
pyautogui.DARWIN_CATCH_UP_TIME = 0.01 if IS_MACOS else 0


class TextInjector:
    """
    文字注入器

    将文字输入到当前光标位置
    支持两种方式:
    1. 剪贴板 + 模拟粘贴 (兼容性最好)
    2. 逐字符模拟输入 (支持更多输入法)
    """

    def __init__(self, method: str = "clipboard"):
        """
        初始化文字注入器

        Args:
            method: 注入方式 ("clipboard" 或 "typing")
        """
        self.method = method

        # 获取粘贴快捷键
        if IS_MACOS:
            self._paste_hotkey = ["command", "v"]
        else:
            self._paste_hotkey = ["ctrl", "v"]

        logger.info(f"文字注入器初始化完成 (方式: {method})")

    def inject(self, text: str) -> bool:
        """
        注入文字到光标位置

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        if not text:
            return True

        if self.method == "clipboard":
            return self._inject_by_clipboard(text)
        else:
            return self._inject_by_typing(text)

    def _inject_by_clipboard(self, text: str) -> bool:
        """
        通过剪贴板注入文字

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        try:
            # 保存当前剪贴板内容
            original_clipboard = pyperclip.paste()

            # 设置新内容到剪贴板
            pyperclip.copy(text)

            # 等待剪贴板更新
            time.sleep(0.05)

            # 模拟粘贴
            pyautogui.hotkey(*self._paste_hotkey)

            # 等待粘贴完成
            time.sleep(0.1)

            # 恢复原剪贴板内容
            pyperclip.copy(original_clipboard)

            logger.debug(f"已注入文字 (剪贴板): {text[:20]}...")
            return True

        except Exception as e:
            logger.error(f"剪贴板注入失败: {e}")
            return False

    def _inject_by_typing(self, text: str) -> bool:
        """
        通过逐字符输入注入文字

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        try:
            # 逐字符输入
            pyautogui.write(text, interval=0.01)

            logger.debug(f"已注入文字 (输入): {text[:20]}...")
            return True

        except Exception as e:
            logger.error(f"输入注入失败: {e}")
            return False

    def set_method(self, method: str) -> None:
        """
        设置注入方式

        Args:
            method: "clipboard" 或 "typing"
        """
        if method in ["clipboard", "typing"]:
            self.method = method
            logger.info(f"注入方式已更改为: {method}")
        else:
            logger.warning(f"无效的注入方式: {method}")

    def get_method(self) -> str:
        """获取当前注入方式"""
        return self.method


# ==================== 单例 ====================

_text_injector = None


def get_text_injector(method: str = "clipboard") -> TextInjector:
    """获取全局文字注入器实例"""
    global _text_injector
    if _text_injector is None:
        _text_injector = TextInjector(method)
    return _text_injector


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    injector = get_text_injector()

    # 测试注入
    print("3 秒后将注入测试文字，请将光标移动到文本输入位置...")
    time.sleep(3)

    injector.inject("快人快语 - 测试文字注入")
    print("注入完成!")
