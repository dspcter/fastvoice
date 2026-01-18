# core/windows_native_injector.py
# Windows 原生文字注入模块 (SendInput + Unicode)

import logging
from typing import List

from config import IS_WINDOWS

logger = logging.getLogger(__name__)

# Windows API 常量
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class WindowsNativeInjector:
    """
    Windows 原生文字注入器

    使用 Windows SendInput API + KEYEVENTF_UNICODE 直接发送 Unicode 字符

    优势：
    - ✅ 不污染剪贴板
    - ✅ 完整 Unicode 支持（emoji、特殊符号）
    - ✅ 不受输入法影响
    - ✅ 速度快（直接 API 调用）

    仅限 Windows 平台
    """

    def __init__(self):
        self._available = IS_WINDOWS
        self._ctypes = None
        self._wintypes = None

        if self._available:
            try:
                import ctypes
                from ctypes import wintypes

                self._ctypes = ctypes
                self._wintypes = wintypes

                # 定义结构体
                class KEYBDINPUT(self._ctypes.Structure):
                    _fields_ = [
                        ("wVk", wintypes.WORD),
                        ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD),
                        ("dwExtraInfo", self._ctypes.c_ulong)
                    ]

                class INPUT(self._ctypes.Structure):
                    class _INPUT_I(self._ctypes.Union):
                        _fields_ = [("ki", KEYBDINPUT)]

                    _anonymous_ = ("_input_i",)
                    _fields_ = [
                        ("type", wintypes.DWORD),
                        ("_input_i", _INPUT_I),
                        ("padding", self._ctypes.c_ubyte * 8)
                    ]

                self.KEYBDINPUT = KEYBDINPUT
                self.INPUT = INPUT

                logger.info("WindowsNativeInjector 初始化成功")

            except ImportError as e:
                logger.warning(f"ctypes 不可用: {e}")
                self._available = False
            except Exception as e:
                logger.error(f"WindowsNativeInjector 初始化失败: {e}")
                self._available = False

    def is_available(self) -> bool:
        """检查是否可用"""
        return self._available

    def inject(self, text: str) -> bool:
        """
        注入文字到当前光标位置

        Args:
            text: 要注入的文字

        Returns:
            是否成功
        """
        if not self._available:
            logger.warning("WindowsNativeInjector 不可用（非 Windows 平台或初始化失败）")
            return False

        if not text:
            return True

        try:
            # 准备输入数组
            inputs = []

            for char in text:
                # 按下
                inp_down = self.INPUT()
                inp_down.type = INPUT_KEYBOARD
                inp_down.ki.wScan = ord(char)
                inp_down.ki.dwFlags = KEYEVENTF_UNICODE
                inputs.append(inp_down)

                # 释放
                inp_up = self.INPUT()
                inp_up.type = INPUT_KEYBOARD
                inp_up.ki.wScan = ord(char)
                inp_up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                inputs.append(inp_up)

            # 调用 SendInput
            user32 = self._ctypes.windll.user32
            result = user32.SendInput(
                len(inputs),
                self._ctypes.byref(inputs[0]),
                self._ctypes.sizeof(self.INPUT)
            )

            if result == len(inputs):
                logger.debug(f"Windows 原生注入成功: {len(text)} 字符")
                return True
            else:
                logger.error(f"SendInput 返回值不匹配: {result} != {len(inputs)}")
                return False

        except Exception as e:
            logger.error(f"Windows 原生注入失败: {e}")
            return False

    def __repr__(self) -> str:
        return f"WindowsNativeInjector(available={self._available})"


# ==================== 单例 ====================

_windows_injector: Optional[WindowsNativeInjector] = None


def get_windows_injector() -> Optional[WindowsNativeInjector]:
    """获取 Windows 原生注入器实例"""
    global _windows_injector
    if _windows_injector is None:
        _windows_injector = WindowsNativeInjector()
    return _windows_injector


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import time

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    injector = get_windows_injector()

    if not injector.is_available():
        print("Windows 原生注入不可用（需要在 Windows 上运行）")
        print("测试模式：模拟注入")
        print(f"将注入: '你好 World! 🚀'")
    else:
        print("Windows 原生注入器已就绪")
        print("3 秒后将注入测试文字，请将光标移动到文本输入位置...")
        time.sleep(3)

        # 测试注入（包含中文、英文、emoji）
        test_text = "你好 World! 🚀 This is a test: 测试中文、English、😊"
        injector.inject(test_text)
        print(f"已注入: {test_text}")
