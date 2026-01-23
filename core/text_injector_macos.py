# core/text_injector_macos.py
# macOS 原生按键模拟器 (使用 Quartz CGEvent)
#
# v1.4.0 新增：替代 pyautogui，提供更可靠的按键模拟
#
# 核心特性：
# - 使用 Quartz CGEvent API，直接调用系统底层接口
# - 精确控制按键时序，解决组合键分离问题
# - 支持 Command+V 等组合键
# - 内置验证和重试机制

import logging
import threading
import time
from typing import Optional, List, Tuple

import pyperclip

from config import IS_MACOS

logger = logging.getLogger(__name__)

# v1.4.3: 全局标志，表示应用正在清理（防止 cleanup 触发意外行为）
_is_cleaning_up = False

# 只在 macOS 上导入 Quartz
if IS_MACOS:
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            CGEventSourceCreate,
            CGEventSetFlags,             # 设置事件标志
            kCGEventKeyDown,
            kCGEventKeyUp,
            kCGSessionEventTap,
            kCGHIDEventTap,              # HID 事件 tap (更可靠)
            kCGEventFlagMaskCommand,     # Command 键标志
            kCGEventFlagMaskControl,     # Control 键标志
            kCGEventFlagMaskAlternate,   # Option/Alt 键标志
            kCGEventFlagMaskShift,       # Shift 键标志
        )
        NATIVE_AVAILABLE = True
    except ImportError:
        NATIVE_AVAILABLE = False
        logger.warning("PyObjC 未安装，macOS 原生按键模拟不可用")
else:
    NATIVE_AVAILABLE = False


# ==================== macOS 虚拟键码映射 ====================

class macOSKeyCode:
    """macOS 虚拟键码常量

    参考: https://developer.apple.com/documentation/coregraphics/1536125-virtual-key-codes
    """
    # 字母键 (QWERTY 布局)
    A_KEY = 0x00        # A 键
    B_KEY = 0x0B        # B 键
    C_KEY = 0x08        # C 键
    D_KEY = 0x02        # D 键
    E_KEY = 0x0E        # E 键
    F_KEY = 0x03        # F 键
    G_KEY = 0x05        # G 键
    H_KEY = 0x04        # H 键
    I_KEY = 0x22        # I 键
    J_KEY = 0x26        # J 键
    K_KEY = 0x28        # K 键
    L_KEY = 0x25        # L 键
    M_KEY = 0x2E        # M 键
    N_KEY = 0x2D        # N 键
    O_KEY = 0x1F        # O 键
    P_KEY = 0x23        # P 键
    Q_KEY = 0x0C        # Q 键
    R_KEY = 0x0F        # R 键
    S_KEY = 0x01        # S 键
    T_KEY = 0x11        # T 键
    U_KEY = 0x20        # U 键
    V_KEY = 0x09        # V 键 (用于粘贴) ✓ 修复
    W_KEY = 0x0D        # W 键
    X_KEY = 0x07        # X 键 (用于剪切)
    Y_KEY = 0x10        # Y 键
    Z_KEY = 0x06        # Z 键 (用于撤销)

    # 功能键
    SPACE = 0x31        # 空格
    TAB = 0x30          # Tab
    ENTER = 0x24        # 回车
    ESC = 0x35          # Esc
    BACKSPACE = 0x33    # 退格
    DELETE = 0x75       # Delete (向前删除)


# ==================== macOS 原生按键模拟器 ====================

