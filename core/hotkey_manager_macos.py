# core/hotkey_manager_macos.py
# macOS 原生全局快捷键管理器 (使用 AppKit/NSEvent)
# 替代 pynput，解决 macOS 上的稳定性问题

import logging
import threading
from enum import Enum
from typing import Callable, Dict, Optional, Set

from config import IS_MACOS

# 只在 macOS 上导入
if IS_MACOS:
    try:
        from AppKit import NSApp, NSApplication
        from PyObjCTools import AppHelper
        import objc
        from Cocoa import (
            NSEvent,
            NSKeyDownMask,
            NSFlagsChanged,
            NSCommandKeyMask,
            NSAlternateKeyMask,
            NSControlKeyMask,
            NSShiftKeyMask,
        )
        NATIVE_AVAILABLE = True
    except ImportError:
        NATIVE_AVAILABLE = False
        logging.warning("PyObjC 未安装，将使用降级方案")
else:
    NATIVE_AVAILABLE = False

logger = logging.getLogger(__name__)


class HotkeyAction(Enum):
    """快捷键动作类型"""
    VOICE_INPUT_PRESS = "voice_input_press"
    VOICE_INPUT_RELEASE = "voice_input_release"
    QUICK_TRANSLATE_PRESS = "quick_translate_press"
    QUICK_TRANSLATE_RELEASE = "quick_translate_release"


class HotkeyState(Enum):
    """快捷键状态机"""
    IDLE = "idle"
    VOICE_RECORDING = "voice_recording"
    TRANSLATE_RECORDING = "translate_recording"


