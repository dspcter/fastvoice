# core/text_injector.py
# 文字注入模块 (P0 重构版 - 支持 Windows 原生注入)

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
    文字注入器 (P0 重构版)

    支持多种注入方式:
    1. clipboard - 剪贴板 + 模拟粘贴 (兼容性最好，默认)
    2. typing - 逐字符模拟输入 (支持更多输入法)
    3. win32_native - Windows 原生 SendInput (P0 新增，不污染剪贴板)

    P0 改进：
    - Windows 原生注入支持
    - 不污染用户剪贴板
    - 完整 Unicode 支持
    """

    def __init__(self, method: str = "clipboard"):
        """
        初始化文字注入器

        Args:
            method: 注入方式 ("clipboard", "typing", "win32_native")
        """
        self.method = method

        # 获取粘贴快捷键
        if IS_MACOS:
            self._paste_hotkey = ["command", "v"]
        else:
            self._paste_hotkey = ["ctrl", "v"]

        # Windows 原生注入器 (懒加载)
        self._win32_injector = None

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
            logger.debug("文字为空，跳过注入")
            return True

        logger.info(f"开始注入文字: '{text}' (方式: {self.method})")

        # P0: Windows 原生注入
        if self.method == "win32_native":
            result = self._inject_by_win32_native(text)
        elif self.method == "clipboard":
            result = self._inject_by_clipboard(text)
        else:  # typing
            result = self._inject_by_typing(text)

        if result:
            logger.info(f"✓ 文字注入成功: '{text}'")
        else:
            logger.error(f"✗ 文字注入失败: '{text}'")

        return result

    def _inject_by_win32_native(self, text: str) -> bool:
        """
        Windows 原生注入 - P0 新增

        使用 SendInput API + KEYEVENTF_UNICODE

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        if not IS_WINDOWS:
            logger.warning("win32_native 仅在 Windows 上可用")
            # 回退到剪贴板方式
            return self._inject_by_clipboard(text)

        try:
            # 懒加载 Windows 注入器
            if self._win32_injector is None:
                from core.windows_native_injector import get_windows_injector
                self._win32_injector = get_windows_injector()

            # 检查是否可用
            if not self._win32_injector.is_available():
                logger.warning("Windows 原生注入不可用，回退到剪贴板方式")
                return self._inject_by_clipboard(text)

            # 使用 Windows 原生注入
            success = self._win32_injector.inject(text)

            if success:
                logger.debug(f"已注入文字 (Win32 原生): {text[:20]}...")
                return True
            else:
                # 失败时回退到剪贴板方式
                logger.warning("Windows 原生注入失败，回退到剪贴板方式")
                return self._inject_by_clipboard(text)

        except Exception as e:
            logger.error(f"Windows 原生注入异常: {e}，回退到剪贴板方式")
            return self._inject_by_clipboard(text)

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
            method: "clipboard", "typing", "win32_native"
        """
        valid_methods = ["clipboard", "typing", "win32_native"]

        if method in valid_methods:
            # Windows 原生注入需要平台检查
            if method == "win32_native" and not IS_WINDOWS:
                logger.warning("win32_native 仅在 Windows 上可用，使用 clipboard")
                method = "clipboard"

            self.method = method
            logger.info(f"注入方式已更改为: {method}")
        else:
            logger.warning(f"无效的注入方式: {method}，有效值: {valid_methods}")

    def get_method(self) -> str:
        """获取当前注入方式"""
        return self.method

    def get_available_methods(self) -> list:
        """
        获取当前平台可用的注入方式

        Returns:
            可用方法列表
        """
        methods = ["clipboard", "typing"]
        if IS_WINDOWS:
            methods.append("win32_native")
        return methods


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
