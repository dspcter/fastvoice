# core/text_injector.py
# 文字注入模块 (v1.4.0 - macOS 原生按键模拟)

import logging
import time
from typing import Optional

import pyperclip

from config import IS_MACOS, IS_WINDOWS

# v1.4.0: 全局标志，表示正在执行文字注入（用于防止监听器拦截）
_is_injecting = False

# v1.4.0: macOS 原生按键模拟（优先）
if IS_MACOS:
    try:
        from core.text_injector_macos import get_macos_injector
        MACOS_NATIVE_AVAILABLE = True
    except ImportError:
        MACOS_NATIVE_AVAILABLE = False
        logger.warning("text_injector_macos 不可用，将使用 pyautogui 后备方案")
else:
    MACOS_NATIVE_AVAILABLE = False

# pyautogui 作为后备方案（非 macOS 或 macOS 原生不可用时）
pyautogui = None
if not IS_MACOS or not MACOS_NATIVE_AVAILABLE:
    try:
        import pyautogui
        pyautogui.PAUSE = 0.01  # 每次操作后暂停 10ms
        if IS_MACOS:
            pyautogui.DARWIN_CATCH_UP_TIME = 0.05  # macOS 增加延迟
    except ImportError:
        pyautogui = None
        logger.warning("pyautogui 不可用")

logger = logging.getLogger(__name__)


class TextInjector:
    """
    文字注入器 (v1.4.0)

    支持多种注入方式:
    1. clipboard - 剪贴板 + 模拟粘贴 (兼容性最好，默认)
    2. typing - 逐字符模拟输入 (仅支持 ASCII)
    3. win32_native - Windows 原生 SendInput (不污染剪贴板)

    v1.4.0 改进：
    - macOS: 使用 Quartz CGEvent 原生按键模拟，解决 Command+V 不可靠问题
    - 更可靠的组合键模拟
    - 内置验证和重试机制
    """

    def __init__(self, method: str = "clipboard"):
        """
        初始化文字注入器

        Args:
            method: 注入方式 ("clipboard", "typing", "win32_native")
        """
        self.method = method

        # v1.4.0: macOS 原生按键模拟器（优先）
        self._macos_injector = None
        if IS_MACOS and MACOS_NATIVE_AVAILABLE:
            self._macos_injector = get_macos_injector()
            if self._macos_injector:
                logger.info("使用 macOS 原生按键模拟器")
            else:
                logger.warning("macOS 原生按键模拟器初始化失败，将使用后备方案")

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

        v1.4.0 改进：
        - macOS: 优先使用 PyObjC 原生模拟
        - pyautogui 作为后备方案（仅 PyObjC 不可用时）
        - 内置验证和重试机制

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        global _is_injecting

        # v1.4.0: macOS 优先使用 PyObjC 原生模拟
        if IS_MACOS and self._macos_injector:
            _is_injecting = True
            try:
                logger.info("使用 PyObjC 原生按键模拟器")
                result = self._macos_injector.paste_with_clipboard(text, verify=True)
                return result
            finally:
                _is_injecting = False

        # pyautogui 作为后备方案（仅在 PyObjC 不可用时）
        if IS_MACOS and pyautogui:
            _is_injecting = True
            try:
                logger.warning("PyObjC 不可用，使用 pyautogui 后备方案")
                result = self._inject_by_clipboard_fallback(text)
                return result
            finally:
                _is_injecting = False

        # 最后的后备方案
        _is_injecting = True
        try:
            logger.warning("PyObjC 和 pyautogui 都不可用，尝试最后的后备方案")
            result = self._inject_by_clipboard_fallback(text)
            return result
        finally:
            _is_injecting = False

    def _inject_by_clipboard_fallback(self, text: str) -> bool:
        """
        通过剪贴板注入文字（后备方案，使用 pyautogui）

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        global _is_injecting

        if pyautogui is None:
            logger.error("pyautogui 不可用，无法使用后备方案")
            return False

        max_retries = 3  # 最大重试次数

        # 获取粘贴快捷键
        paste_hotkey = ["command", "v"] if IS_MACOS else ["ctrl", "v"]

        for attempt in range(max_retries):
            try:
                # 设置注入标志（防止监听器拦截）
                _is_injecting = True

                # 保存当前剪贴板内容
                original_clipboard = pyperclip.paste()
                logger.info(f"[尝试 {attempt + 1}/{max_retries}] 原剪贴板长度: {len(original_clipboard)}")

                # 设置新内容到剪贴板
                pyperclip.copy(text)
                logger.info(f"剪贴板已设置为: '{text[:30]}...'")

                # 等待剪贴板更新
                time.sleep(0.15)

                # 验证剪贴板内容是否正确写入
                current_clipboard = pyperclip.paste()
                if current_clipboard != text:
                    if attempt < max_retries - 1:
                        logger.warning(f"剪贴板内容被其他程序修改，重试 ({attempt + 1}/{max_retries})")
                        time.sleep(0.05)
                        continue
                    else:
                        logger.error("剪贴板冲突，多次重试后仍失败")
                        return False

                logger.info(f"剪贴板验证通过，准备发送 {paste_hotkey}...")

                # 模拟粘贴 (使用 pyautogui)
                pyautogui.hotkey(*paste_hotkey)
                logger.info(f"pyautogui.hotkey({paste_hotkey}) 已执行")

                # 等待粘贴完成（增加延迟）
                time.sleep(0.5)

                # 恢复原剪贴板内容
                pyperclip.copy(original_clipboard)
                logger.info(f"剪贴板已恢复，原内容长度: {len(original_clipboard)}")

                logger.info(f"✓ 文字注入完成: {text[:20]}...")

                return True

            except Exception as e:
                logger.error(f"剪贴板注入失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.1)
                else:
                    return False
            finally:
                # 清除注入标志
                _is_injecting = False

        return False

    def _inject_by_typing(self, text: str) -> bool:
        """
        通过逐字符输入注入文字

        注意：此方法仅支持 ASCII 字符
        中文文本请使用 clipboard 方式

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        # v1.4.0: macOS 优先使用原生按键模拟器
        if IS_MACOS and self._macos_injector:
            return self._macos_injector.type_text(text, interval=0.01)

        # 后备方案：使用 pyautogui
        if pyautogui is None:
            logger.error("pyautogui 不可用，无法使用逐字符输入")
            return False

        try:
            # 逐字符输入
            pyautogui.write(text, interval=0.01)

            logger.debug(f"已注入文字 (输入+pyautogui): {text[:20]}...")
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