class MacOSTextInjector:
    """
    macOS 原生按键模拟器 (v1.4.0)

    使用 Quartz CGEvent API 实现可靠的按键模拟

    核心优势：
    - 直接调用系统底层 API，无 AppleScript 中间层
    - 精确控制按键时序，避免组合键分离
    - 支持 Command+V、Command+C 等组合键
    - 内置验证和重试机制
    - 异常安全：确保修饰键在异常时也能释放

    使用场景：
    - 模拟粘贴 (Command+V)
    - 模拟复制 (Command+C)
    - 模拟其他快捷键
    """

    def __init__(self):
        """初始化按键模拟器"""
        if not NATIVE_AVAILABLE:
            raise RuntimeError("macOS 原生按键模拟不可用，请安装 PyObjC")

        # 创建事件源（使用 kCGEventSourceStateCombinedSessionState = 0）
        self._event_source = CGEventSourceCreate(0)

        # 按键延迟配置（毫秒）
        self._key_delay = 0.01          # 按键间隔 10ms
        self._combo_delay = 0.05        # 组合键保持时间 50ms (增加以确保识别)
        self._post_delay = 0.10         # 按键后等待 100ms (增加以确保处理)

        # v1.4.1: 按键状态跟踪（用于异常恢复）
        self._pressed_keys = []         # 当前按下的键列表 (keycode, name)
        self._lock = threading.RLock()  # 保护状态的可重入锁

        logger.info("macOS 原生按键模拟器初始化完成")

    def paste(self) -> bool:
        """
        模拟粘贴操作 (Command+V)

        Returns:
            是否成功
        """
        return self._hotkey(kCGEventFlagMaskCommand, macOSKeyCode.V_KEY)

    def copy(self) -> bool:
        """
        模拟复制操作 (Command+C)

        Returns:
            是否成功
        """
        return self._hotkey(kCGEventFlagMaskCommand, macOSKeyCode.C_KEY)

    def cut(self) -> bool:
        """
        模拟剪切操作 (Command+X)

        Returns:
            是否成功
        """
        return self._hotkey(kCGEventFlagMaskCommand, macOSKeyCode.X_KEY)

    def select_all(self) -> bool:
        """
        模拟全选操作 (Command+A)

        Returns:
            是否成功
        """
        return self._hotkey(kCGEventFlagMaskCommand, macOSKeyCode.A_KEY)

    def undo(self) -> bool:
        """
        模拟撤销操作 (Command+Z)

        Returns:
            是否成功
        """
        return self._hotkey(kCGEventFlagMaskCommand, macOSKeyCode.Z_KEY)

    def _hotkey(self, flags: int, key_code: int) -> bool:
        """
        模拟组合键 (使用正确的按键序列)

        macOS 组合键的正确模拟方式：
        1. 按下修饰键（如 Command）
        2. 按下主键（如 V）
        3. 释放主键
        4. 释放修饰键

        v1.4.1 改进：使用 try-finally 确保修饰键在异常时也能释放

        Args:
            flags: 修饰键标志 (如 kCGEventFlagMaskCommand)
            key_code: 虚拟键码 (如 macOSKeyCode.V_KEY)

        Returns:
            是否成功
        """
        # 根据标志确定需要按下的修饰键
        modifier_keycodes = []
        if flags & kCGEventFlagMaskCommand:
            modifier_keycodes.append((0x37, kCGEventFlagMaskCommand, "Command"))
        if flags & kCGEventFlagMaskControl:
            modifier_keycodes.append((0x3B, kCGEventFlagMaskControl, "Control"))
        if flags & kCGEventFlagMaskAlternate:
            modifier_keycodes.append((0x3A, kCGEventFlagMaskAlternate, "Option"))
        if flags & kCGEventFlagMaskShift:
            modifier_keycodes.append((0x38, kCGEventFlagMaskShift, "Shift"))

        modifier_names = [name for _, _, name in modifier_keycodes]
        logger.info(f"⌨ 模拟组合键: {'+'.join(modifier_names)} + keycode={key_code:#x}")

        try:
            # 计算标志位（用于主键事件）
            event_flags = 0
            for _, flag, _ in modifier_keycodes:
                event_flags |= flag

            # 1. 按下所有修饰键
            for mod_keycode, _, mod_name in modifier_keycodes:
                mod_down = CGEventCreateKeyboardEvent(self._event_source, mod_keycode, True)
                CGEventPost(kCGSessionEventTap, mod_down)
                # 记录按下的键
                with self._lock:
                    self._pressed_keys.append((mod_keycode, mod_name))
                logger.info(f"  ⌘ 按下修饰键: {mod_name} (keycode={mod_keycode:#x})")
                time.sleep(0.01)

            # 2. 按下主键（此时修饰键已按下，需要设置标志位）
            key_down = CGEventCreateKeyboardEvent(self._event_source, key_code, True)
            CGEventSetFlags(key_down, event_flags)  # 设置修饰键标志位
            CGEventPost(kCGSessionEventTap, key_down)
            with self._lock:
                self._pressed_keys.append((key_code, f"key_{key_code:#x}"))
            logger.info(f"  ⌨ 按下主键: keycode={key_code:#x} (flags={event_flags:#x})")
            time.sleep(self._combo_delay)

            # 3. 释放主键（也需要设置标志位）
            key_up = CGEventCreateKeyboardEvent(self._event_source, key_code, False)
            CGEventSetFlags(key_up, event_flags)  # 设置修饰键标志位
            CGEventPost(kCGSessionEventTap, key_up)
            with self._lock:
                # 从列表中移除主键
                self._pressed_keys = [(kc, n) for kc, n in self._pressed_keys if kc != key_code]
            logger.info(f"  ⌨ 释放主键: keycode={key_code:#x}")
            time.sleep(0.01)

            # 等待系统处理
            time.sleep(self._post_delay)

            logger.info(f"✓ 组合键模拟完成")
            return True

        except Exception as e:
            logger.error(f"模拟组合键失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

        finally:
            # v1.4.1: 确保所有修饰键都被释放（即使发生异常）
            logger.info("  🧹 清理修饰键状态...")
            for mod_keycode, _, mod_name in reversed(modifier_keycodes):
                try:
                    mod_up = CGEventCreateKeyboardEvent(self._event_source, mod_keycode, False)
                    CGEventPost(kCGSessionEventTap, mod_up)
                    with self._lock:
                        # 从列表中移除已释放的键
                        self._pressed_keys = [(kc, n) for kc, n in self._pressed_keys if kc != mod_keycode]
                    logger.info(f"  ⌘ 释放修饰键: {mod_name} (keycode={mod_keycode:#x})")
                    time.sleep(0.01)
                except Exception as cleanup_error:
                    logger.error(f"释放修饰键 {mod_name} 失败: {cleanup_error}")

            # 额外确认：确保列表为空
            with self._lock:
                if self._pressed_keys:
                    logger.warning(f"⚠ 仍有按键未释放: {self._pressed_keys}")
                    # 强制清空列表
                    self._pressed_keys = []

    def cleanup(self) -> None:
        """
        v1.5.1: 清理按键状态（不发送事件）

        在以下情况调用：
        1. 程序退出时
        2. 检测到异常状态时

        设计原则：
        - 应用退出后不应有任何按键行为
        - Event Tap 会在监听器停止时被禁用
        - 只需清空状态追踪，不发送任何按键事件
        - 系统会自动恢复按键状态
        """
        global _is_cleaning_up
        _is_cleaning_up = True

        with self._lock:
            if not self._pressed_keys:
                logger.debug("🧹 [MacOSInjector] cleanup: 没有需要释放的键")
                _is_cleaning_up = False
                return

            logger.warning(f"🧹 [MacOSInjector] cleanup: 清空 {len(self._pressed_keys)} 个按键状态追踪（不发送事件）")

            # 只清空状态追踪，不发送任何按键事件
            # 原因：
            # 1. 应用已退出或正在退出，不应发送任何事件
            # 2. Event Tap 已被禁用，不会有事件冲突
            # 3. 系统会自动恢复按键状态
            pressed_count = len(self._pressed_keys)
            self._pressed_keys = []

            logger.info(f"✓ [MacOSInjector] cleanup 完成：已清空 {pressed_count} 个按键状态追踪")
            _is_cleaning_up = False

    def type_text(self, text: str, interval: float = 0.01) -> bool:
        """
        逐字符输入文本 (仅支持 ASCII)

        注意：此方法仅支持 ASCII 字符，中文请使用 paste_with_clipboard()

        Args:
            text: 要输入的文本
            interval: 字符间隔（秒）

        Returns:
            是否成功
        """
        try:
            for char in text:
                # 检查是否为 ASCII 字符
                if ord(char) > 127:
                    logger.warning(f"跳过非 ASCII 字符: '{char}' (U+{ord(char):04X})")
                    continue

                # 获取键码
                key_code = self._char_to_keycode(char)
                if key_code is None:
                    logger.warning(f"无法映射字符: '{char}'")
                    continue

                # 按下并释放
                self._press_and_release(key_code)
                time.sleep(interval)

            return True

        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False

    def _press_and_release(self, key_code: int) -> None:
        """按下并释放单个按键"""
        key_down = CGEventCreateKeyboardEvent(self._event_source, key_code, True)
        key_up = CGEventCreateKeyboardEvent(self._event_source, key_code, False)

        CGEventPost(kCGSessionEventTap, key_down)  # 使用 SessionEventTap
        time.sleep(self._key_delay)
        CGEventPost(kCGSessionEventTap, key_up)  # 使用 SessionEventTap

    def _char_to_keycode(self, char: str) -> Optional[int]:
        """
        将字符转换为 macOS 虚拟键码

        Args:
            char: 单个字符

        Returns:
            虚拟键码，如果不支持则返回 None
        """
        # ASCII 键码映射
        if 'a' <= char <= 'z':
            return 0x00 + (ord(char) - ord('a'))
        elif 'A' <= char <= 'Z':
            return 0x00 + (ord(char) - ord('A'))
        elif '0' <= char <= '9':
            return 0x1D + (ord(char) - ord('0'))
        elif char == ' ':
            return macOSKeyCode.SPACE
        elif char == '\t':
            return macOSKeyCode.TAB
        elif char == '\n':
            return macOSKeyCode.ENTER
        elif char == '\r':
            return macOSKeyCode.ENTER
        else:
            return None

    def paste_with_clipboard(self, text: str, verify: bool = True) -> bool:
        """
        通过剪贴板粘贴文本（带验证和重试）

        v1.4.3: 增强日志输出，便于观察退出时的行为

        Args:
            text: 要粘贴的文本
            verify: 是否验证粘贴成功

        Returns:
            是否成功
        """
        global _is_cleaning_up

        # v1.4.3: 检查是否正在清理
        if _is_cleaning_up:
            logger.warning("🛑 [MacOSInjector] 正在清理中，跳过粘贴")
            return False

        max_retries = 3

        logger.info(f"📋 [MacOSInjector] 开始剪贴板粘贴流程")
        logger.info(f"   文本内容: '{text[:100]}...' (总长度: {len(text)})")
        logger.info(f"   最大重试次数: {max_retries}")

        # v1.5.1: 在外层保存剪贴板，确保在异常时也能恢复
        original_clipboard = pyperclip.paste() or ""  # 处理 None 的情况
        logger.debug(f"   原剪贴板长度: {len(original_clipboard)}")

        try:
            for attempt in range(max_retries):
                # 每次循环开始时检查清理状态
                if _is_cleaning_up:
                    logger.warning(f"🛑 [MacOSInjector] 检测到清理信号，中止粘贴 (尝试 {attempt + 1}/{max_retries})")
                    return False

                try:
                    logger.info(f"🔄 [MacOSInjector] 尝试 {attempt + 1}/{max_retries}")

                    # 设置新内容到剪贴板
                    logger.debug(f"   设置新剪贴板内容...")
                    pyperclip.copy(text)

                    # 等待剪贴板更新
                    time.sleep(0.1)

                    # 验证剪贴板内容（如果启用）
                    if verify:
                        current_clipboard = pyperclip.paste()
                        if current_clipboard != text:
                            if attempt < max_retries - 1:
                                logger.warning(f"   剪贴板内容被修改，重试 ({attempt + 1}/{max_retries})")
                                time.sleep(0.05)
                                continue
                            else:
                                logger.error("✗ [MacOSInjector] 剪贴板冲突，多次重试后仍失败")
                                return False
                        logger.debug(f"   剪贴板验证通过")

                    # 模拟 Command+V 粘贴
                    logger.info(f"   ⌨️  模拟 Command+V 粘贴...")
                    if not self.paste():
                        if attempt < max_retries - 1:
                            logger.warning(f"   粘贴失败，重试 ({attempt + 1}/{max_retries})")
                            time.sleep(0.1)
                            continue
                        else:
                            logger.error("✗ [MacOSInjector] 多次重试后粘贴仍失败")
                            return False

                    logger.info(f"   ✓ Command+V 已执行")

                    # 等待粘贴完成（增加延迟以确保应用有时间处理粘贴）
                    time.sleep(0.3)

                    logger.info(f"✅ [MacOSInjector] 粘贴成功: '{text[:30]}...'")
                    return True

                except Exception as e:
                    logger.error(f"✗ [MacOSInjector] 剪贴板粘贴失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                    else:
                        return False

            logger.error(f"✗ [MacOSInjector] 所有重试均失败")
            return False

        finally:
            # v1.4.7: 总是恢复剪贴板，防止退出时剪贴板残留注入文本
            try:
                pyperclip.copy(original_clipboard)
                logger.debug(f"✓ [MacOSInjector] 剪贴板已恢复")
            except Exception as e:
                logger.error(f"✗ [MacOSInjector] 恢复剪贴板失败: {e}")


# ==================== 工厂函数 ====================

def get_macos_injector() -> Optional[MacOSTextInjector]:
    """
    获取 macOS 原生按键模拟器实例

    Returns:
        MacOSTextInjector 实例，如果不可用则返回 None
    """
    if IS_MACOS and NATIVE_AVAILABLE:
        try:
            return MacOSTextInjector()
        except Exception as e:
            logger.error(f"创建 macOS 按键模拟器失败: {e}")
            return None
    else:
        return None


# ==================== 测试代码 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("="*60)
    print("macOS 原生按键模拟器测试")
    print("="*60)

    injector = get_macos_injector()
    if not injector:
        print("❌ 无法创建按键模拟器")
        exit(1)

    print("\n测试将在 3 秒后开始...")
    print("请将光标移动到文本输入位置\n")

    time.sleep(3)

    # 测试 1: 简单粘贴
    print("测试 1: 模拟粘贴 'Hello macOS!'")
    injector.paste_with_clipboard("Hello macOS!")

    time.sleep(1)

    # 测试 2: 中文粘贴
    print("\n测试 2: 模拟粘贴 '你好世界'")
    injector.paste_with_clipboard("你好世界")

    time.sleep(1)

    # 测试 3: 组合键
    print("\n测试 3: 模拟全选 (Command+A)")
    injector.select_all()

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)
