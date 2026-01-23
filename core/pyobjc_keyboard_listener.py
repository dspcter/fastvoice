# core/pyobjc_keyboard_listener.py
# PyObjC 原生键盘监听器 v1.3.4
#
# v1.3.4 修复内容：
# - 修复退出时崩溃问题（移除手动 CFRelease 调用，让 PyObjC 自动管理对象生命周期）
#
# v1.3.3 修复内容：
# - 修复退出时崩溃问题（添加 __del__ 方法，在 Python GC 清理前释放 CoreFoundation 资源）
#
# v1.3.2 修复内容：
# - 修复退出时崩溃问题（添加资源释放标志，防止重复释放）
#
# v1.3.1 修复内容：
# - 正确处理 kCGEventFlagsChanged 事件
# - 通过 keycode 区分左右修饰键
# - 使用标志位变化判断按下/释放状态

import logging
import threading
import time
from typing import Callable, Optional

from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventGetType,
    CGEventMaskBit,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventFlagsChanged,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventTapOptionListenOnly,
    kCGHeadInsertEventTap,
    kCGSessionEventTap,
    kCGKeyboardEventKeycode,
)

from CoreFoundation import (
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRemoveSource,
    CFRunLoopRun,
    CFRunLoopStop,
    CFMachPortCreateRunLoopSource,
    kCFRunLoopDefaultMode,
)

# macOS 睡眠/唤醒通知（仅 macOS 可用）
try:
    from AppKit import NSWorkspace, NSWorkspaceWillSleepNotification, NSWorkspaceDidWakeNotification
    from PyObjCTools import AppHelper
    SLEEP_WAKE_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    SLEEP_WAKE_NOTIFICATIONS_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==================== 键码定义 ====================

class KeyCodes:
    """macOS 键码常量"""

    # 修饰键
    ALT_L = 0x3A   # 58 - 左 Option
    ALT_R = 0x3D   # 61 - 右 Option
    CMD_L = 0x37   # 55 - 左 Command
    CMD_R = 0x36   # 54 - 右 Command
    CTRL_L = 0x3B  # 59 - 左 Control
    CTRL_R = 0x3E  # 62 - 右 Control
    SHIFT_L = 0x38 # 56 - 左 Shift
    SHIFT_R = 0x3C # 60 - 右 Shift

    # 修饰键集合（用于快速判断）
    MODIFIER_KEYS = {ALT_L, ALT_R, CMD_L, CMD_R, CTRL_L, CTRL_R, SHIFT_L, SHIFT_R}


# ==================== 键名映射 ====================

_KEYCODE_TO_NAME = {
    KeyCodes.ALT_L: "alt_l",
    KeyCodes.ALT_R: "alt_r",
    KeyCodes.CMD_L: "cmd_l",
    KeyCodes.CMD_R: "cmd_r",
    KeyCodes.CTRL_L: "ctrl_l",
    KeyCodes.CTRL_R: "ctrl_r",
    KeyCodes.SHIFT_L: "shift_l",
    KeyCodes.SHIFT_R: "shift_r",
}


def keycode_to_name(keycode: int) -> str:
    """将键码转换为键名"""
    return _KEYCODE_TO_NAME.get(keycode, f"key_{keycode}")


# ==================== 修饰键状态追踪 ====================