class MacOSHotkeyManager:
    """
    macOS 原生快捷键管理器

    使用 AppKit/NSEvent 实现全局快捷键监听

    优势:
    - 使用 macOS 原生 API，更可靠
    - 不会有 pynput 的 CGEventTap 失效问题
    - 更好的性能和稳定性

    限制:
    - 仅支持 macOS
    - 需要安装 PyObjC
    """

    # 防抖时间 (毫秒)
    DEBOUNCE_MS = 50

    def __init__(self):
        self._callbacks: Dict[HotkeyAction, Callable] = {}
        self._hotkeys: Dict[str, Dict] = {}  # 存储快捷键配置

        # 当前按下的所有按键
        self._pressed_keys: Set[str] = set()

        # 状态机
        self._state = HotkeyState.IDLE
        self._state_lock = threading.RLock()

        # 防抖
        self._last_keydown_time: Dict[str, float] = {}

        # NSEvent 监听器
        self._event_monitor = None
        self._event_handlers = []

        # 修饰键状态
        self._modifier_flags = 0

        logger.info("macOS 原生快捷键管理器初始化完成")

    def register_callback(self, action: HotkeyAction, callback: Callable) -> None:
        """注册快捷键动作回调"""
        self._callbacks[action] = callback
        logger.debug(f"注册回调: {action.value}")

    def parse_hotkey(self, hotkey_str: str) -> Dict:
        """
        解析快捷键字符串

        支持格式:
        - "fn" (macOS)
        - "ctrl+shift+t"
        - "cmd+space" (macOS)

        Returns:
            包含修饰键和字符的字典
        """
        if not hotkey_str:
            return {}

        parts = hotkey_str.lower().replace(" ", "").split("+")

        hotkey_info = {
            "cmd": False,
            "ctrl": False,
            "alt": False,
            "shift": False,
            "key": None,
            "key_code": None,
        }

        for part in parts:
            if part in ["cmd", "command", "win"]:
                hotkey_info["cmd"] = True
            elif part in ["ctrl", "control"]:
                hotkey_info["ctrl"] = True
            elif part in ["alt", "option"]:
                hotkey_info["alt"] = True
            elif part == "shift":
                hotkey_info["shift"] = True
            elif part == "fn":
                # Fn 键映射到 Alt
                hotkey_info["alt"] = True
            elif len(part) == 1:
                # 单个字符键
                hotkey_info["key"] = part.lower()
            else:
                # 功能键
                key_codes = {
                    "space": 49,
                    "tab": 48,
                    "enter": 36,
                    "return": 36,
                    "esc": 53,
                    "up": 126,
                    "down": 125,
                    "left": 123,
                    "right": 124,
                    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
                    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
                    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
                }
                if part in key_codes:
                    hotkey_info["key_code"] = key_codes[part]

        return hotkey_info

    def set_hotkey(self, name: str, hotkey_str: str) -> bool:
        """设置快捷键"""
        hotkey_info = self.parse_hotkey(hotkey_str)
        if not hotkey_info:
            logger.warning(f"快捷键解析失败: {hotkey_str}")
            return False

        self._hotkeys[name] = hotkey_info
        logger.info(f"快捷键已设置: {name} = {hotkey_str}")
        return True

    def start(self, voice_input_hotkey: str, translate_hotkey: str) -> bool:
        """启动快捷键监听"""
        if not NATIVE_AVAILABLE:
            logger.error("PyObjC 不可用，无法启动 macOS 原生快捷键")
            return False

        # 设置快捷键
        if not self.set_hotkey("voice_input", voice_input_hotkey):
            return False
        if not self.set_hotkey("quick_translate", translate_hotkey):
            return False

        try:
            # 创建全局事件监听器
            self._setup_event_monitor()

            logger.info("✓ macOS 原生快捷键监听器已启动")
            return True

        except Exception as e:
            logger.error(f"启动快捷键监听器失败: {e}")
            return False

    def _setup_event_monitor(self):
        """设置 NSEvent 全局监听器"""

        def event_handler(callback):
            def handler(event):
                try:
                    self._handle_event(event)
                except Exception as e:
                    logger.error(f"处理事件失败: {e}")
                return event  # 不拦截事件，继续传递
            return handler

        # 注册全局事件监听器
        # 使用 NSKeyDownMask 监听按键按下
        self._event_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSKeyDownMask,
            event_handler(None)
        )

        logger.info("NSEvent 全局监听器已设置")

    def _handle_event(self, event):
        """处理 NSEvent"""
        try:
            # 获取按键信息
            key_code = event.keyCode()
            modifier_flags = event.modifierFlags()

            # 检查修饰键
            cmd_pressed = bool(modifier_flags & NSCommandKeyMask)
            ctrl_pressed = bool(modifier_flags & NSControlKeyMask)
            alt_pressed = bool(modifier_flags & NSAlternateKeyMask)
            shift_pressed = bool(modifier_flags & NSShiftKeyMask)

            # 获取字符
            characters = event.characters()
            if characters and len(characters) > 0:
                char = characters.lower()[0]
            else:
                char = None

            # 构建当前按键状态
            current_hotkey = {
                "cmd": cmd_pressed,
                "ctrl": ctrl_pressed,
                "alt": alt_pressed,
                "shift": shift_pressed,
                "key": char,
                "key_code": key_code,
            }

            # 检查是否匹配快捷键
            self._check_hotkey_match("voice_input", current_hotkey)
            self._check_hotkey_match("quick_translate", current_hotkey)

        except Exception as e:
            logger.error(f"处理 NSEvent 失败: {e}")

    def _check_hotkey_match(self, name: str, current_hotkey: Dict):
        """检查当前按键是否匹配快捷键"""
        if name not in self._hotkeys:
            return

        target = self._hotkeys[name]

        # 检查修饰键
        if (target.get("cmd") != current_hotkey.get("cmd") or
            target.get("ctrl") != current_hotkey.get("ctrl") or
            target.get("alt") != current_hotkey.get("alt") or
            target.get("shift") != current_hotkey.get("shift")):
            return

        # 检查按键
        target_key = target.get("key")
        target_code = target.get("key_code")

        if target_key and target_key == current_hotkey.get("key"):
            # 匹配成功
            self._trigger_hotkey_action(name)
        elif target_code and target_code == current_hotkey.get("key_code"):
            # 匹配成功（使用 key_code）
            self._trigger_hotkey_action(name)

    def _trigger_hotkey_action(self, name: str):
        """触发快捷键动作"""
        with self._state_lock:
            if self._state != HotkeyState.IDLE:
                logger.debug(f"状态非 IDLE ({self._state.value})，忽略快捷键")
                return

            if name == "voice_input":
                if self._transition_state(HotkeyState.VOICE_RECORDING):
                    logger.info("语音输入: 开始录音 (macOS 原生)")
                    self._trigger_callback(HotkeyAction.VOICE_INPUT_PRESS)
            elif name == "quick_translate":
                if self._transition_state(HotkeyState.TRANSLATE_RECORDING):
                    logger.info("快速翻译: 开始录音 (macOS 原生)")
                    self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_PRESS)

    def _transition_state(self, new_state: HotkeyState) -> bool:
        """状态转换"""
        valid_transitions = {
            HotkeyState.IDLE: [HotkeyState.VOICE_RECORDING, HotkeyState.TRANSLATE_RECORDING],
            HotkeyState.VOICE_RECORDING: [HotkeyState.IDLE],
            HotkeyState.TRANSLATE_RECORDING: [HotkeyState.IDLE],
        }

        if new_state not in valid_transitions.get(self._state, []):
            return False

        old_state = self._state
        self._state = new_state
        logger.debug(f"状态转换: {old_state.value} → {new_state.value}")
        return True

    def reset_state(self) -> None:
        """重置状态到 IDLE"""
        with self._state_lock:
            if self._state != HotkeyState.IDLE:
                old_state = self._state
                self._state = HotkeyState.IDLE
                logger.info(f"状态重置: {old_state.value} → IDLE")

                # 触发对应的释放回调
                if old_state == HotkeyState.VOICE_RECORDING:
                    self._trigger_callback(HotkeyAction.VOICE_INPUT_RELEASE)
                elif old_state == HotkeyState.TRANSLATE_RECORDING:
                    self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_RELEASE)

    def get_state(self) -> HotkeyState:
        """获取当前状态"""
        return self._state

    def _trigger_callback(self, action: HotkeyAction) -> None:
        """触发回调函数"""
        callback = self._callbacks.get(action)
        if callback:
            try:
                callback()
            except Exception as e:
                logger.error(f"回调执行失败 ({action.value}): {e}")
        else:
            logger.warning(f"未注册回调: {action.value}")

    def stop(self) -> None:
        """停止快捷键监听"""
        if self._event_monitor:
            try:
                # NSEvent 的监听器会自动清理，无需手动停止
                self._event_monitor = None
                logger.info("macOS 原生快捷键监听器已停止")
            except Exception as e:
                logger.error(f"停止监听器失败: {e}")

    def is_running(self) -> bool:
        """检查监听器是否正在运行"""
        return self._event_monitor is not None


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    def on_voice_press():
        print("语音输入: 按下")

    def on_voice_release():
        print("语音输入: 释放")

    manager = MacOSHotkeyManager()
    manager.register_callback(HotkeyAction.VOICE_INPUT_PRESS, on_voice_press)
    manager.register_callback(HotkeyAction.VOICE_INPUT_RELEASE, on_voice_release)

    # macOS: 使用 alt 键
    if manager.start("alt", "ctrl+shift+t"):
        print("快捷键监听已启动，按 Ctrl+C 退出")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop()
