# core/hotkey_manager.py
# 全局快捷键监听模块

import logging
import threading
from enum import Enum
from typing import Callable, Dict, Optional, Set

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from config import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)


class HotkeyAction(Enum):
    """快捷键动作类型"""
    VOICE_INPUT_PRESS = "voice_input_press"      # 语音输入按键按下
    VOICE_INPUT_RELEASE = "voice_input_release"  # 语音输入按键释放
    QUICK_TRANSLATE_PRESS = "quick_translate_press"      # 翻译按键按下
    QUICK_TRANSLATE_RELEASE = "quick_translate_release"  # 翻译按键释放


class HotkeyManager:
    """
    全局快捷键管理器

    功能:
    - 跨平台全局快捷键监听
    - 支持按住触发模式 (press-hold-release)
    - 支持单击触发模式
    - 快捷键冲突检测
    """

    def __init__(self):
        self._listener: Optional[keyboard.Listener] = None
        self._callbacks: Dict[HotkeyAction, Callable] = {}
        self._hotkeys: Dict[str, Set[str]] = {}  # 改用字符串集合存储，便于比较

        # 当前按下的所有按键 (用于组合键检测) - 存储键的字符串表示
        self._pressed_keys: Set[str] = set()

        # 快捷键状态跟踪
        self._voice_input_active = False
        self._translate_active = False

        # 线程锁
        self._lock = threading.Lock()

        logger.info("快捷键管理器初始化完成")

    def register_callback(self, action: HotkeyAction, callback: Callable) -> None:
        """
        注册快捷键动作回调

        Args:
            action: 动作类型
            callback: 回调函数
        """
        with self._lock:
            self._callbacks[action] = callback
            logger.debug(f"注册回调: {action.value}")

    def parse_hotkey(self, hotkey_str: str) -> Set[str]:
        """
        解析快捷键字符串为键的字符串集合

        支持格式:
        - "fn" (macOS)
        - "ctrl+shift+t"
        - "right_ctrl"
        - "cmd+space" (macOS)

        Args:
            hotkey_str: 快捷键字符串

        Returns:
            键的字符串集合
        """
        if not hotkey_str:
            return set()

        parts = hotkey_str.lower().replace(" ", "").split("+")
        keys = set()

        for part in parts:
            key_str = self._parse_key_part(part)
            if key_str:
                keys.add(key_str)

        return keys

    def _parse_key_part(self, part: str) -> Optional[str]:
        """解析单个按键，返回字符串表示"""
        # 特殊功能键
        if part == "fn":
            # Fn 键在 pynput 中无法直接监听，使用替代方案
            # macOS: 使用 Option/Command，Windows: 使用 Right Ctrl
            if IS_MACOS:
                return "alt_l"
            return "ctrl_r"

        # 修饰键
        if part in ["ctrl", "control"]:
            return "ctrl_l"
        if part in ["alt", "option"]:
            return "alt_l"
        if part == "shift":
            return "shift_l"
        if part in ["cmd", "command", "win", "windows"]:
            return "cmd"

        # 右侧修饰键
        if part == "right_ctrl":
            return "ctrl_r"
        if part == "right_alt":
            return "alt_r"
        if part == "right_shift":
            return "shift_r"
        # macOS 上 pynput 无法区分左右 Command 键，统一使用 cmd
        if part in ["right_cmd", "right_command"]:
            return "cmd" if IS_MACOS else "cmd_r"

        # 字母和数字 - 直接返回字符
        if len(part) == 1:
            return f"char_{part}"

        # 功能键
        special_keys = {
            "space": "space",
            "tab": "tab",
            "enter": "enter",
            "return": "enter",
            "esc": "esc",
            "escape": "esc",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "home": "home",
            "end": "end",
            "delete": "delete",
            "backspace": "backspace",
            "caps_lock": "caps_lock",
            "f1": "f1",
            "f2": "f2",
            "f3": "f3",
            "f4": "f4",
            "f5": "f5",
            "f6": "f6",
            "f7": "f7",
            "f8": "f8",
            "f9": "f9",
            "f10": "f10",
            "f11": "f11",
            "f12": "f12",
        }

        return special_keys.get(part)

    def set_hotkey(self, name: str, hotkey_str: str) -> bool:
        """
        设置快捷键

        Args:
            name: 快捷键名称 ("voice_input" 或 "quick_translate")
            hotkey_str: 快捷键字符串

        Returns:
            是否设置成功
        """
        keys = self.parse_hotkey(hotkey_str)
        if not keys:
            logger.warning(f"快捷键解析失败: {hotkey_str}")
            return False

        self._hotkeys[name] = keys
        logger.info(f"快捷键已设置: {name} = {hotkey_str}")
        return True

    def _match_hotkey(self, name: str, pressed_keys: Set[keyboard.Key]) -> bool:
        """检查当前按键是否匹配快捷键"""
        if name not in self._hotkeys:
            return False
        return self._hotkeys[name] == pressed_keys

    def start(self, voice_input_hotkey: str, translate_hotkey: str) -> bool:
        """
        启动快捷键监听

        Args:
            voice_input_hotkey: 语音输入快捷键
            translate_hotkey: 翻译快捷键

        Returns:
            是否启动成功
        """
        # 设置快捷键
        if not self.set_hotkey("voice_input", voice_input_hotkey):
            return False
        if not self.set_hotkey("quick_translate", translate_hotkey):
            return False

        # 启动监听器
        if self._listener is not None:
            logger.warning("快捷键监听器已在运行")
            return True

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self._listener.start()
            logger.info("快捷键监听器已启动")
            return True
        except Exception as e:
            logger.error(f"启动快捷键监听器失败: {e}")
            return False

    def stop(self) -> None:
        """停止快捷键监听"""
        if self._listener:
            self._listener.stop()
            self._listener = None
            logger.info("快捷键监听器已停止")

    def clear_pressed_keys(self) -> None:
        """
        清空已按下的按键集合

        用于修复按键状态不同步问题，例如在 PyQt6 窗口事件后
        """
        with self._lock:
            if self._pressed_keys:
                logger.info(f"清空按键状态: {self._pressed_keys}")
                self._pressed_keys.clear()
                # 重置激活状态
                self._voice_input_active = False
                self._translate_active = False

    def _on_press(self, key) -> None:
        """按键按下事件"""
        try:
            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 添加到已按下集合
            self._pressed_keys.add(key_str)

            # Debug log for troubleshooting
            logger.info(f"按键按下: {key_str}, 已按下: {self._pressed_keys}")

            # 检查语音输入快捷键 (单键模式，按下即触发)
            voice_keys = self._hotkeys.get("voice_input", set())
            if voice_keys and voice_keys == self._pressed_keys:
                if not self._voice_input_active:
                    self._voice_input_active = True
                    self._trigger_callback(HotkeyAction.VOICE_INPUT_PRESS)

            # 检查翻译快捷键 (单键模式，按下即触发 - 与语音输入相同)
            translate_keys = self._hotkeys.get("quick_translate", set())
            if translate_keys and translate_keys == self._pressed_keys:
                if not self._translate_active:
                    self._translate_active = True
                    self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_PRESS)

        except Exception as e:
            logger.error(f"处理按键按下事件失败: {e}")

    def _on_release(self, key) -> None:
        """按键释放事件"""
        try:
            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 添加调试日志
            logger.info(f"[DEBUG] 按键释放: {key_str}, 语音激活: {self._voice_input_active}, 翻译激活: {self._translate_active}")

            # 从已按下集合移除
            self._pressed_keys.discard(key_str)

            # 检查语音输入快捷键释放
            voice_keys = self._hotkeys.get("voice_input", set())
            if voice_keys and key_str in voice_keys:
                logger.info(f"[DEBUG] 检测到语音输入快捷键释放: {key_str} in {voice_keys}, 激活状态: {self._voice_input_active}")
                if self._voice_input_active:
                    self._voice_input_active = False
                    logger.info("触发语音输入释放回调")
                    self._trigger_callback(HotkeyAction.VOICE_INPUT_RELEASE)
                else:
                    logger.warning(f"语音输入快捷键 {key_str} 释放，但 _voice_input_active 为 False")

            # 检查翻译快捷键释放
            translate_keys = self._hotkeys.get("quick_translate", set())
            if translate_keys and key_str in translate_keys:
                logger.info(f"[DEBUG] 检测到翻译快捷键释放: {key_str} in {translate_keys}, 激活状态: {self._translate_active}")
                if self._translate_active:
                    self._translate_active = False
                    logger.info("触发翻译释放回调")
                    self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_RELEASE)
                else:
                    logger.warning(f"翻译快捷键 {key_str} 释放，但 _translate_active 为 False")

        except Exception as e:
            logger.error(f"处理按键释放事件失败: {e}")

    def _key_to_string(self, key) -> str:
        """将 pynput 按键对象转换为字符串表示"""
        if isinstance(key, KeyCode):
            # 字符键 - 使用 char 属性
            if hasattr(key, 'char') and key.char:
                return f"char_{key.char}"
            # 使用 vk 属性
            if hasattr(key, 'vk') and key.vk:
                return f"vk_{key.vk}"
        elif isinstance(key, Key):
            # 特殊键
            key_str = str(key).replace('Key.', '')
            # pynput 在 macOS 上使用的键名可能不同
            # 需要转换为我们内部使用的格式
            # macOS 上 pynput 可能报告: alt, cmd 等 (不带左右后缀)
            # 我们需要将其映射为与 _parse_key_part 一致的格式
            key_map = {
                'alt': 'alt_l',      # macOS Option/Alt 键
                'alt_r': 'alt_l',
                'alt_l': 'alt_l',
                'cmd': 'cmd',        # macOS Command 键 (通用)
                'cmd_r': 'cmd',      # 右侧 Command 键映射到 cmd
                'cmd_l': 'cmd',      # 左侧 Command 键映射到 cmd
                'ctrl': 'ctrl_l',    # Ctrl 键
                'ctrl_r': 'ctrl_r',  # 右侧 Ctrl
                'ctrl_l': 'ctrl_l',  # 左侧 Ctrl
                'shift': 'shift_l',  # Shift 键
                'shift_r': 'shift_r',
                'shift_l': 'shift_l',
            }
            return key_map.get(key_str, key_str)
        return str(key)

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

    def check_hotkey_conflict(self, hotkey_str: str) -> Optional[str]:
        """
        检查快捷键是否与系统或其他应用冲突

        Args:
            hotkey_str: 快捷键字符串

        Returns:
            冲突描述，无冲突返回 None
        """
        # 常见系统快捷键列表
        system_hotkeys = {
            "darwin": [  # macOS
                "cmd+space", "cmd+tab", "cmd+q", "cmd+w", "cmd+c", "cmd+v",
                "cmd+option+esc", "cmd+shift+3", "cmd+shift+4", "cmd+shift+5",
                "ctrl+up", "ctrl+down", "ctrl+left", "ctrl+right",
            ],
            "windows": [  # Windows
                "ctrl+escape", "ctrl+shift+esc", "ctrl+alt+delete",
                "win+e", "win+d", "win+l", "win+r", "win+tab",
                "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a",
                "alt+tab", "alt+f4", "print_screen",
            ],
        }

        platform = "darwin" if IS_MACOS else "windows"
        hotkey_normalized = hotkey_str.lower().replace(" ", "")

        if hotkey_normalized in system_hotkeys.get(platform, []):
            return f"与系统快捷键冲突: {hotkey_str}"

        return None

    def is_running(self) -> bool:
        """检查监听器是否正在运行"""
        return self._listener is not None and self._listener.is_alive


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    def on_voice_press():
        print("语音输入: 按下")

    def on_voice_release():
        print("语音输入: 释放")

    def on_translate():
        print("快速翻译")

    manager = HotkeyManager()
    manager.register_callback(HotkeyAction.VOICE_INPUT_PRESS, on_voice_press)
    manager.register_callback(HotkeyAction.VOICE_INPUT_RELEASE, on_voice_release)
    manager.register_callback(HotkeyAction.QUICK_TRANSLATE, on_translate)

    # macOS: fn 键 (实际用 alt 代替), Windows: right_ctrl
    voice_hotkey = "alt" if IS_MACOS else "right_ctrl"
    translate_hotkey = "ctrl+shift+t"

    if manager.start(voice_hotkey, translate_hotkey):
        print("快捷键监听已启动，按 Ctrl+C 退出")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop()