class ModifierTracker:
    """
    修饰键状态追踪器（线程安全）

    功能：
    - 追踪每个修饰键的当前状态（按下/释放）
    - 通过比较标志位变化来判断状态变化
    """

    # 标志位到键码的映射（用于检测哪个修饰键变化）
    FLAG_TO_KEYCODES = {
        kCGEventFlagMaskAlternate: (KeyCodes.ALT_L, KeyCodes.ALT_R),
        kCGEventFlagMaskCommand: (KeyCodes.CMD_L, KeyCodes.CMD_R),
        kCGEventFlagMaskControl: (KeyCodes.CTRL_L, KeyCodes.CTRL_R),
        kCGEventFlagMaskShift: (KeyCodes.SHIFT_L, KeyCodes.SHIFT_R),
    }

    def __init__(self):
        # 线程锁（保护共享状态）
        self._lock = threading.Lock()

        # 当前修饰键状态（键码 -> 是否按下）
        self._key_states = {
            KeyCodes.ALT_L: False,
            KeyCodes.ALT_R: False,
            KeyCodes.CMD_L: False,
            KeyCodes.CMD_R: False,
            KeyCodes.CTRL_L: False,
            KeyCodes.CTRL_R: False,
            KeyCodes.SHIFT_L: False,
            KeyCodes.SHIFT_R: False,
        }
        # 当前标志位
        self._current_flags = 0

    def update_from_key_event(self, keycode: int, event_type: int) -> Optional[tuple]:
        """
        从普通按键事件更新状态

        Args:
            keycode: 键码
            event_type: 事件类型

        Returns:
            (key_name, is_pressed) 或 None
        """
        if keycode not in KeyCodes.MODIFIER_KEYS:
            return None

        is_pressed = (event_type == kCGEventKeyDown)

        with self._lock:
            self._key_states[keycode] = is_pressed

        return keycode_to_name(keycode), is_pressed

    def update_from_flags_changed(self, keycode: int, new_flags: int) -> Optional[tuple]:
        """
        从 kCGEventFlagsChanged 事件更新状态

        这是关键方法：通过 keycode 确定是哪个修饰键，
        通过标志位变化判断是按下还是释放

        Args:
            keycode: 键码
            new_flags: 新的标志位

        Returns:
            (key_name, is_pressed) 或 None
        """
        if keycode not in KeyCodes.MODIFIER_KEYS:
            return None

        with self._lock:
            # 检查状态是否变化
            was_pressed = self._key_states[keycode]

            # 确定当前状态：检查对应的标志位
            is_pressed = False
            if keycode in [KeyCodes.ALT_L, KeyCodes.ALT_R]:
                is_pressed = bool(new_flags & kCGEventFlagMaskAlternate)
            elif keycode in [KeyCodes.CMD_L, KeyCodes.CMD_R]:
                is_pressed = bool(new_flags & kCGEventFlagMaskCommand)
            elif keycode in [KeyCodes.CTRL_L, KeyCodes.CTRL_R]:
                is_pressed = bool(new_flags & kCGEventFlagMaskControl)
            elif keycode in [KeyCodes.SHIFT_L, KeyCodes.SHIFT_R]:
                is_pressed = bool(new_flags & kCGEventFlagMaskShift)

            # 只在状态变化时触发
            if was_pressed != is_pressed:
                self._key_states[keycode] = is_pressed
                self._current_flags = new_flags
                return keycode_to_name(keycode), is_pressed

            self._current_flags = new_flags

        return None

    def is_pressed(self, keycode: int) -> bool:
        """检查按键是否按下"""
        with self._lock:
            return self._key_states.get(keycode, False)


# ==================== PyObjC 原生键盘监听器 ====================

