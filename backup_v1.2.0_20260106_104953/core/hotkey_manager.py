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
    """快捷键状态机 - 支持两种触发模式"""
    # 通用状态
    IDLE = "idle"                                          # 空闲

    # 一次按键模式（语音输入 - Option键）
    VOICE_RECORDING = "voice_recording"                    # 语音输入录音中（一次按键）
    VOICE_TAIL_COLLECTING = "voice_tail_collecting"        # 语音输入尾音收集中

    # 双击+长按+延迟尾音模式（翻译 - Command键）
    WAIT_FIRST_RELEASE = "wait_first_release"              # 等待第一次快速释放
    WAIT_SECOND_KEY = "wait_second_key"                    # 等待第二次按键
    WAIT_LONG_PRESS = "wait_long_press"                    # 等待长按确认
    TRANSLATE_RECORDING = "translate_recording"            # 翻译录音中
    TRANSLATE_TAIL_COLLECTING = "translate_tail_collecting" # 翻译尾音收集中


class HotkeyManager:
    """
    全局快捷键管理器 (支持两种触发模式)

    功能:
    - 跨平台全局快捷键监听
    - 两种触发模式：
      * 一次按键模式：按下开始录音，松开停止（用于语音输入）
      * 双击+长按+延迟尾音：防误触的精确触发（用于翻译）
    - 状态机管理 (IDLE → RECORDING → IDLE)
    - 防抖机制 (50ms)
    - 幂等性保证 (重复keydown忽略)
    - Watchdog 超时保护 (10秒强制回IDLE)
    - Listener 功能测试（检测静默失效）

    触发模式:
    - 语音输入（Option键）: 一次按键，按下开始录音，松开停止
    - 快速翻译（Command键）: 双击+长按+延迟尾音，防止误触
    """

    # 防抖时间 (毫秒)
    DEBOUNCE_MS = 50

    # ========== 双击+长按+延迟尾音参数 ==========
    # 第一次按键：快速释放阈值（毫秒）
    FIRST_RELEASE_TIMEOUT = 150  # 第一次按键必须在 150ms 内释放

    # 两次按键间隔阈值（毫秒）
    DOUBLE_CLICK_INTERVAL = 500  # 两次按键间隔不能超过 500ms

    # 长按确认阈值（毫秒）
    LONG_PRESS_THRESHOLD = 350   # 第二次按键必须按住 > 350ms

    # 尾音收集延迟（毫秒）
    TAIL_SOUND_DELAY = 200        # 松开后延迟 200ms 收集尾音

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

        # ========== 双击+长按+延迟尾音状态跟踪（仅用于翻译模式） ==========
        self._first_keydown_time: Optional[float] = None   # 第一次按键按下时间
        self._first_keyup_time: Optional[float] = None     # 第一次按键释放时间
        self._second_keydown_time: Optional[float] = None  # 第二次按键按下时间
        self._tail_timer: Optional[threading.Timer] = None  # 尾音延迟定时器

        logger.info("快捷键管理器初始化完成 (支持两种触发模式：一次按键 + 双击+长按)")

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

        # ========== 左侧修饰键 ==========
        if part in ["left_ctrl", "ctrl", "control"]:
            return "ctrl_l"
        if part in ["left_alt", "alt", "option"]:
            return "alt_l"
        if part in ["left_shift", "shift"]:
            return "shift_l"
        if part in ["left_cmd", "left_command", "cmd", "command", "win", "windows"]:
            # pynput 在 macOS 上只能识别通用的 cmd 键，无法区分左右
            # 所以即使指定 left_cmd，也映射到 "cmd"
            return "cmd"

        # ========== 右侧修饰键 ==========
        if part in ["right_ctrl"]:
            return "ctrl_r"
        if part in ["right_alt", "right_option"]:
            return "alt_r"
        if part in ["right_shift"]:
            return "shift_r"
        if part in ["right_cmd", "right_command"]:
            # pynput 在 macOS 上只能识别通用的 cmd 键，无法区分左右
            # 所以即使指定 right_cmd，也映射到 "cmd"
            return "cmd"

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

    def _match_hotkey(self, name: str, pressed_keys: Set[str]) -> bool:
        """
        检查当前按键是否匹配快捷键

        完全根据配置判断，不做任何特殊处理
        """
        if name not in self._hotkeys:
            return False

        configured_keys = self._hotkeys[name]
        return configured_keys == pressed_keys

    def start(self, voice_input_hotkey: str, translate_hotkey: str) -> bool:
        """
        启动快捷键监听

        Args:
            voice_input_hotkey: 语音输入快捷键
            translate_hotkey: 翻译快捷键（可为空字符串）

        Returns:
            是否启动成功
        """
        # 设置快捷键
        if not self.set_hotkey("voice_input", voice_input_hotkey):
            return False
        # 翻译快捷键可以为空（不使用翻译功能）
        if translate_hotkey and not self.set_hotkey("quick_translate", translate_hotkey):
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

                    # 每 60 秒输出一次心跳日志 - 使用 lazy logging
                    if self._watchdog_loop_count % 60 == 0:
                        listener_alive = False
                        if self._listener:
                            try:
                                listener_alive = self._listener.is_alive()
                            except:
                                listener_alive = False
                        # 使用 lazy logging 避免字符串累积
                        logger.info("Watchdog %ds | Listener:%s",
                                   self._watchdog_loop_count,
                                   '✓' if listener_alive else '✗')

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
        logger.info("Watchdog 已启动 (超时: %ds, Listener检查: %ds, 心跳日志: 每60s)",
                   self.WATCHDOG_TIMEOUT_S, self.LISTENER_HEALTH_CHECK_INTERVAL)

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
        重置状态到 IDLE (幂等操作)

        用于异常恢复、watchdog 触发等场景
        """
        old_state = self._state
        self._state = HotkeyState.IDLE
        self._last_activity_time = time.time()
        self._last_keydown_time.clear()

        # 清理双击+长按状态变量（仅翻译模式使用）
        self._first_keydown_time = None
        self._first_keyup_time = None
        self._second_keydown_time = None

        # 取消尾音收集定时器
        if self._tail_timer:
            self._tail_timer.cancel()
            self._tail_timer = None

        if old_state != HotkeyState.IDLE:
            logger.warning(f"状态已重置: {old_state.value} → IDLE")

    def _transition_state(self, new_state: HotkeyState) -> bool:
        """
        状态转换 (带验证) - 支持两种触发模式

        Args:
            new_state: 目标状态

        Returns:
            是否转换成功
        """
        with self._state_lock:
            # 验证状态转换合法性（支持两种模式）
            valid_transitions = {
                # IDLE 状态可以转换到：
                HotkeyState.IDLE: [
                    HotkeyState.VOICE_RECORDING,          # 一次按键模式：按下 Option 开始录音
                    HotkeyState.WAIT_FIRST_RELEASE,       # 双击模式：第一次按键按下
                ],
                # 双击模式的状态转换
                HotkeyState.WAIT_FIRST_RELEASE: [
                    HotkeyState.WAIT_SECOND_KEY,          # 第一次快速释放
                    HotkeyState.IDLE,                     # 释放太慢，回到 IDLE
                ],
                HotkeyState.WAIT_SECOND_KEY: [
                    HotkeyState.WAIT_LONG_PRESS,          # 第二次按键按下
                    HotkeyState.IDLE,                     # 超时，回到 IDLE
                ],
                HotkeyState.WAIT_LONG_PRESS: [
                    HotkeyState.TRANSLATE_RECORDING,      # 长按确认，开始录音
                    HotkeyState.IDLE,                     # 释放太早，回到 IDLE
                ],
                # 翻译录音状态
                HotkeyState.TRANSLATE_RECORDING: [
                    HotkeyState.TRANSLATE_TAIL_COLLECTING, # 按键释放，收集尾音
                    HotkeyState.IDLE,                     # 直接停止（兼容模式）
                ],
                HotkeyState.TRANSLATE_TAIL_COLLECTING: [
                    HotkeyState.IDLE,                     # 尾音收集完成
                ],
                # 语音输入录音状态（一次按键模式 + 尾音收集）
                HotkeyState.VOICE_RECORDING: [
                    HotkeyState.VOICE_TAIL_COLLECTING,    # 按键释放，收集尾音
                    HotkeyState.IDLE,                     # 直接停止（兼容模式）
                ],
                # 尾音收集状态
                HotkeyState.VOICE_TAIL_COLLECTING: [
                    HotkeyState.IDLE,                     # 尾音收集完成
                ],
            }

            if new_state not in valid_transitions.get(self._state, []):
                logger.warning(
                    f"非法状态转换: {self._state.value} → {new_state.value}，已忽略"
                )
                return False

            old_state = self._state
            self._state = new_state
            self._last_activity_time = time.time()

            logger.info(f"状态转换: {old_state.value} → {new_state.value}")
            return True

    def get_state(self) -> HotkeyState:
        """获取当前状态 - P0 重构"""
        return self._state

    def _on_press(self, key) -> None:
        """
        按键按下事件 - 支持两种触发模式

        一次按键模式（Option - 语音输入）:
        1. IDLE → 按下 Option → VOICE_RECORDING（开始录音）
        2. VOICE_RECORDING → 释放 Option → VOICE_TAIL_COLLECTING（收集尾音）
        3. VOICE_TAIL_COLLECTING → 延迟 200ms → IDLE（停止录音并提交 ASR）

        双击+长按模式（Command - 翻译）:
        1. IDLE → 第一次轻按 Command（<150ms 释放）→ WAIT_SECOND_KEY
        2. WAIT_SECOND_KEY → 第二次按下 Command（按住 >350ms）→ TRANSLATE_RECORDING
        3. TRANSLATE_RECORDING → 释放 Command → TRANSLATE_TAIL_COLLECTING（收集尾音）
        4. TRANSLATE_TAIL_COLLECTING → 延迟 200ms → IDLE（停止录音并翻译）
        """
        try:
            # 更新按键事件时间（用于检测 listener 静默失效）
            self._last_key_event_time = time.time()

            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 添加到已按下集合
            self._pressed_keys.add(key_str)

            # 防抖检查（防止重复触发）
            current_time = time.time()
            last_time = self._last_keydown_time.get(key_str, 0)
            if current_time - last_time < (self.DEBOUNCE_MS / 1000):
                logger.debug(f"防抖: 忽略重复按下 ({key_str})")
                return

            self._last_keydown_time[key_str] = current_time

            # ========== 状态机处理 ==========
            with self._state_lock:
                # 根据配置动态判断是否匹配快捷键
                is_voice_hotkey = self._match_hotkey("voice_input", self._pressed_keys)
                is_translate_hotkey = self._match_hotkey("quick_translate", self._pressed_keys)

                # ========== 一次按键模式（语音输入 - 左右 Option键） ==========
                if is_voice_hotkey and self._state == HotkeyState.IDLE:
                    logger.info(f"[一次按键模式] 语音输入开始 ({key_str})")
                    # 状态转换: IDLE → VOICE_RECORDING
                    self._transition_state(HotkeyState.VOICE_RECORDING)
                    self._trigger_callback(HotkeyAction.VOICE_INPUT_PRESS)
                    return

                # ========== 双击模式（翻译 - 如有配置） ==========
                if is_translate_hotkey and self._state == HotkeyState.IDLE:
                    # ========== 第一次按键按下 ==========
                    logger.info(f"[双击模式] 第一次按键按下 ({key_str})")
                    self._first_keydown_time = current_time
                    self._first_keyup_time = None
                    self._second_keydown_time = None

                    # 状态转换: IDLE → WAIT_FIRST_RELEASE
                    self._transition_state(HotkeyState.WAIT_FIRST_RELEASE)

                    # 启动超时定时器（如果 150ms 内没释放，取消）
                    def first_press_timeout():
                        with self._state_lock:
                            if self._state == HotkeyState.WAIT_FIRST_RELEASE:
                                logger.info("第一次按键超时（未快速释放），回到 IDLE")
                                self._reset_state()

                    timer = threading.Timer(
                        self.FIRST_RELEASE_TIMEOUT / 1000.0,
                        first_press_timeout
                    )
                    timer.daemon = True
                    timer.start()
                    return

                if is_translate_hotkey and self._state == HotkeyState.WAIT_SECOND_KEY:
                    # ========== 第二次按键按下 ==========
                    logger.info(f"[双击模式] 第二次按键按下 ({key_str})")

                    # 检查两次按键间隔
                    if self._first_keyup_time is None:
                        logger.warning("第一次按键未释放，忽略第二次按键")
                        return

                    interval = (current_time - self._first_keyup_time) * 1000  # 转换为毫秒
                    if interval > self.DOUBLE_CLICK_INTERVAL:
                        logger.info(f"两次按键间隔太长 ({interval:.0f}ms > {self.DOUBLE_CLICK_INTERVAL}ms)，回到 IDLE")
                        self._reset_state()
                        return

                    self._second_keydown_time = current_time

                    # 状态转换: WAIT_SECOND_KEY → WAIT_LONG_PRESS
                    self._transition_state(HotkeyState.WAIT_LONG_PRESS)

                    # 启动长按检测定时器
                    def check_long_press():
                        with self._state_lock:
                            if self._state == HotkeyState.WAIT_LONG_PRESS:
                                # 长按确认，开始录音
                                logger.info(f"[双击模式] 长按确认 ({self.LONG_PRESS_THRESHOLD}ms)，开始翻译录音")
                                self._transition_state(HotkeyState.TRANSLATE_RECORDING)
                                self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_PRESS)

                    timer = threading.Timer(
                        self.LONG_PRESS_THRESHOLD / 1000.0,
                        check_long_press
                    )
                    timer.daemon = True
                    timer.start()
                    return

                if self._state == HotkeyState.WAIT_LONG_PRESS:
                    # ========== 在等待长按期间又按了键 ==========
                    logger.info("长按等待期间重复按键，忽略")
                    # 保持当前状态，等待长按定时器触发

        except Exception as e:
            logger.error(f"处理按键按下事件失败: {e}")

    def _on_release(self, key) -> None:
        """
        按键释放事件 - 支持两种触发模式

        一次按键模式（Option - 语音输入）:
        - VOICE_RECORDING → 释放 Option → VOICE_TAIL_COLLECTING（收集 200ms 尾音）
        - VOICE_TAIL_COLLECTING → IDLE（停止录音）

        双击模式（Command - 翻译）:
        - WAIT_FIRST_RELEASE → 检测是否快速释放 (<150ms)
        - WAIT_LONG_PRESS → 释放太早，取消
        - TRANSLATE_RECORDING → 释放 Command → TRANSLATE_TAIL_COLLECTING（收集 200ms 尾音）
        - TRANSLATE_TAIL_COLLECTING → IDLE（停止录音）
        """
        try:
            # 更新按键事件时间（用于检测 listener 静默失效）
            self._last_key_event_time = time.time()

            # 将按键转换为字符串表示
            key_str = self._key_to_string(key)

            # 从已按下集合移除
            self._pressed_keys.discard(key_str)

            current_time = time.time()

            # ========== 状态机处理 ==========
            with self._state_lock:
                # 根据配置动态判断是否匹配快捷键
                voice_keys = self._hotkeys.get("voice_input", set())
                translate_keys = self._hotkeys.get("quick_translate", set())

                is_voice_key = voice_keys and key_str in voice_keys
                is_translate_key = translate_keys and key_str in translate_keys

                # ========== 双击模式：第一次按键释放 ==========
                if is_translate_key and self._state == HotkeyState.WAIT_FIRST_RELEASE:
                    release_time = (current_time - self._first_keydown_time) * 1000  # 毫秒

                    if release_time <= self.FIRST_RELEASE_TIMEOUT:
                        # 快速释放，进入等待第二次按键状态
                        logger.info(f"[双击模式] 第一次快速释放 ({release_time:.0f}ms < {self.FIRST_RELEASE_TIMEOUT}ms)")
                        self._first_keyup_time = current_time

                        # 状态转换: WAIT_FIRST_RELEASE → WAIT_SECOND_KEY
                        self._transition_state(HotkeyState.WAIT_SECOND_KEY)

                        # 启动超时定时器（如果 500ms 内没第二次按键，取消）
                        def double_click_timeout():
                            with self._state_lock:
                                if self._state == HotkeyState.WAIT_SECOND_KEY:
                                    logger.info("双击超时（无第二次按键），回到 IDLE")
                                    self._reset_state()

                        timer = threading.Timer(
                            self.DOUBLE_CLICK_INTERVAL / 1000.0,
                            double_click_timeout
                        )
                        timer.daemon = True
                        timer.start()
                    else:
                        # 释放太慢，取消
                        logger.info(f"[双击模式] 第一次释放太慢 ({release_time:.0f}ms)，回到 IDLE")
                        self._reset_state()
                    return

                # ========== 双击模式：长按等待期间释放 ==========
                if is_translate_key and self._state == HotkeyState.WAIT_LONG_PRESS:
                    # 用户在长按确认前就释放了，取消
                    logger.info("[双击模式] 长按等待期间释放，回到 IDLE")
                    self._reset_state()
                    return

                # ========== 一次按键模式：语音输入录音结束 + 尾音收集 ==========
                if is_voice_key and self._state == HotkeyState.VOICE_RECORDING:
                    logger.info("[一次按键模式] 语音输入结束，开始收集尾音...")

                    # 状态转换: VOICE_RECORDING → VOICE_TAIL_COLLECTING
                    self._transition_state(HotkeyState.VOICE_TAIL_COLLECTING)

                    # 启动尾音收集定时器（延迟 200ms 后真正停止）
                    def finish_voice_tail_collecting():
                        with self._state_lock:
                            if self._state == HotkeyState.VOICE_TAIL_COLLECTING:
                                logger.info(f"[一次按键模式] 尾音收集完成 ({self.TAIL_SOUND_DELAY}ms)")
                                # 状态转换: VOICE_TAIL_COLLECTING → IDLE
                                self._transition_state(HotkeyState.IDLE)
                                # 触发停止录音回调
                                self._trigger_callback(HotkeyAction.VOICE_INPUT_RELEASE)

                    # 取消之前的尾音定时器（如果有）
                    if self._tail_timer:
                        self._tail_timer.cancel()

                    # 启动新的尾音定时器
                    self._tail_timer = threading.Timer(
                        self.TAIL_SOUND_DELAY / 1000.0,
                        finish_voice_tail_collecting
                    )
                    self._tail_timer.daemon = True
                    self._tail_timer.start()
                    return

                # ========== 双击模式：翻译录音结束 + 尾音收集 ==========
                if is_translate_key and self._state == HotkeyState.TRANSLATE_RECORDING:
                    logger.info("[双击模式] 翻译录音结束，开始收集尾音...")

                    # 状态转换: TRANSLATE_RECORDING → TRANSLATE_TAIL_COLLECTING
                    self._transition_state(HotkeyState.TRANSLATE_TAIL_COLLECTING)

                    # 启动尾音收集定时器（延迟 200ms 后真正停止）
                    def finish_translate_tail_collecting():
                        with self._state_lock:
                            if self._state == HotkeyState.TRANSLATE_TAIL_COLLECTING:
                                logger.info(f"[双击模式] 翻译尾音收集完成 ({self.TAIL_SOUND_DELAY}ms)")
                                # 状态转换: TRANSLATE_TAIL_COLLECTING → IDLE
                                self._transition_state(HotkeyState.IDLE)
                                # 触发停止录音回调
                                self._trigger_callback(HotkeyAction.QUICK_TRANSLATE_RELEASE)

                    # 取消之前的尾音定时器（如果有）
                    if self._tail_timer:
                        self._tail_timer.cancel()

                    # 启动新的尾音定时器
                    self._tail_timer = threading.Timer(
                        self.TAIL_SOUND_DELAY / 1000.0,
                        finish_translate_tail_collecting
                    )
                    self._tail_timer.daemon = True
                    self._tail_timer.start()
                    return

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
                # Option/Alt 键 - 保留左右信息
                'alt': 'alt_l',      # macOS 左 Option/Alt 键（pynput 报告为 alt）
                'alt_l': 'alt_l',    # 左 Option/Alt
                'alt_r': 'alt_r',    # 右 Option/Alt（保留右侧信息）
                # Command 键 - 统一映射（但我们不会监听它）
                'cmd': 'cmd',        # macOS Command 键 (通用)
                'cmd_r': 'cmd',      # 右侧 Command 键映射到 cmd
                'cmd_l': 'cmd',      # 左侧 Command 键映射到 cmd
                # Control 键
                'ctrl': 'ctrl_l',    # 左 Ctrl
                'ctrl_r': 'ctrl_r',  # 右侧 Ctrl
                'ctrl_l': 'ctrl_l',  # 左侧 Ctrl
                # Shift 键
                'shift': 'shift_l',  # 左 Shift
                'shift_r': 'shift_r', # 右侧 Shift
                'shift_l': 'shift_l', # 左侧 Shift
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

    def recover(self) -> bool:
        """
        一键恢复：检查并恢复 listener 和 watchdog

        这是一个幂等操作，可以多次调用

        Returns:
            是否恢复成功
        """
        logger.info("开始一键恢复快捷键系统...")
        success = True

        # 检查并恢复 watchdog
        if not self.is_watchdog_alive():
            logger.warning("Watchdog 未运行，尝试重启...")
            if not self.restart_watchdog():
                success = False

        # 检查并恢复 listener
        listener_status = self.get_listener_status()
        if not listener_status['thread_alive'] or listener_status['health'] == '可能已静默失效':
            logger.warning(f"Listener 状态异常 ({listener_status['health']})，尝试重启...")
            if not self.restart_listener():
                success = False

        if success:
            logger.info("✓ 快捷键系统恢复成功")
        else:
            logger.error("✗ 快捷键系统恢复失败")

        return success

    def restart_watchdog(self) -> bool:
        """
        重启 watchdog（幂等操作）

        可以多次调用，不会重复创建

        Returns:
            是否重启成功
        """
        try:
            # 先停止现有的 watchdog
            self._stop_watchdog()

            # 启动新的 watchdog
            self._start_watchdog()

            logger.info("✓ Watchdog 重启成功")
            return True

        except Exception as e:
            logger.error(f"✗ Watchdog 重启失败: {e}")
            return False

    def restart_listener(self) -> bool:
        """
        重启 listener（幂等操作，带重试）

        可以多次调用，会安全地停止旧 listener 并启动新 listener

        Returns:
            是否重启成功
        """
        # 复用现有的 _restart_listener 方法（已包含重试逻辑）
        return self._restart_listener()


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
