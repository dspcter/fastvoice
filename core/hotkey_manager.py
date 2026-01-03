# core/hotkey_manager.py
# 全局快捷键监听模块 (P0 重构版: 状态机 + 防抖 + watchdog)

import logging
import threading
import time
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


class HotkeyState(Enum):
    """快捷键状态机 - P0 重构"""
    IDLE = "idle"                    # 空闲，无快捷键激活
    VOICE_RECORDING = "voice_recording"  # 语音输入录音中
    TRANSLATE_RECORDING = "translate_recording"  # 翻译录音中


class HotkeyManager:
    """
    全局快捷键管理器 (P0 重构版)

    功能:
    - 跨平台全局快捷键监听
    - 状态机管理 (IDLE → RECORDING → IDLE)
    - 防抖机制 (50ms)
    - 幂等性保证 (重复keydown忽略)
    - Watchdog 超时保护 (10秒强制回IDLE)
    - Listener 功能测试（检测静默失效）

    P0 改进:
    - 显式状态机替代布尔标志
    - 防抖防止误触发
    - Watchdog 防止卡死
    - 所有状态转换可恢复
    - 按键事件时间跟踪（检测静默失效）
    """

    # 防抖时间 (毫秒)
    DEBOUNCE_MS = 50

    # Watchdog 超时 (秒) - 防止卡死
    WATCHDOG_TIMEOUT_S = 10

    # Listener 健康检查间隔 (秒)
    LISTENER_HEALTH_CHECK_INTERVAL = 30

    def __init__(self):
        self._listener: Optional[keyboard.Listener] = None
        self._callbacks: Dict[HotkeyAction, Callable] = {}
        self._hotkeys: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()

        # 当前按下的所有按键
        self._pressed_keys: Set[str] = set()

        # P0 重构: 状态机替代布尔标志
        self._state = HotkeyState.IDLE
        # 使用 RLock 而不是 Lock，允许在同一线程中多次获取
        self._state_lock = threading.RLock()

        # P0: 防抖 - 记录最后一次 keydown 时间
        self._last_keydown_time: Dict[str, float] = {}

        # P0: Watchdog - 超时强制回 IDLE
        self._last_activity_time: Optional[float] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = False
        self._watchdog_loop_count: int = 0  # Watchdog 循环计数器
        self._watchdog_last_heartbeat: float = 0.0  # Watchdog 上次心跳时间

        # 按键事件时间跟踪 - 检测 listener 静默失效
        self._last_key_event_time: float = time.time()  # 上次收到任何按键事件的时间

        logger.info("快捷键管理器初始化完成 (P0 重构版: 状态机 + 防抖 + watchdog + 按键事件跟踪)")

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
            # P0: 启动 watchdog
            self._start_watchdog()

            # macOS 特殊处理：确保 CGEventTap 能正常工作
            # 在 macOS 上，pynput 使用 CGEventTap 创建全局键盘钩子
            # 这可能与 Qt 的事件循环冲突，所以我们需要在 Qt 应用创建后再启动
            from pynput.keyboard import Listener as KeyboardListener

            self._listener = KeyboardListener(
                on_press=self._on_press,
                on_release=self._on_release,
                # macOS: 不抑制任何按键，只监听
                suppress=False
            )

            logger.info("正在启动 pynput listener...")
            self._listener.start()

            # 验证 listener 是否真正启动并等待其稳定
            import time
            time.sleep(1.0)  # 给 listener 更多时间启动

            try:
                is_alive = self._listener.is_alive()
            except:
                is_alive = False

            if not is_alive:
                logger.error("❌ Listener 启动失败！线程未运行！")
                logger.error("这可能是 macOS 权限问题，请检查：")
                logger.error("1. 系统设置 > 隐私与安全性 > 辅助功能")
                logger.error("2. 确保当前应用已被勾选")
                logger.error("3. 如果已勾选，先取消再重新勾选")
                return False

            logger.info(f"✓ 快捷键监听器已启动 (带 watchdog)")

            # 输出 listener 状态用于调试
            try:
                logger.info(f"✓ Listener 线程状态: alive={is_alive}")
            except:
                pass

            return True
        except Exception as e:
            logger.error(f"启动快捷键监听器失败: {e}")
            return False

    def stop(self) -> None:
        """停止快捷键监听"""
        # P0: 停止 watchdog
        self._stop_watchdog()

        if self._listener:
            self._listener.stop()
            self._listener = None
            logger.info("快捷键监听器已停止")

    def clear_pressed_keys(self) -> None:
        """
        清空已按下的按键集合

        用于修复按键状态不同步问题，例如在 PyQt6 窗口事件后
        """
        with self._state_lock:
            if self._pressed_keys:
                logger.info(f"清空按键状态: {self._pressed_keys}")
                self._pressed_keys.clear()
                # P0: 重置状态到 IDLE
                self._reset_state()

    def _start_watchdog(self) -> None:
        """启动 watchdog 线程 - P0 重构"""
        self._watchdog_running = True
        self._last_activity_time = time.time()
        self._watchdog_loop_count = 0  # 添加循环计数器
        self._watchdog_last_heartbeat = time.time()  # 上次心跳时间

        def watchdog_loop():
            last_listener_check = time.time()

            while self._watchdog_running:
                try:
                    time.sleep(1)  # 每秒检查一次
                    self._watchdog_loop_count += 1
                    self._watchdog_last_heartbeat = time.time()  # 更新心跳时间

                    current_time = time.time()

                    # 每 60 秒输出一次心跳日志
                    if self._watchdog_loop_count % 60 == 0:
                        listener_status = "未知"
                        if self._listener:
                            try:
                                listener_status = "运行中" if self._listener.is_alive() else "已死亡"
                            except:
                                listener_status = "检查失败"
                        logger.info(f"🐕 Watchdog 心跳: 运行 {self._watchdog_loop_count}s, Listener: {listener_status}")

                    # 定期检查 listener 健康状态
                    if current_time - last_listener_check > self.LISTENER_HEALTH_CHECK_INTERVAL:
                        last_listener_check = current_time

                        if self._listener:
                            try:
                                is_alive = self._listener.is_alive()

                                # 检查是否静默失效（线程活着但没有接收按键事件）
                                time_since_last_key_event = current_time - self._last_key_event_time
                                # 静默失效阈值：3 分钟无任何按键事件就认为可能失效
                                is_silent_dead = time_since_last_key_event > 180

                                if not is_alive:
                                    logger.error("❌ pynput listener 线程已死亡！尝试重启...")
                                    import threading
                                    restart_thread = threading.Thread(
                                        target=self._restart_listener,
                                        daemon=True,
                                        name="ListenerRestart"
                                    )
                                    restart_thread.start()
                                elif is_silent_dead:
                                    logger.warning(f"⚠️ Listener 可能已静默失效（{time_since_last_key_event:.0f}秒无按键事件）")
                                    logger.warning("   线程活着但可能不接收键盘事件，尝试重启...")
                                    import threading
                                    restart_thread = threading.Thread(
                                        target=self._restart_listener,
                                        daemon=True,
                                        name="ListenerRestart"
                                    )
                                    restart_thread.start()

                            except Exception as e:
                                logger.error(f"❌ 检查 listener 状态失败: {e}")

                    # 检查状态锁
                    with self._state_lock:
                        if self._state == HotkeyState.IDLE:
                            self._last_activity_time = current_time
                            continue

                        # 检查是否超时
                        elapsed = current_time - self._last_activity_time
                        if elapsed > self.WATCHDOG_TIMEOUT_S:
                            logger.warning(
                                f"Watchdog 触发: {elapsed:.1f}s 无活动，"
                                f"强制重置状态 (当前: {self._state.value})"
                            )
                            self._reset_state()
                except Exception as e:
                    logger.error(f"❌ Watchdog 循环异常: {e}，继续运行")

        self._watchdog_thread = threading.Thread(
            target=watchdog_loop,
            daemon=True,
            name="HotkeyWatchdog"
        )
        self._watchdog_thread.start()
        logger.info(f"Watchdog 已启动 (超时: {self.WATCHDOG_TIMEOUT_S}s, Listener检查: {self.LISTENER_HEALTH_CHECK_INTERVAL}s, 心跳日志: 每60s)")

    def is_watchdog_alive(self) -> bool:
        """
        检查 watchdog 是否还在运行

        Returns:
            True 如果 watchdog 最近有心跳（2秒内有更新）
        """
        if not hasattr(self, '_watchdog_last_heartbeat'):
            return False
        return (time.time() - self._watchdog_last_heartbeat) < 2.0

    def get_listener_status(self) -> dict:
        """
        获取 listener 详细状态

        Returns:
            包含 listener 状态信息的字典
        """
        status = {
            "listener_exists": self._listener is not None,
            "thread_alive": False,
            "seconds_since_last_key_event": 0.0,
            "total_keys_detected": len(self._last_keydown_time),
        }

        if self._listener:
            try:
                status["thread_alive"] = self._listener.is_alive()
            except:
                status["thread_alive"] = False

        status["seconds_since_last_key_event"] = time.time() - self._last_key_event_time

        # 判断是否静默失效
        if status["thread_alive"]:
            if status["seconds_since_last_key_event"] > 300:  # 5 分钟
                status["health"] = "可能已静默失效"
            elif status["seconds_since_last_key_event"] > 60:  # 1 分钟
                status["health"] = "可能闲置中"
            else:
                status["health"] = "正常"
        else:
            status["health"] = "已死亡"

        return status

    def _stop_watchdog(self) -> None:
        """停止 watchdog 线程"""
        self._watchdog_running = False
        if self._watchdog_thread:
            self._watchdog_thread = None
            logger.info("Watchdog 已停止")

    def _restart_listener(self) -> bool:
        """
        重启 pynput listener（带重试机制）

        当检测到 listener 线程死亡时调用此方法尝试恢复

        Returns:
            是否重启成功
        """
        max_retries = 3
        retry_delay = 1.0  # 秒

        for attempt in range(1, max_retries + 1):
            try:
                logger.warning(f"开始重启 pynput listener... (尝试 {attempt}/{max_retries})")

                # 保存当前快捷键配置
                voice_hotkey = self._hotkeys.get("voice_input", set())
                translate_hotkey = self._hotkeys.get("quick_translate", set())

                # 停止旧 listener
                if self._listener:
                    try:
                        self._listener.stop()
                        logger.debug("旧 listener 已停止")
                    except Exception as e:
                        logger.debug(f"停止旧 listener 时出错: {e}")
                    self._listener = None

                # 等待一下确保资源释放
                time.sleep(retry_delay)

                # 创建新 listener
                from pynput.keyboard import Listener as KeyboardListener

                self._listener = KeyboardListener(
                    on_press=self._on_press,
                    on_release=self._on_release,
                    suppress=False
                )

                self._listener.start()
                time.sleep(0.5)  # 等待启动

                try:
                    is_alive = self._listener.is_alive()
                except:
                    is_alive = False

                if not is_alive:
                    if attempt < max_retries:
                        logger.warning(f"Listener 重启失败（第 {attempt} 次），{retry_delay} 秒后重试...")
                        continue
                    else:
                        logger.error("❌ Listener 重启失败（已达最大重试次数）")
                        return False

                logger.info(f"✓ Listener 重启成功 (尝试 {attempt}/{max_retries})")
                return True

            except Exception as e:
                logger.error(f"❌ Listener 重启失败 (尝试 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    logger.info(f"{retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    return False

        return False

    def _reset_state(self) -> None:
        """
        重置状态到 IDLE (幂等操作) - P0 重构

        用于异常恢复、watchdog 触发等场景
        """
        old_state = self._state
        self._state = HotkeyState.IDLE
        self._last_activity_time = time.time()
        self._last_keydown_time.clear()

        if old_state != HotkeyState.IDLE:
            logger.warning(f"状态已重置: {old_state.value} → IDLE")

    def _transition_state(self, new_state: HotkeyState) -> bool:
        """
        状态转换 (带验证) - P0 重构

        Args:
            new_state: 目标状态

        Returns:
            是否转换成功
        """
        with self._state_lock:
            # 验证状态转换合法性
            valid_transitions = {
                HotkeyState.IDLE: [HotkeyState.VOICE_RECORDING, HotkeyState.TRANSLATE_RECORDING],
                HotkeyState.VOICE_RECORDING: [HotkeyState.IDLE],
                HotkeyState.TRANSLATE_RECORDING: [HotkeyState.IDLE],
            }

            if new_state not in valid_transitions.get(self._state, []):
                logger.warning(
                    f"非法状态转换: {self._state.value} → {new_state.value}，已忽略"
                )
                return False

            old_state = self._state
            self._state = new_state
            self._last_activity_time = time.time()

            logger.debug(f"状态转换: {old_state.value} → {new_state.value}")
            return True

    def get_state(self) -> HotkeyState:
        """获取当前状态 - P0 重构"""
        return self._state

    def _on_press(self, key) -> None:
        """
        按键按下事件 (P0 重构版)

        改进:
        - 防抖 (50ms)
        - 幂等性 (重复keydown忽略)
        - 状态机管理
        - 按键事件时间跟踪
        """
        try:
            # 更新按键事件时间（用于检测 listener 静默失效）
            self._last_key_event_time = time.time()

            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 添加到已按下集合
            self._pressed_keys.add(key_str)

            # P0: 防抖检查
            current_time = time.time()
            last_time = self._last_keydown_time.get(key_str, 0)
            if current_time - last_time < (self.DEBOUNCE_MS / 1000):
                logger.debug(f"防抖: 忽略重复按下 ({key_str})")
                return

            # P0: 幂等性 + 状态机检查
            with self._state_lock:
                # 如果已经在录音中，忽略重复的 keydown
                if self._state != HotkeyState.IDLE:
                    logger.debug(f"状态非 IDLE ({self._state.value})，忽略 keydown")
                    return

                # 检查语音输入快捷键
                voice_keys = self._hotkeys.get("voice_input", set())
                if voice_keys and voice_keys == self._pressed_keys:
                    # 幂等性: 再次检查状态（双重检查锁定）
                    if self._state == HotkeyState.IDLE:
                        # 状态转换: IDLE → VOICE_RECORDING
                        if self._transition_state(HotkeyState.VOICE_RECORDING):
                            self._last_keydown_time[key_str] = current_time
                            logger.info(f"语音输入: 开始录音 (状态: {self._state.value})")
                            self._trigger_callback(HotkeyAction.VOICE_INPUT_PRESS)

                # 检查翻译快捷键
                translate_keys = self._hotkeys.get("quick_translate", set())
                logger.debug(f"翻译快捷键检查: 已按下={self._pressed_keys}, 目标={translate_keys}")
                if translate_keys and translate_keys == self._pressed_keys:
                    # 幂等性: 再次检查状态
                    if self._state == HotkeyState.IDLE:
                        # 状态转换: IDLE → TRANSLATE_RECORDING
                        if self._transition_state(HotkeyState.TRANSLATE_RECORDING):
                            self._last_keydown_time[key_str] = current_time
                            logger.info(f"快速翻译: 开始录音 (状态: {self._state.value})")
                            self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_PRESS)

        except Exception as e:
            logger.error(f"处理按键按下事件失败: {e}")

    def _on_release(self, key) -> None:
        """
        按键释放事件 (P0 重构版)

        改进:
        - 状态机管理
        - 只在对应状态下触发回调
        - 状态自动回 IDLE
        - 按键事件时间跟踪
        """
        try:
            # 更新按键事件时间（用于检测 listener 静默失效）
            self._last_key_event_time = time.time()

            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 从已按下集合移除
            self._pressed_keys.discard(key_str)

            # P0: 使用状态机判断
            with self._state_lock:
                # 检查语音输入快捷键释放
                voice_keys = self._hotkeys.get("voice_input", set())
                if voice_keys and key_str in voice_keys:
                    if self._state == HotkeyState.VOICE_RECORDING:
                        # 状态转换: VOICE_RECORDING → IDLE
                        if self._transition_state(HotkeyState.IDLE):
                            logger.info(f"语音输入: 停止录音 (状态: {self._state.value})")
                            self._trigger_callback(HotkeyAction.VOICE_INPUT_RELEASE)
                    else:
                        logger.debug(
                            f"语音输入 keyup 但状态不匹配 "
                            f"(key={key_str}, state={self._state.value})"
                        )

                # 检查翻译快捷键释放
                translate_keys = self._hotkeys.get("quick_translate", set())
                if translate_keys and key_str in translate_keys:
                    if self._state == HotkeyState.TRANSLATE_RECORDING:
                        # 状态转换: TRANSLATE_RECORDING → IDLE
                        if self._transition_state(HotkeyState.IDLE):
                            logger.info(f"快速翻译: 停止录音 (状态: {self._state.value})")
                            self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_RELEASE)
                    else:
                        logger.debug(
                            f"翻译 keyup 但状态不匹配 "
                            f"(key={key_str}, state={self._state.value})"
                        )

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
        if self._listener is None:
            return False
        try:
            return self._listener.is_alive()  # 是方法调用，不是属性
        except:
            return False


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