class PyObjCKeyboardListener:
    """
    PyObjC 原生键盘监听器 v1.3.4

    核心改进：
    1. 正确处理 kCGEventFlagsChanged 事件
    2. 通过 keycode 区分左右修饰键
    3. 使用标志位变化判断按下/释放
    4. 移除手动 CFRelease，让 PyObjC 自动管理对象生命周期（v1.3.4）

    性能特性：
    - 启动快速（<50ms）
    - 内存占用低（<5MB）
    - 无 TSM 线程安全问题
    - 退出时无崩溃

    v1.3.4 关键修复：
    - 不再手动调用 CFRelease，避免与 PyObjC 的内部清理冲突
    - PyObjC 会在 Python GC 时自动调用 CFRelease
    - 只需确保从 RunLoop 移除 source 并停止 RunLoop
    """

    def __init__(
        self,
        on_press: Optional[Callable[[str], None]] = None,
        on_release: Optional[Callable[[str], None]] = None,
    ):
        """
        初始化监听器

        Args:
            on_press: 按键按下回调（参数：key_name）
            on_release: 按键释放回调（参数：key_name）
        """
        self.on_press = on_press
        self.on_release = on_release

        # Event Tap 相关
        self._tap = None
        self._loop_source = None
        self._loop = None

        # 监听线程
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # 修饰键状态追踪
        self._modifier_tracker = ModifierTracker()

        # 性能统计
        self._events_processed = 0
        self._callback_errors = 0
        self._startup_time = 0

        # ============ v1.4.0 诊断功能 ============
        # 最后按键事件时间（用于检测静默失效）
        self._last_event_time: float = time.time()
        self._last_event_lock = threading.Lock()

        # 修饰键事件计数（分别统计按下和释放）
        self._modifier_press_count = 0
        self._modifier_release_count = 0
        self._modifier_event_lock = threading.Lock()

        # 事件类型统计
        self._event_type_stats = {
            "keydown": 0,
            "keyup": 0,
            "flags_changed": 0,
        }
        self._event_stats_lock = threading.Lock()

        # 睡眠/唤醒事件追踪
        self._sleep_count = 0
        self._wake_count = 0
        self._last_sleep_time: Optional[float] = None
        self._last_wake_time: Optional[float] = None

        logger.info("PyObjCKeyboardListener v1.3.4 初始化完成（含诊断增强）")

    def start(self) -> bool:
        """
        启动监听器

        Returns:
            是否启动成功
        """
        if self._running:
            logger.warning("监听器已在运行")
            return True

        start_time = time.perf_counter()

        try:
            # 创建 Event Tap
            if not self._create_event_tap():
                logger.error("创建 Event Tap 失败")
                return False

            # 启动监听线程
            self._running = True
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="PyObjCKeyboardListener",
                daemon=False,  # 非守护线程：确保有足够时间清理资源
            )
            self._thread.start()

            # 等待线程启动
            deadline = time.time() + 1.0
            while self._loop is None and time.time() < deadline:
                time.sleep(0.01)

            if self._loop is None:
                logger.error("监听线程启动超时")
                self.stop()
                return False

            # 记录启动时间
            self._startup_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"✓ 监听器启动成功 (耗时: {self._startup_time:.2f}ms)")
            return True

        except Exception as e:
            logger.error(f"启动监听器失败: {e}", exc_info=True)
            self.stop()
            return False

    def stop(self) -> None:
        """停止监听器"""
        if not self._running:
            return

        logger.info("停止监听器...")
        self._running = False

        # 停止 Run Loop
        if self._loop is not None:
            try:
                CFRunLoopStop(self._loop)
            except Exception as e:
                logger.warning(f"停止 Run Loop 失败: {e}")

        # 等待线程结束
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("监听线程停止超时")

        # 清理资源
        self._cleanup_resources()

        logger.info("监听器已停止")

    def is_alive(self) -> bool:
        """检查监听器是否存活"""
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            包含详细统计信息的字典
        """
        with self._last_event_lock:
            last_event_time = self._last_event_time

        with self._modifier_event_lock:
            press_count = self._modifier_press_count
            release_count = self._modifier_release_count

        with self._event_stats_lock:
            event_stats = self._event_type_stats.copy()

        return {
            "events_processed": self._events_processed,
            "callback_errors": self._callback_errors,
            "startup_time_ms": round(self._startup_time, 2),
            "is_alive": self.is_alive(),
            # v1.4.0 新增诊断信息
            "last_event_time": last_event_time,
            "seconds_since_last_event": time.time() - last_event_time,
            "modifier_press_count": press_count,
            "modifier_release_count": release_count,
            "event_type_stats": event_stats,
        }

    def get_last_event_time(self) -> float:
        """
        获取最后一次按键事件的时间

        Returns:
            最后一次事件的时间戳
        """
        with self._last_event_lock:
            return self._last_event_time

    def get_diagnostics_report(self) -> str:
        """
        获取诊断报告（用于日志输出）

        Returns:
            诊断报告字符串
        """
        stats = self.get_stats()
        seconds_since_last = stats["seconds_since_last_event"]

        # 判断健康状态
        if seconds_since_last > 300:  # 5 分钟
            health = "⚠ 可能已静默失效"
        elif seconds_since_last > 60:  # 1 分钟
            health = "⚠ 可能闲置中"
        else:
            health = "✓ 正常"

        report = (
            f"Listener: {health} | "
            f"事件: {stats['events_processed']} | "
            f"距上次: {seconds_since_last:.0f}s | "
            f"修饰键: ↑{stats['modifier_press_count']} ↓{stats['modifier_release_count']} | "
            f"类型: K↓{stats['event_type_stats']['keydown']} "
            f"K↑{stats['event_type_stats']['keyup']} "
            f"F⚡{stats['event_type_stats']['flags_changed']}"
        )

        # 添加睡眠/唤醒信息（如果有）
        if self._sleep_count > 0 or self._wake_count > 0:
            report += f" | 睡眠/唤醒: 💤{self._sleep_count} ☀️{self._wake_count}"
            if self._last_wake_time:
                seconds_since_wake = time.time() - self._last_wake_time
                report += f" (距唤醒: {seconds_since_wake:.0f}s)"

        return report

    # ==================== 内部方法 ====================

    def _create_event_tap(self) -> bool:
        """创建 Event Tap"""
        try:
            # 定义事件掩码（监听所有类型的事件）
            event_mask = (
                CGEventMaskBit(kCGEventKeyDown)
                | CGEventMaskBit(kCGEventKeyUp)
                | CGEventMaskBit(kCGEventFlagsChanged)
            )

            # 创建 Event Tap
            self._tap = CGEventTapCreate(
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventTapOptionListenOnly,  # 只监听，不拦截
                event_mask,
                self._event_callback,
                None,
            )

            if self._tap is None:
                logger.error("无法创建 Event Tap（可能需要辅助功能权限）")
                return False

            logger.debug("Event Tap 创建成功")
            return True

        except Exception as e:
            logger.error(f"创建 Event Tap 失败: {e}", exc_info=True)
            return False

    def _run_event_loop(self) -> None:
        """运行事件循环（在专用线程中）"""
        thread_id = threading.get_ident()
        logger.info(f"事件循环线程启动 (thread_id: {thread_id})")

        # 睡眠/唤醒通知回调
        def _on_sleep_notification(notification):
            self._sleep_count += 1
            self._last_sleep_time = time.time()
            logger.warning(f"💤 系统即将睡眠 (第 {self._sleep_count} 次)")

        def _on_wake_notification(notification):
            self._wake_count += 1
            self._last_wake_time = time.time()
            logger.info(f"☀️  系统已唤醒 (第 {self._wake_count} 次)")

        try:
            # 获取当前线程的 Run Loop
            self._loop = CFRunLoopGetCurrent()

            # 创建 Run Loop Source
            self._loop_source = CFMachPortCreateRunLoopSource(None, self._tap, 0)

            # 添加到 Run Loop
            CFRunLoopAddSource(
                self._loop,
                self._loop_source,
                kCFRunLoopDefaultMode
            )

            # 注册睡眠/唤醒通知（如果可用）
            if SLEEP_WAKE_NOTIFICATIONS_AVAILABLE:
                try:
                    workspace = NSWorkspace.sharedWorkspace()
                    workspace.notificationCenter_addObserver_object_name_(
                        self, _on_sleep_notification,
                        NSWorkspaceWillSleepNotification, None
                    )
                    workspace.notificationCenter_addObserver_object_name_(
                        self, _on_wake_notification,
                        NSWorkspaceDidWakeNotification, None
                    )
                    logger.info("已注册系统睡眠/唤醒通知监听")
                except Exception as e:
                    logger.warning(f"注册睡眠/唤醒通知失败: {e}")

            # 启用 Event Tap
            CGEventTapEnable(self._tap, True)

            logger.debug("事件循环开始运行")

            # 运行事件循环（阻塞，直到调用 CFRunLoopStop）
            CFRunLoopRun()

            logger.debug("事件循环已停止")

        except Exception as e:
            logger.error(f"事件循环异常: {e}", exc_info=True)
        finally:
            logger.info(f"事件循环线程退出 (thread_id: {thread_id}")

    def _event_callback(self, proxy, event_type, event, refcon):
        """
        事件回调函数（在监听线程中调用）

        这是核心方法：正确处理所有事件类型，包括修饰键
        """
        try:
            self._events_processed += 1

            # 更新最后事件时间（用于检测静默失效）
            with self._last_event_lock:
                self._last_event_time = time.time()

            # v1.4.0: 检查是否正在注入文字，如果是则忽略 Command+V 等注入事件
            if self._should_ignore_injection_event(event, event_type):
                return  # 不处理这个事件，让它正常传递

            # 获取键码
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            key_name = keycode_to_name(keycode)

            # 处理不同类型的事件
            if event_type == kCGEventKeyDown:
                # 更新事件类型统计
                with self._event_stats_lock:
                    self._event_type_stats["keydown"] += 1

                # 普通按键按下
                result = self._modifier_tracker.update_from_key_event(keycode, event_type)
                if result:
                    key_name, is_pressed = result
                    # 修饰键按下：记录详细日志
                    with self._modifier_event_lock:
                        self._modifier_press_count += 1
                    logger.debug(f"⌨  [KEYDOWN] {key_name} (keycode: {keycode})")
                    if is_pressed and self.on_press:
                        self._safe_callback(self.on_press, key_name)

            elif event_type == kCGEventKeyUp:
                # 更新事件类型统计
                with self._event_stats_lock:
                    self._event_type_stats["keyup"] += 1

                # 普通按键释放
                result = self._modifier_tracker.update_from_key_event(keycode, event_type)
                if result:
                    key_name, is_pressed = result
                    # 修饰键释放：记录详细日志
                    with self._modifier_event_lock:
                        self._modifier_release_count += 1
                    logger.debug(f"⌨  [KEYUP] {key_name} (keycode: {keycode})")
                    if not is_pressed and self.on_release:
                        self._safe_callback(self.on_release, key_name)

            elif event_type == kCGEventFlagsChanged:
                # 更新事件类型统计
                with self._event_stats_lock:
                    self._event_type_stats["flags_changed"] += 1

                # 修饰键状态变化（关键改进！）
                flags = CGEventGetFlags(event)

                # 通过 keycode 确定是哪个修饰键
                # 通过标志位变化判断是按下还是释放
                result = self._modifier_tracker.update_from_flags_changed(keycode, flags)

                if result:
                    key_name, is_pressed = result
                    action = "按下" if is_pressed else "释放"
                    # 修饰键事件：记录详细日志（使用 info 级别）
                    logger.info(f"⌨  [MODIFIER] {key_name} {action} (keycode: {keycode})")
                    if is_pressed:
                        with self._modifier_event_lock:
                            self._modifier_press_count += 1
                        if self.on_press:
                            self._safe_callback(self.on_press, key_name)
                    elif not is_pressed:
                        with self._modifier_event_lock:
                            self._modifier_release_count += 1
                        if self.on_release:
                            self._safe_callback(self.on_release, key_name)

            # 返回事件（传递给其他应用）
            return event

        except Exception as e:
            logger.error(f"事件回调异常: {e}", exc_info=True)
            self._callback_errors += 1
            return event

    def _safe_callback(self, callback: Callable, key_name: str):
        """安全调用回调函数"""
        try:
            callback(key_name)
        except Exception as e:
            self._callback_errors += 1
            logger.error(f"回调异常 ({key_name}): {e}")

    def _should_ignore_injection_event(self, event, event_type) -> bool:
        """
        检查是否应该忽略注入事件（v1.4.0）

        当应用自己发送 Command+V 进行文字注入时，
        监听器不应该拦截这个事件，否则会导致注入失败。

        Returns:
            True if this is an injection event that should be ignored
        """
        try:
            # 检查全局注入标志
            from core.text_injector import _is_injecting
            if not _is_injecting:
                return False

            # 获取键码和标志
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)

            # V 键的键码是 0x09 (v1.4.3 修复)
            if keycode != 0x09:
                return False

            # 检查是否有 Command 标志
            from Quartz import kCGEventFlagMaskCommand
            has_command = bool(flags & kCGEventFlagMaskCommand)

            # 如果是 Command+V，忽略这个事件
            if has_command:
                logger.debug(f"⚠️ 忽略注入事件: Command+V (keycode={keycode}, flags={flags})")
                return True

            return False

        except Exception as e:
            logger.debug(f"检查注入事件时出错: {e}")
            return False

    def _cleanup_resources(self) -> None:
        """
        清理资源（防止内存泄漏和退出后事件残留）

        v1.5.1 关键改进：
        - 先禁用 Event Tap，防止退出后仍触发事件
        - 再从 RunLoop 移除 source
        - 最后清空引用
        """
        try:
            # 步骤1: 禁用 Event Tap（关键！防止退出后仍触发事件）
            if self._tap is not None:
                try:
                    CGEventTapEnable(self._tap, False)
                    logger.info("✓ Event Tap 已禁用")
                except Exception as e:
                    logger.warning(f"禁用 Event Tap 失败: {e}")

            # 步骤2: 从 Run Loop 移除 Source（防止 RunLoop 持有引用）
            if self._loop_source is not None and self._loop is not None:
                try:
                    CFRunLoopRemoveSource(
                        self._loop,
                        self._loop_source,
                        kCFRunLoopDefaultMode
                    )
                    logger.debug("Loop Source 已从 Run Loop 移除")
                except Exception as e:
                    logger.debug(f"移除 Loop Source 失败: {e}")

            # 步骤3: 清空引用（让 Python GC 清理 PyObjC 对象）
            self._loop_source = None
            self._tap = None
            self._loop = None

            logger.info("✓ 资源引用已清空")

        except Exception as e:
            logger.debug(f"清理资源时出错: {e}")
            # 确保引用被清空
            self._loop_source = None
            self._tap = None
            self._loop = None
